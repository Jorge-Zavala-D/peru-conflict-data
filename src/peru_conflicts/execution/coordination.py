"""Private coordinator execution contracts; never distribute these to annotators."""

from collections.abc import Mapping, Sequence
from typing import Literal, Self

from pydantic import Field, model_validator

from peru_conflicts.benchmark.models import PartitionRole
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .packages import PackageManifest, verify_package
from .references import sha256


class EligibilityAttestation(StrictModel):
    """Future private coordinator assertion, not proof of authorship or launch authority."""

    role: Literal["annotator-a", "annotator-b"]
    private_person_token: str = Field(min_length=1)
    distinct_human_confirmed: bool
    machine_answers_seen: bool
    parser_predictions_seen: bool
    machine_prefill_seen: bool
    other_submission_seen: bool
    partition_labels_received: bool


def verify_eligibility(a: EligibilityAttestation, b: EligibilityAttestation) -> None:
    if (a.role, b.role) != ("annotator-a", "annotator-b") or (
        a.private_person_token == b.private_person_token
    ):
        raise ValueError("A/B must represent distinct privately attested humans")
    for person in (a, b):
        if not person.distinct_human_confirmed or any(
            (
                person.machine_answers_seen,
                person.parser_predictions_seen,
                person.machine_prefill_seen,
                person.other_submission_seen,
                person.partition_labels_received,
            )
        ):
            raise ValueError("human is not eligible for blind annotation")


class SubmissionRoute(StrictModel):
    report_number: int = Field(ge=260, le=269)
    partition_role: PartitionRole
    sealed: bool
    development_visible: Literal[False] = False

    @model_validator(mode="after")
    def preserve_sealing(self) -> Self:
        if self.partition_role is PartitionRole.HELD_OUT_EVALUATION and not self.sealed:
            raise ValueError("held-out labels must remain coordinator-only sealed")
        return self


class CoordinatorContext(StrictModel):
    kind: Literal["COORDINATOR_ONLY_NOT_FOR_ANNOTATORS"] = "COORDINATOR_ONLY_NOT_FOR_ANNOTATORS"
    package_id: Sha256
    role: Literal["annotator-a", "annotator-b"]
    routes: tuple[SubmissionRoute, ...]
    submission_root: Literal["submissions/annotator-a", "submissions/annotator-b"]
    comparison_root: Literal["coordinator/comparisons"] = "coordinator/comparisons"
    annotation_launch_approved: Literal[False] = False


def build_context(
    package: PackageManifest, partitions: Mapping[int, PartitionRole]
) -> CoordinatorContext:
    if set(partitions) != {m.report_number for m in package.references}:
        raise ValueError("coordinator source assignment differs from neutral package")
    return CoordinatorContext(
        package_id=package.package_id,
        role=package.role,
        submission_root="submissions/annotator-a"
        if package.role == "annotator-a"
        else "submissions/annotator-b",
        routes=tuple(
            SubmissionRoute(
                report_number=number,
                partition_role=partition,
                sealed=partition is PartitionRole.HELD_OUT_EVALUATION,
            )
            for number, partition in sorted(partitions.items())
        ),
    )


def verify_context(context: CoordinatorContext, package: PackageManifest) -> None:
    expected = build_context(package, {r.report_number: r.partition_role for r in context.routes})
    if context != expected:
        raise ValueError("coordinator package/role/routing identity changed")


class IssuedPackageIdentity(StrictModel):
    """Neutral source/protocol identity; contains neither personnel nor partition labels."""

    run_id: Literal["m2-02-v1", "synthetic-run"]
    role: Literal["annotator-a", "annotator-b"]
    package_id: Sha256
    manifest_sha256: Sha256
    reference_aggregate_sha256: Sha256
    file_set_sha256: Sha256
    reference_policy_sha256s: tuple[Sha256, ...]
    execution_policy_version: Literal["m2-02-execution-policy-v1"] = "m2-02-execution-policy-v1"
    neutral_reader_contract: Literal["m2-neutral-reader-contract-v1"] = (
        "m2-neutral-reader-contract-v1"
    )


class EligibilityBinding(StrictModel):
    """Coordinator-only; opaque token digests are private, never annotator material."""

    kind: Literal["COORDINATOR_ONLY_ELIGIBILITY_BINDING"] = "COORDINATOR_ONLY_ELIGIBILITY_BINDING"
    binding_id: Sha256
    identity: IssuedPackageIdentity
    attestation_sha256: Sha256
    private_person_token_sha256: Sha256
    owner_readiness_approved: Literal[False] = False
    annotation_launch_approved: Literal[False] = False


class PackageIssuanceReceipt(StrictModel):
    """Out-of-band coordinator trust material, not a signature or issuance permission."""

    identity: IssuedPackageIdentity
    eligibility_binding_id: Sha256
    eligibility_binding_sha256: Sha256
    issuance_state: Literal["unissued_readiness_candidate"] = "unissued_readiness_candidate"
    owner_readiness_approved: Literal[False] = False
    annotation_launch_approved: Literal[False] = False


def _model_sha(value: StrictModel) -> str:
    return sha256(canonical_json_bytes(value.model_dump(mode="json")))


def package_identity(
    files: Mapping[str, bytes], *, allow_drafts: bool = False
) -> IssuedPackageIdentity:
    manifest = verify_package(files, allow_drafts=allow_drafts)
    return IssuedPackageIdentity(
        run_id=manifest.run_id,
        role=manifest.role,
        package_id=manifest.package_id,
        manifest_sha256=sha256(files["PACKAGE_MANIFEST.json"]),
        reference_aggregate_sha256=sha256(
            canonical_json_bytes([m.snapshot_sha256 for m in manifest.references])
        ),
        file_set_sha256=sha256(canonical_json_bytes(manifest.file_hashes)),
        reference_policy_sha256s=tuple(
            sorted({m.extraction_policy_sha256 for m in manifest.references})
        ),
    )


def bind_eligibility_pair(
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
    *,
    allow_drafts: bool = False,
) -> tuple[EligibilityBinding, ...]:
    if len(people) != 2 or len(packages) != 2:
        raise ValueError("issuance requires both independent A/B attestations and packages")
    people = tuple(EligibilityAttestation.model_validate(p.model_dump()) for p in people)
    verify_eligibility(people[0], people[1])
    bindings: list[EligibilityBinding] = []
    for person, files in zip(people, packages, strict=True):
        identity = package_identity(files, allow_drafts=allow_drafts)
        if person.role != identity.role:
            raise ValueError("eligibility role differs from package issuance role")
        person_sha = sha256(b"m2-private-person-v1\0" + person.private_person_token.encode("utf-8"))
        attestation_sha = _model_sha(person)
        binding_id = sha256(
            canonical_json_bytes([identity.model_dump(mode="json"), person_sha, attestation_sha])
        )
        bindings.append(
            EligibilityBinding(
                binding_id=binding_id,
                identity=identity,
                attestation_sha256=attestation_sha,
                private_person_token_sha256=person_sha,
            )
        )
    if bindings[0].identity.run_id != bindings[1].identity.run_id or (
        bindings[0].identity.reference_aggregate_sha256
        != bindings[1].identity.reference_aggregate_sha256
    ):
        raise ValueError("A/B issuance references/run differ")
    return tuple(bindings)


def issuance_receipt(binding: EligibilityBinding) -> PackageIssuanceReceipt:
    binding = EligibilityBinding.model_validate(binding.model_dump())
    return PackageIssuanceReceipt(
        identity=binding.identity,
        eligibility_binding_id=binding.binding_id,
        eligibility_binding_sha256=_model_sha(binding),
    )


def verify_trusted_package(
    files: Mapping[str, bytes], expected: PackageIssuanceReceipt, *, allow_drafts: bool = False
) -> PackageManifest:
    expected = PackageIssuanceReceipt.model_validate(expected.model_dump())
    if package_identity(files, allow_drafts=allow_drafts) != expected.identity:
        raise ValueError("package differs from trusted coordinator issuance identity")
    return verify_package(files, allow_drafts=allow_drafts)


def verify_issuance_pair(
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
    bindings: Sequence[EligibilityBinding],
    receipts: Sequence[PackageIssuanceReceipt],
) -> None:
    expected = bind_eligibility_pair(people, packages, allow_drafts=True)
    if tuple(bindings) != expected or len(receipts) != 2:
        raise ValueError("eligibility/issuance binding changed")
    for files, binding, receipt in zip(packages, expected, receipts, strict=True):
        if receipt != issuance_receipt(binding):
            raise ValueError("issuance receipt changed")
        verify_trusted_package(files, receipt, allow_drafts=True)


def production_lock_preflight(
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
    bindings: Sequence[EligibilityBinding],
    receipts: Sequence[PackageIssuanceReceipt],
) -> None:
    """Future mandatory custody contract; even a valid binding cannot enable real locking."""
    verify_issuance_pair(people, packages, bindings, receipts)
    raise ValueError("production locking remains disabled: readiness and launch are unapproved")
