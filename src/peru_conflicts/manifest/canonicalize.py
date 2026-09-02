"""Owner-bound M1 manifest canonicalization with preview and write-once publication."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypedDict, cast

from peru_conflicts.acquisition.fs_safety import (
    DirectoryLease,
    DirectoryLeaseError,
    rename_between_directories_no_replace,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.manifest.models import (
    ArtifactFingerprint,
    ByteVersionRecord,
    CorpusReportManifestEntry,
    CoverageReport,
    GapRegisterEntry,
    MaterializationReceipt,
    SourceObservationRecord,
    VersionSourceRelationshipEdge,
)
from peru_conflicts.manifest.reviewed_models import (
    AdjudicationOutcome,
    ApprovalFingerprint,
    CanonicalizationReceipt,
    CoverageAccountingStatus,
    DeferredAcquisitionPolicy,
    HumanReviewStatus,
    ManifestAdjudicationRecord,
    OwnerApprovalArtifact,
    ReviewedCoverageReport,
)
from peru_conflicts.models.common import StrictModel
from peru_conflicts.paths import DataPathError, DataPaths

CANONICAL_TARGET_RELATIVE = PurePosixPath("06_validation/m1_corpus_manifest/v0.2.0")
CANONICAL_RECEIPT_NAME = "canonicalization_receipt.json"
CANONICAL_LOCK_NAME = ".m1-04c1-v020.lock"

CANDIDATE_TO_CANONICAL = {
    "corpus_manifest_candidate.jsonl": "corpus_manifest_v011.jsonl",
    "source_observations_candidate.jsonl": "source_observations_v011.jsonl",
    "byte_versions_candidate.jsonl": "byte_versions_v011.jsonl",
    "version_edges_candidate.jsonl": "version_edges_v011.jsonl",
    "gap_register_candidate.jsonl": "gap_register_v011.jsonl",
    "coverage_report_candidate.json": "candidate_coverage_v011.json",
}


class CanonicalizationError(RuntimeError):
    """Reviewed canonicalization input, target, or publication is unsafe."""


Validator = Callable[[bytes], bool]


class _ProposedAdjudicationRow(TypedDict):
    review_unit_id: str
    proposed_outcome: str
    owner_approval_required: bool
    owner_decision: object | None
    creates_new_report_identity: bool
    creates_new_month_mapping: bool
    asserts_new_byte_identity: bool
    preserves_all_source_observations: bool
    current_gap_ids: list[str]
    related_manifest_ids: list[str]
    related_source_observation_ids: list[str]
    evidence_references: list[str]
    rationale: str


@dataclass(frozen=True, slots=True)
class CanonicalPackage:
    """Completely rendered and validated canonical bytes, ready for preview or write."""

    rendered_files: Mapping[str, bytes]
    record_counts: Mapping[str, int]
    validators: Mapping[str, Validator]
    receipt: CanonicalizationReceipt
    receipt_bytes: bytes


def _canonical_json_line(model: StrictModel) -> bytes:
    return canonical_json_bytes(model.model_dump(mode="json")) + b"\n"


def _fingerprint(
    filename: str,
    raw: bytes,
    *,
    record_count: int,
    role: str = "canonical_output",
) -> ArtifactFingerprint:
    return ArtifactFingerprint(
        artifact_role=f"{role}:{filename}",
        path=filename,
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        record_count=record_count,
    )


def _validate_canonical_model(raw: bytes, model: type[StrictModel]) -> bool:
    parsed = model.model_validate_json(raw)
    return _canonical_json_line(parsed) == raw


def _validate_canonical_jsonl(raw: bytes, model: type[StrictModel]) -> bool:
    if not raw or not raw.endswith(b"\n"):
        return False
    return all(
        _canonical_json_line(model.model_validate_json(line)) == line + b"\n"
        for line in raw.splitlines()
    )


def _validate_exact(raw: bytes, expected: bytes) -> bool:
    return raw == expected


def _validate_canonical_json_bytes(raw: bytes) -> bool:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return canonical_json_bytes(parsed) + b"\n" == raw


def _verify_fingerprint(path: Path, expected: ApprovalFingerprint | ArtifactFingerprint) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CanonicalizationError(f"approved input is unavailable: {expected.path}") from error
    if len(raw) != expected.bytes or hashlib.sha256(raw).hexdigest() != expected.sha256:
        raise CanonicalizationError(f"approved input fingerprint mismatch: {expected.path}")
    return raw


def verify_owner_approval_sources(
    approval: OwnerApprovalArtifact,
    *,
    repository_root: Path,
    candidate_dir: Path,
) -> tuple[bytes, tuple[_ProposedAdjudicationRow, ...]]:
    """Verify every owner-bound source and return the exact proposed decisions."""

    root = repository_root.resolve()
    candidate = candidate_dir.resolve()
    for fingerprint in approval.candidate_fingerprints:
        _verify_fingerprint(candidate / fingerprint.path, fingerprint)
    _verify_fingerprint(
        candidate / "materialization_receipt.json",
        approval.post_merge_materialization_receipt,
    )

    for fingerprint in approval.review_input_fingerprints.values():
        source = root / Path(fingerprint.path)
        _verify_fingerprint(source, fingerprint)

    proposed_fingerprint = approval.review_input_fingerprints["proposed_adjudications"]
    proposed_raw = _verify_fingerprint(root / Path(proposed_fingerprint.path), proposed_fingerprint)
    try:
        rows = tuple(
            cast(_ProposedAdjudicationRow, json.loads(line)) for line in proposed_raw.splitlines()
        )
    except (TypeError, ValueError) as error:
        raise CanonicalizationError("approved adjudication source is not valid JSONL") from error
    approved = {
        item.review_unit_id: item.approved_outcome.value for item in approval.approved_decisions
    }
    proposed = {row.get("review_unit_id"): row.get("proposed_outcome") for row in rows}
    if len(rows) != 50 or len(proposed) != 50 or proposed != approved:
        raise CanonicalizationError("approved decision queue does not match proposed bytes")
    if any(
        row.get("owner_approval_required") is not True
        or row.get("owner_decision") is not None
        or row.get("creates_new_report_identity") is not False
        or row.get("creates_new_month_mapping") is not False
        or row.get("asserts_new_byte_identity") is not False
        or row.get("preserves_all_source_observations") is not True
        for row in rows
    ):
        raise CanonicalizationError("approved decisions would strengthen or drop source evidence")

    packet_fingerprint = approval.review_input_fingerprints["owner_decision_packet"]
    packet_raw = _verify_fingerprint(root / Path(packet_fingerprint.path), packet_fingerprint)
    packet = json.loads(packet_raw)
    if (
        packet.get("owner_approval_required") is not True
        or packet.get("owner_approved") is not False
        or packet.get("approved_at") is not None
    ):
        raise CanonicalizationError("owner packet preapproval state does not match reviewed bytes")
    return proposed_raw, rows


def _adjudication_id(review_unit_id: str) -> str:
    digest = hashlib.sha256(review_unit_id.encode("utf-8")).hexdigest()[:24]
    return f"manifest-adjudication-{digest}"


def _historical_months() -> tuple[str, ...]:
    return tuple(
        f"{year:04d}-{month:02d}"
        for year, start, stop in ((2004, 4, 13), (2005, 1, 13))
        for month in range(start, stop)
    )


def _validate_coverage_language(claims: tuple[str, ...]) -> None:
    unsafe = (
        "complete official pdf corpus",
        "complete pdf byte corpus",
        "full pdf corpus",
        "authoritative byte corpus is complete",
    )
    normalized = "\n".join(claims).casefold()
    if any(phrase in normalized for phrase in unsafe):
        raise CanonicalizationError("approved coverage claim implies complete PDF acquisition")


def build_reviewed_package(
    *,
    repository_root: Path,
    candidate_dir: Path,
    owner_approval_path: Path,
    execution_commit: str,
    implementation_tree_sha: str,
) -> CanonicalPackage:
    """Build exact canonical bytes from frozen v0.1.1 evidence and owner approval."""

    root = repository_root.resolve()
    approval_raw = owner_approval_path.read_bytes()
    approval = OwnerApprovalArtifact.model_validate_json(approval_raw)
    if not _validate_canonical_json_bytes(approval_raw):
        raise CanonicalizationError("owner approval is not canonical JSON plus LF")
    proposed_raw, rows = verify_owner_approval_sources(
        approval,
        repository_root=root,
        candidate_dir=candidate_dir,
    )
    approval_sha = hashlib.sha256(approval_raw).hexdigest()
    proposed_sha = hashlib.sha256(proposed_raw).hexdigest()

    old_models: dict[str, type[StrictModel]] = {
        "corpus_manifest_candidate.jsonl": CorpusReportManifestEntry,
        "source_observations_candidate.jsonl": SourceObservationRecord,
        "byte_versions_candidate.jsonl": ByteVersionRecord,
        "version_edges_candidate.jsonl": VersionSourceRelationshipEdge,
        "gap_register_candidate.jsonl": GapRegisterEntry,
        "coverage_report_candidate.json": CoverageReport,
    }
    candidate_raw: dict[str, bytes] = {}
    candidate_objects: dict[str, tuple[StrictModel, ...] | StrictModel] = {}
    for source_name, model in old_models.items():
        raw = (candidate_dir / source_name).read_bytes()
        candidate_raw[source_name] = raw
        if source_name.endswith(".jsonl"):
            parsed = tuple(model.model_validate_json(line) for line in raw.splitlines())
            if not _validate_canonical_jsonl(raw, model):
                raise CanonicalizationError(f"candidate evidence is not canonical: {source_name}")
        else:
            parsed = model.model_validate_json(raw)
            if not _validate_canonical_model(raw, model):
                raise CanonicalizationError(f"candidate evidence is not canonical: {source_name}")
        candidate_objects[source_name] = parsed

    manifests = candidate_objects["corpus_manifest_candidate.jsonl"]
    observations = candidate_objects["source_observations_candidate.jsonl"]
    byte_versions = candidate_objects["byte_versions_candidate.jsonl"]
    edges = candidate_objects["version_edges_candidate.jsonl"]
    gaps = candidate_objects["gap_register_candidate.jsonl"]
    coverage = candidate_objects["coverage_report_candidate.json"]
    if not isinstance(coverage, CoverageReport):
        raise CanonicalizationError("candidate coverage has the wrong model")

    manifest_ids = {item.manifest_report_id for item in manifests}  # type: ignore[union-attr]
    observation_ids = {item.source_observation_record_id for item in observations}  # type: ignore[union-attr]
    gap_ids = {item.gap_id for item in gaps}  # type: ignore[union-attr]
    if len(manifests) != 247 or len(observations) != 1989 or len(gaps) != 287:  # type: ignore[arg-type]
        raise CanonicalizationError("candidate evidence record counts changed")
    if len(byte_versions) != 10 or len(edges) != 993:  # type: ignore[arg-type]
        raise CanonicalizationError("candidate byte/version evidence counts changed")

    adjudications: list[ManifestAdjudicationRecord] = []
    for row in rows:
        related_gap_ids = tuple(row.get("current_gap_ids", ()))
        related_manifest_ids = tuple(row.get("related_manifest_ids", ()))
        evidence_refs = tuple(row.get("evidence_references", ()))
        if any(item not in gap_ids for item in related_gap_ids):
            raise CanonicalizationError("adjudication has an unknown gap reference")
        if any(item not in manifest_ids for item in related_manifest_ids):
            raise CanonicalizationError("adjudication has an unknown manifest reference")
        related_observations = tuple(row.get("related_source_observation_ids", ()))
        if any(item not in observation_ids for item in related_observations):
            raise CanonicalizationError("adjudication has an unknown observation reference")
        if not evidence_refs or not set(
            related_gap_ids + related_manifest_ids + related_observations
        ).issubset(set(evidence_refs)):
            raise CanonicalizationError("adjudication evidence references are incomplete")
        adjudications.append(
            ManifestAdjudicationRecord(
                adjudication_id=_adjudication_id(str(row["review_unit_id"])),
                source_review_unit_id=row["review_unit_id"],
                related_gap_ids=related_gap_ids,
                related_manifest_ids=related_manifest_ids,
                proposed_adjudications_sha256=proposed_sha,
                approved_outcome=AdjudicationOutcome(row["proposed_outcome"]),
                approved_by=approval.approved_by,
                owner_approval_id=approval.approval_id,
                owner_approval_sha256=approval_sha,
                evidence_refs=evidence_refs,
                identity_changes=False,
                month_mapping_changes=False,
                byte_assertion_changes=False,
                unresolved_evidence_retained=True,
                decision_rationale=row["rationale"],
                decided_at=approval.approved_at,
            )
        )
    if len({item.adjudication_id for item in adjudications}) != 50:
        raise CanonicalizationError("adjudication IDs are not unique")

    policy = DeferredAcquisitionPolicy(
        policy_id="m1-deferred-byte-acquisition-23-259-v1",
        report_numbers=tuple(range(23, 260)),
        deferred_report_count=237,
        report_identities_observed=True,
        authoritative_bytes_acquired=False,
        authoritative_byte_corpus_complete=False,
        future_evidence_classification="useful_but_deferred",
        owner_approval_id=approval.approval_id,
        owner_approval_sha256=approval_sha,
    )
    claims = approval.approved_permissible_coverage_statement
    _validate_coverage_language(claims)
    reviewed_coverage = ReviewedCoverageReport(
        research_coverage_start="2004-04",
        observation_cutoff="2026-07",
        observed_numbered_report_min=23,
        observed_numbered_report_max=269,
        observed_numbered_report_count=247,
        observed_reference_month_min="2006-01",
        observed_reference_month_max="2026-07",
        observed_reference_month_count=247,
        report_to_month_conflict_count=0,
        month_to_report_conflict_count=0,
        human_review_status=HumanReviewStatus.OWNER_APPROVED,
        owner_approved_decision_count=50,
        approved_outcome_counts=approval.approved_outcome_counts,
        coverage_accounting_status=CoverageAccountingStatus.REVIEWED_WITH_EXPLICIT_LIMITATIONS,
        factual_gap_count=287,
        unresolved_evidence_retained=True,
        deferred_byte_acquisition_count=237,
        byte_verified_report_count=10,
        authoritative_byte_corpus_complete=False,
        reports_1_22_status="unobserved_report_number_hypotheses",
        unresolved_historical_months=_historical_months(),
        historical_unnumbered_lead_years=(2004, 2005),
        byte_unknown_report_numbers=(69, 153, 169),
        opaque_association_report_numbers=(261, 263),
        approved_coverage_claims=claims,
        prohibited_overclaims=approval.prohibited_overclaims,
        owner_approval_id=approval.approval_id,
        owner_approval_sha256=approval_sha,
    )

    rendered: dict[str, bytes] = {
        target: candidate_raw[source] for source, target in CANDIDATE_TO_CANONICAL.items()
    }
    adjudication_raw = b"".join(
        _canonical_json_line(item)
        for item in sorted(adjudications, key=lambda item: item.adjudication_id)
    )
    rendered.update(
        {
            "manifest_adjudications_v020.jsonl": adjudication_raw,
            "deferred_acquisition_policy_v020.json": _canonical_json_line(policy),
            "reviewed_coverage_v020.json": _canonical_json_line(reviewed_coverage),
            "owner_approval.json": approval_raw,
        }
    )
    record_counts = {
        "corpus_manifest_v011.jsonl": 247,
        "source_observations_v011.jsonl": 1989,
        "byte_versions_v011.jsonl": 10,
        "version_edges_v011.jsonl": 993,
        "gap_register_v011.jsonl": 287,
        "candidate_coverage_v011.json": 1,
        "manifest_adjudications_v020.jsonl": 50,
        "deferred_acquisition_policy_v020.json": 1,
        "reviewed_coverage_v020.json": 1,
        "owner_approval.json": 1,
    }
    validators: dict[str, Validator] = {
        target: (lambda raw, expected=candidate_raw[source]: _validate_exact(raw, expected))
        for source, target in CANDIDATE_TO_CANONICAL.items()
    }
    validators.update(
        {
            "manifest_adjudications_v020.jsonl": lambda raw: _validate_canonical_jsonl(
                raw, ManifestAdjudicationRecord
            ),
            "deferred_acquisition_policy_v020.json": lambda raw: _validate_canonical_model(
                raw, DeferredAcquisitionPolicy
            ),
            "reviewed_coverage_v020.json": lambda raw: _validate_canonical_model(
                raw, ReviewedCoverageReport
            ),
            "owner_approval.json": lambda raw: (
                _validate_exact(raw, approval_raw)
                and _validate_canonical_json_bytes(raw)
                and bool(OwnerApprovalArtifact.model_validate_json(raw))
            ),
        }
    )

    candidate_receipt = MaterializationReceipt.model_validate_json(
        (candidate_dir / "materialization_receipt.json").read_bytes()
    )
    output_fingerprints = tuple(
        _fingerprint(name, raw, record_count=record_counts[name])
        for name, raw in sorted(rendered.items())
    )
    adjudication_fingerprint = next(
        item for item in output_fingerprints if item.path == "manifest_adjudications_v020.jsonl"
    )
    owner_approval_fingerprint = ApprovalFingerprint(
        path="owner_approval.json",
        bytes=len(approval_raw),
        sha256=approval_sha,
        record_count=1,
    )
    review_inputs = tuple(
        approval.review_input_fingerprints[name]
        for name in sorted(approval.review_input_fingerprints)
    )
    receipt = CanonicalizationReceipt(
        task_id="M1-04C.1",
        execution_commit=execution_commit,
        implementation_tree_sha=implementation_tree_sha,
        manifest_schema_version="0.2.0",
        canonical_target_relative_path="06_validation/m1_corpus_manifest/v0.2.0",
        candidate_input_artifacts=approval.candidate_fingerprints,
        review_input_artifacts=review_inputs,
        discovery_input_artifacts=candidate_receipt.input_artifacts,
        operational_input_artifacts=candidate_receipt.operational_artifacts,
        owner_approval_artifact=owner_approval_fingerprint,
        proposed_adjudications_artifact=approval.review_input_fingerprints[
            "proposed_adjudications"
        ],
        adjudication_records_artifact=adjudication_fingerprint,
        output_artifacts=output_fingerprints,
        record_counts=tuple(sorted(record_counts.items())),
        unresolved_gap_counts=tuple(
            (classification.value, count) for classification, count in candidate_receipt.gap_counts
        ),
        deferred_acquisition_count=237,
        byte_verified_count=10,
        authoritative_byte_corpus_complete=False,
        approved_coverage_claims=claims,
        deterministic_sort_rules=(
            "v0.1.1-evidence:byte_preserved",
            "adjudications:adjudication_id",
            "json:canonical_utf8_lf",
            "receipt:last",
        ),
        no_network_assertion=True,
        no_raw_write_assertion=True,
        write_once_no_overwrite=True,
        receipt_written_last=True,
    )
    receipt_raw = _canonical_json_line(receipt)
    package = CanonicalPackage(
        rendered_files=rendered,
        record_counts=record_counts,
        validators=validators,
        receipt=receipt,
        receipt_bytes=receipt_raw,
    )
    _verify_package(package)
    return package


def _verify_package(package: CanonicalPackage) -> None:
    if set(package.rendered_files) != set(package.validators) or set(package.rendered_files) != set(
        package.record_counts
    ):
        raise CanonicalizationError("canonical package file registry is incomplete")
    expected = {item.path: item for item in package.receipt.output_artifacts}
    if set(expected) != set(package.rendered_files):
        raise CanonicalizationError("receipt output registry does not match package")
    for name, raw in package.rendered_files.items():
        if package.validators[name](raw) is not True:
            raise CanonicalizationError(f"canonical output validation failed: {name}")
        fingerprint = expected[name]
        if (
            len(raw) != fingerprint.bytes
            or hashlib.sha256(raw).hexdigest() != fingerprint.sha256
            or package.record_counts[name] != fingerprint.record_count
        ):
            raise CanonicalizationError(f"canonical output fingerprint mismatch: {name}")
    parsed = CanonicalizationReceipt.model_validate_json(package.receipt_bytes)
    if parsed != package.receipt or _canonical_json_line(parsed) != package.receipt_bytes:
        raise CanonicalizationError("canonicalization receipt failed canonical roundtrip")


def require_new_canonical_target(data_paths: DataPaths, requested_target: Path) -> Path:
    """Require the one fixed derived target and refuse any existing destination."""

    expected = data_paths.validation / "m1_corpus_manifest" / "v0.2.0"
    try:
        safe = data_paths.require_writable(requested_target)
    except DataPathError as error:
        raise CanonicalizationError(
            "canonical target is outside the fixed writable namespace"
        ) from error
    if safe != expected.resolve():
        raise CanonicalizationError("canonical writer accepts only the fixed v0.2.0 target")
    if safe.exists():
        raise CanonicalizationError("canonical target already exists")
    return safe


def _write_file_fsync(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _verify_directory(package: CanonicalPackage, directory: Path) -> None:
    expected_names = set(package.rendered_files) | {CANONICAL_RECEIPT_NAME}
    if {path.name for path in directory.iterdir()} != expected_names:
        raise CanonicalizationError("written canonical package file set is incomplete")
    for name, raw in package.rendered_files.items():
        written = (directory / name).read_bytes()
        if written != raw or package.validators[name](written) is not True:
            raise CanonicalizationError(f"written canonical output verification failed: {name}")
    receipt_raw = (directory / CANONICAL_RECEIPT_NAME).read_bytes()
    if receipt_raw != package.receipt_bytes:
        raise CanonicalizationError("written canonicalization receipt differs")
    parsed = CanonicalizationReceipt.model_validate_json(receipt_raw)
    if _canonical_json_line(parsed) != receipt_raw:
        raise CanonicalizationError("written canonicalization receipt is not canonical")


def materialize_canonical_preview(
    package: CanonicalPackage,
    *,
    output_dir: Path,
    repository_root: Path,
) -> Path:
    """Write the same canonical bytes beneath ignored cache, never external storage."""

    _verify_package(package)
    root = repository_root.resolve()
    cache = root / ".cache"
    output = output_dir.resolve()
    if not output.is_relative_to(cache) or output == cache:
        raise CanonicalizationError("canonical preview must be beneath ignored repository cache")
    if output.exists():
        raise CanonicalizationError("canonical preview target already exists")
    output.mkdir(parents=True)
    for name in sorted(package.rendered_files):
        _write_file_fsync(output / name, package.rendered_files[name])
    _write_file_fsync(output / CANONICAL_RECEIPT_NAME, package.receipt_bytes)
    _verify_directory(package, output)
    return output


def write_canonical_package(
    package: CanonicalPackage,
    *,
    data_paths: DataPaths,
    requested_target: Path | None = None,
) -> Path:
    """Publish once to the fixed validation namespace using no-replace promotion."""

    _verify_package(package)
    target = require_new_canonical_target(
        data_paths,
        requested_target
        if requested_target is not None
        else data_paths.validation / "m1_corpus_manifest" / "v0.2.0",
    )
    package_parent = target.parent
    try:
        package_parent.mkdir(parents=True, exist_ok=True)
        with DirectoryLease.acquire(package_parent) as parent:
            lock = parent.open_child_exclusive(CANONICAL_LOCK_NAME)
            try:
                lock.write(b"1")
                lock.flush()
                os.fsync(lock.fileno())
                if parent.child_exists(target.name):
                    raise CanonicalizationError("canonical target already exists")
                temporary = Path(tempfile.mkdtemp(prefix=".m1-04c1-v020-", dir=package_parent))
                for name in sorted(package.rendered_files):
                    _write_file_fsync(temporary / name, package.rendered_files[name])
                _write_file_fsync(temporary / CANONICAL_RECEIPT_NAME, package.receipt_bytes)
                _verify_directory(package, temporary)
                if os.name == "nt":
                    # Windows rename is no-replace; the retained parent lease and
                    # exclusive lock close the in-process race window.
                    temporary.rename(target)
                else:
                    rename_between_directories_no_replace(
                        parent,
                        temporary.name,
                        parent,
                        target.name,
                    )
            except CanonicalizationError:
                raise
            except BaseException as error:
                raise CanonicalizationError(
                    "canonical package promotion failed; partial evidence was retained"
                ) from error
            finally:
                lock.close()
                parent.unlink_child(CANONICAL_LOCK_NAME, missing_ok=True)
    except CanonicalizationError:
        raise
    except (DirectoryLeaseError, OSError) as error:
        raise CanonicalizationError(
            "canonical writer could not bind its fixed namespace"
        ) from error
    _verify_directory(package, target)
    return target
