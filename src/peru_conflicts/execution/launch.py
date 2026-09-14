"""Coordinator-only draft launch controls; never authority or an execution API."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator, model_validator

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .contracts import AnnotationContractIdentity, validate_annotation_contract_alignment
from .coordination import (
    EligibilityAttestation,
    EligibilityBinding,
    IssuedPackageIdentity,
    PackageIssuanceReceipt,
    bind_eligibility_pair,
    package_identity,
    verify_issuance_pair,
)
from .evidence_index import OwnerReadinessEvidenceIndex, validate_evidence_index
from .references import sha256
from .runtime_build import NeutralViewIdentity, RuntimeManifest

ROOT = Path(__file__).resolve().parents[3]

DRAFT_FALSE_FLAGS = (
    "owner_launch_approved",
    "annotation_launch_approved",
    "annotation_started",
    "real_humans_assigned",
    "real_eligibility_attestations_created",
    "external_root_created",
    "dropbox_writes_approved",
    "real_access_tests_passed",
    "real_issuance_receipts_created",
    "real_packages_issued",
    "production_locking_enabled",
    "human_gold_created",
    "parser_work_approved",
    "m3_owner_approved",
    "normative_metric_amendment_approved",
)

# Each ID fixes actor, operation, resource and the required outcome. PASS means
# that outcome was observed, so a denied-read check must never mean read allowed.
ACCESS_CHECKS: dict[str, tuple[str, str, str, str]] = {
    "a-read-own-issue": ("annotator-a", "read", "annotator-a/issue", "allow"),
    "a-write-own-submission": ("annotator-a", "write", "annotator-a/submission", "allow"),
    "b-read-own-issue": ("annotator-b", "read", "annotator-b/issue", "allow"),
    "b-write-own-submission": ("annotator-b", "write", "annotator-b/submission", "allow"),
    **{
        f"coordinator-{operation}-{area}-{role}": (
            "coordinator",
            operation,
            f"annotator-{role}/{area}",
            "allow",
        )
        for role in ("a", "b")
        for area in ("issue", "submission")
        for operation in ("list", "read")
    },
    **{
        f"{role}-{operation}-other-{area}": (
            f"annotator-{role}",
            operation,
            f"annotator-{other}/{area}",
            "deny",
        )
        for role, other in (("a", "b"), ("b", "a"))
        for area in ("issue", "submission")
        for operation in ("list", "read")
    },
    **{
        f"{role}-{operation}-{area}": (
            f"annotator-{role}",
            operation,
            f"coordinator/{area}",
            "deny",
        )
        for role in ("a", "b")
        for area in (
            "custody",
            "comparison",
            "adjudication",
            "held-out-sealed",
            "receipts",
            "locked/annotator-a",
            "locked/annotator-b",
            "supersession",
        )
        for operation in ("list", "read")
    },
    **{
        f"coordinator-{operation}-custody": (
            "coordinator",
            operation,
            "coordinator/custody",
            "allow",
        )
        for operation in ("list", "read")
    },
}

# These are named hypothetical prerequisite assertions, never callable actions.
# External-write authority is checked before any hypothetical external operation.
CEREMONY_STEPS = (
    "launch_authority",
    "exact_runtime",
    "exact_packages",
    "exact_references",
    "private_eligibility",
    "distinct_people",
    "real_access_tests",
    "external_write_authority",
    "external_paths_and_permissions",
    "eligibility_bindings",
    "issuance_receipts",
    "issue_a_only_to_a",
    "issue_b_only_to_b",
    "independent_issued_bytes",
    "issue_timestamp_and_identity",
    "annotation_start",
)


def model_sha256(value: StrictModel) -> str:
    return sha256(canonical_json_bytes(value.model_dump(mode="json")))


class LaunchIdentity(StrictModel):
    """Original readiness lineage and separate derived/runtime custody pins."""

    original: IssuedPackageIdentity
    projection_policy: Literal["m2-neutral-human-view-v1"] = "m2-neutral-human-view-v1"
    view_sha256: Sha256
    view_file_set_sha256: Sha256
    runtime_policy: Literal["m2-neutral-runtime-source-selection-v1"] = (
        "m2-neutral-runtime-source-selection-v1"
    )
    runtime_sha256: Sha256
    runtime_file_set_sha256: Sha256
    runtime_contract_sha256: Sha256
    registry_sha256: Sha256
    launcher_sha256: Sha256
    interpreter_sha256: Sha256
    dependency_sha256: Sha256

    @model_validator(mode="after")
    def contract_alignment(self) -> Self:
        expected = sha256(
            canonical_json_bytes(self.original.contract_identity.model_dump(mode="json")) + b"\n"
        )
        if self.runtime_contract_sha256 != expected:
            raise ValueError("runtime contract differs from original package contract")
        return self


def compose_identity(
    original: IssuedPackageIdentity, view: NeutralViewIdentity, runtime: RuntimeManifest
) -> LaunchIdentity:
    original = IssuedPackageIdentity.model_validate_json(original.model_dump_json())
    view = NeutralViewIdentity.model_validate_json(view.model_dump_json())
    runtime = RuntimeManifest.model_validate_json(runtime.model_dump_json())
    validate_annotation_contract_alignment(original.contract_identity)
    if (
        view.original_package_sha256 != original.manifest_sha256
        or view.original_package_id != original.package_id
        or view.contract_sha256 != runtime.contract_sha256
    ):
        raise ValueError("neutral view differs from original package/runtime lineage")
    return LaunchIdentity(
        original=original,
        view_sha256=view.view_sha256,
        view_file_set_sha256=sha256(canonical_json_bytes(view.file_hashes)),
        runtime_sha256=runtime.runtime_sha256,
        runtime_file_set_sha256=sha256(canonical_json_bytes(runtime.file_hashes)),
        runtime_contract_sha256=runtime.contract_sha256,
        registry_sha256=runtime.registry_sha256,
        launcher_sha256=runtime.launcher_sha256,
        interpreter_sha256=runtime.interpreter_sha256,
        dependency_sha256=runtime.dependency_sha256,
    )


def _validate_pair(identities: Sequence[LaunchIdentity]) -> tuple[LaunchIdentity, ...]:
    pair = tuple(
        LaunchIdentity.model_validate_json(identity.model_dump_json()) for identity in identities
    )
    if len(pair) != 2 or tuple(i.original.role for i in pair) != ("annotator-a", "annotator-b"):
        raise ValueError("composite identities require ordered A/B roles")
    a, b = pair
    if (
        a.original.run_id != b.original.run_id
        or a.original.contract_identity != b.original.contract_identity
        or a.original.reference_aggregate_sha256 != b.original.reference_aggregate_sha256
        or a.original.reference_policy_sha256s != b.original.reference_policy_sha256s
        or a.model_dump(exclude={"original", "view_sha256", "view_file_set_sha256"})
        != b.model_dump(exclude={"original", "view_sha256", "view_file_set_sha256"})
    ):
        raise ValueError("A/B composite run/reference/runtime identities differ")
    return pair


def pair_sha256(identities: Sequence[LaunchIdentity]) -> str:
    pair = _validate_pair(identities)
    return sha256(
        b"m2-launch-composite-pair-v1\0"
        + canonical_json_bytes([i.model_dump(mode="json") for i in pair])
    )


class LaunchCandidate(StrictModel):
    candidate_id: Literal["M2-02-LAUNCH-CANDIDATE-V1"] = "M2-02-LAUNCH-CANDIDATE-V1"
    status: Literal["owner_review_draft"] = "owner_review_draft"
    protected_main_merge_sha: Literal["995b54115f94454fc81d4af36f138add43ba8614"]
    protected_main_merge_tree: Literal["67284c356125d4f9758dc28a9e6c92a45cab3553"]
    readiness_v3_sha256: Sha256
    evidence_v5_sha256: Sha256
    reference_manifest_sha256: Sha256
    contract_identity: AnnotationContractIdentity
    identities: tuple[LaunchIdentity, LaunchIdentity]
    external_layout_version: Literal["m2-02-external-layout-v1"] = "m2-02-external-layout-v1"
    access_control_test_protocol_version: Literal["m2-02-real-access-tests-v1"] = (
        "m2-02-real-access-tests-v1"
    )
    owner_readiness_approved: Literal[True] = True
    owner_launch_approved: Literal[False] = False
    annotation_launch_approved: Literal[False] = False
    annotation_started: Literal[False] = False
    real_humans_assigned: Literal[False] = False
    real_eligibility_attestations_created: Literal[False] = False
    external_root_created: Literal[False] = False
    dropbox_writes_approved: Literal[False] = False
    real_access_tests_passed: Literal[False] = False
    real_issuance_receipts_created: Literal[False] = False
    real_packages_issued: Literal[False] = False
    production_locking_enabled: Literal[False] = False
    human_gold_created: Literal[False] = False
    parser_work_approved: Literal[False] = False
    m3_owner_approved: Literal[False] = False
    normative_metric_amendment_approved: Literal[False] = False

    @field_validator(*DRAFT_FALSE_FLAGS, mode="before")
    @classmethod
    def flags_are_literal_booleans(cls, value: object) -> object:
        if value is not False:
            raise ValueError("draft launch flags must be literal false")
        return value

    @field_validator("owner_readiness_approved", mode="before")
    @classmethod
    def readiness_is_literal_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("owner readiness flag must be literal true")
        return value

    @model_validator(mode="after")
    def consistent_pair(self) -> Self:
        pair = _validate_pair(self.identities)
        if pair[0].original.contract_identity != self.contract_identity:
            raise ValueError("candidate differs from governing annotation contract")
        return self


def verify_candidate(
    candidate: LaunchCandidate, expected_candidate_sha256: str, identities: Sequence[LaunchIdentity]
) -> None:
    """Read-only custody check; caller supplies a separately trusted candidate pin."""
    candidate = LaunchCandidate.model_validate_json(candidate.model_dump_json())
    if model_sha256(candidate) != expected_candidate_sha256:
        raise ValueError("candidate differs from independently trusted digest")
    validate_annotation_contract_alignment(candidate.contract_identity)
    evidence_path = "docs/m2_02a_readiness_evidence_index_v5.yaml"
    for path, expected in (
        ("config/benchmark/m2_02a_readiness_v3.yaml", candidate.readiness_v3_sha256),
        (evidence_path, candidate.evidence_v5_sha256),
    ):
        data = (ROOT / path).read_bytes()
        if sha256(data) != expected:
            raise ValueError("candidate readiness/evidence authority is stale")
        if path == evidence_path:
            evidence = validate_evidence_index(data)
            if (
                not isinstance(evidence, OwnerReadinessEvidenceIndex)
                or evidence.reference_manifest_sha256 != candidate.reference_manifest_sha256
            ):
                raise ValueError("candidate reference manifest differs from governing evidence")
    if _validate_pair(identities) != candidate.identities:
        raise ValueError("observed composite differs from independently pinned candidate")


class CompositeEligibilityBinding(StrictModel):
    kind: Literal["SYNTHETIC_COMPOSITE_ELIGIBILITY_REHEARSAL"] = (
        "SYNTHETIC_COMPOSITE_ELIGIBILITY_REHEARSAL"
    )
    original_binding: EligibilityBinding
    composite_sha256: Sha256
    model_as_annotator: Literal[False] = False
    held_out_labels_seen: Literal[False] = False


def bind_synthetic_eligibility(
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
    identities: Sequence[LaunchIdentity],
    *,
    model_as_annotator: Sequence[bool],
    held_out_labels_seen: Sequence[bool],
) -> tuple[CompositeEligibilityBinding, ...]:
    pair = _validate_pair(identities)
    if any(i.original.run_id != "synthetic-run" for i in pair):
        raise ValueError("eligibility rehearsal requires synthetic-run packages")
    if tuple(model_as_annotator) != (False, False) or tuple(held_out_labels_seen) != (False, False):
        raise ValueError("synthetic person has prohibited model use or held-out exposure")
    bindings = bind_eligibility_pair(people, packages)
    result: list[CompositeEligibilityBinding] = []
    for binding, identity in zip(bindings, pair, strict=True):
        if binding.identity != identity.original:
            raise ValueError("eligibility and original package identity differ")
        result.append(
            CompositeEligibilityBinding(
                original_binding=binding, composite_sha256=model_sha256(identity)
            )
        )
    return tuple(result)


def private_eligibility_template() -> dict[str, str | None]:
    """Blank private future schema, without any recorded person or attestation."""
    fields = (
        "role",
        "private_person_token",
        "private_name_and_contact",
        "exposure_history",
        "distinct_human_confirmed",
        "machine_answers_seen",
        "parser_predictions_seen",
        "machine_prefill_seen",
        "other_submission_seen",
        "partition_labels_received",
        "held_out_labels_seen",
        "model_as_annotator",
        "run_id",
        "package_id",
        "manifest_sha256",
        "reference_aggregate_sha256",
        "runtime_sha256",
        "view_sha256",
        "composite_sha256",
        "contract_sha256",
        "attested_at",
    )
    return {"kind": "BLANK_PRIVATE_ELIGIBILITY_TEMPLATE", **dict.fromkeys(fields)}


class AccessReceipt(StrictModel):
    kind: Literal["REAL_ACCOUNT_ACCESS_TEST", "SYNTHETIC_ACCESS_REHEARSAL"]
    check_id: str
    composite_pair_sha256: Sha256
    status: Literal["NOT RUN", "PASS", "FAIL"] = "NOT RUN"

    @model_validator(mode="after")
    def no_real_test_claim(self) -> Self:
        if self.check_id not in ACCESS_CHECKS:
            raise ValueError("unknown access actor/operation/resource/outcome route")
        if self.kind == "REAL_ACCOUNT_ACCESS_TEST" and self.status != "NOT RUN":
            raise ValueError("real-account tests remain NOT RUN in this draft")
        return self


def real_access_test_template(identities: Sequence[LaunchIdentity]) -> tuple[AccessReceipt, ...]:
    """Unperformed future real-account checks, containing no account identities."""
    digest = pair_sha256(identities)
    return tuple(
        AccessReceipt(kind="REAL_ACCOUNT_ACCESS_TEST", check_id=check, composite_pair_sha256=digest)
        for check in ACCESS_CHECKS
    )


class CeremonyEvidence(StrictModel):
    kind: Literal["SYNTHETIC_CEREMONY_REHEARSAL"] = "SYNTHETIC_CEREMONY_REHEARSAL"
    composite_pair_sha256: Sha256
    steps: tuple[str, ...] = ()


class RehearsalResult(StrictModel):
    status: Literal["SYNTHETIC_REHEARSAL_ONLY"] = "SYNTHETIC_REHEARSAL_ONLY"
    prerequisites_satisfied: bool
    failures: tuple[str, ...]
    annotation_launch_approved: Literal[False] = False
    production_locking_enabled: Literal[False] = False


def production_launch_preflight() -> None:
    raise ValueError("production launch remains unapproved; this draft cannot grant authority")


def synthetic_launch_preflight(
    *,
    candidate: LaunchCandidate,
    expected_candidate_sha256: str,
    identities: Sequence[LaunchIdentity],
    people: Sequence[EligibilityAttestation],
    packages: Sequence[Mapping[str, bytes]],
    bindings: Sequence[CompositeEligibilityBinding],
    receipts: Sequence[PackageIssuanceReceipt],
    runtime_receipts: Sequence[bytes],
    runtime_receipt_sha256s: Sequence[str],
    access: Sequence[AccessReceipt],
    ceremony: CeremonyEvidence,
) -> RehearsalResult:
    """Evaluate invented assertions only. No result proves identity or real access."""
    failures: list[str] = []
    try:
        verify_candidate(candidate, expected_candidate_sha256, identities)
        pair_digest = pair_sha256(identities)
        if any(i.original.run_id != "synthetic-run" for i in identities):
            raise ValueError("rehearsal accepts synthetic packages only")
        if tuple(package_identity(files) for files in packages) != tuple(
            i.original for i in identities
        ):
            raise ValueError("package bytes differ from composite identity")
    except ValueError:
        return RehearsalResult(
            prerequisites_satisfied=False, failures=("candidate_or_composite_custody_failed",)
        )
    try:
        checked = tuple(
            CompositeEligibilityBinding.model_validate_json(b.model_dump_json()) for b in bindings
        )
        expected = bind_synthetic_eligibility(
            people,
            packages,
            identities,
            model_as_annotator=tuple(b.model_as_annotator for b in checked),
            held_out_labels_seen=tuple(b.held_out_labels_seen for b in checked),
        )
        if checked != expected:
            raise ValueError("composite eligibility binding changed")
        verify_issuance_pair(people, packages, tuple(b.original_binding for b in checked), receipts)
    except ValueError:
        failures.append("private_eligibility_or_exact_binding_failed")
    try:
        if len(runtime_receipts) != 2 or len(runtime_receipt_sha256s) != 2:
            raise ValueError("runtime rehearsal receipt pair missing")
        for identity, raw, pin in zip(
            identities, runtime_receipts, runtime_receipt_sha256s, strict=True
        ):
            expected_receipt = {
                "kind": "UNISSUED_RUNTIME_REHEARSAL",
                "runtime_sha256": identity.runtime_sha256,
                "dependency_sha256": identity.dependency_sha256,
                "launcher_sha256": identity.launcher_sha256,
                "interpreter_sha256": identity.interpreter_sha256,
                "view_sha256": identity.view_sha256,
                "original_package_sha256": identity.original.manifest_sha256,
                "contract_sha256": identity.runtime_contract_sha256,
                "role": identity.original.role,
                "run_id": identity.original.run_id,
            }
            if sha256(raw) != pin or json.loads(raw) != expected_receipt:
                raise ValueError("runtime rehearsal receipt differs from trusted bytes/identity")
    except ValueError:
        failures.append("runtime_rehearsal_receipt_custody_failed")
    try:
        checks = tuple(AccessReceipt.model_validate_json(a.model_dump_json()) for a in access)
        if (
            len(checks) != len(ACCESS_CHECKS)
            or {a.check_id for a in checks} != set(ACCESS_CHECKS)
            or any(
                a.kind != "SYNTHETIC_ACCESS_REHEARSAL"
                or a.status != "PASS"
                or a.composite_pair_sha256 != pair_digest
                for a in checks
            )
        ):
            raise ValueError("access checks incomplete or failed")
    except ValueError:
        failures.append("access_checks_incomplete_or_failed")
    try:
        ceremony = CeremonyEvidence.model_validate_json(ceremony.model_dump_json())
        if ceremony.composite_pair_sha256 != pair_digest or ceremony.steps != CEREMONY_STEPS:
            raise ValueError("ceremony incomplete or out of order")
    except ValueError:
        failures.append("ceremony_incomplete_or_out_of_order")
    return RehearsalResult(prerequisites_satisfied=not failures, failures=tuple(failures))
