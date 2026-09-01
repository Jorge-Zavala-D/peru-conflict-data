"""Read-only loading and validation of frozen M1 evidence."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableByteObjectV2,
    DurableCleanupV2,
    DurableComparisonV2,
    DurableIssueV2,
    DurableLandingAssociationV2,
    DurableRunOpenedV2,
    DurableRunTerminalV2,
    DurableSourceRehashV2,
    StorageNamespaceMarkerV2,
    UseIndexClaimV2,
    UseIndexLedgerAnchorV2,
    UseIndexLedgerCreatedV2,
    UseIndexTerminalV2,
    marker_bytes,
)
from peru_conflicts.acquisition.persistent_ledger import (
    _INDEX_ADAPTER,  # pyright: ignore[reportPrivateUsage]
    _LEDGER_ADAPTER,  # pyright: ignore[reportPrivateUsage]
    _parse_chain,  # pyright: ignore[reportPrivateUsage]
    validate_durable_ledger_graph,
)
from peru_conflicts.acquisition.plan import (
    REVIEWED_V2_PLAN_FILE_SHA256,
    load_reviewed_pilot_plan,
)
from peru_conflicts.discovery.models import ProvisionalDiscoveryRecord
from peru_conflicts.discovery.receipts import ReconnaissanceSummary, RequestAttemptReceipt
from peru_conflicts.manifest.models import ArtifactFingerprint


class EvidenceError(RuntimeError):
    """Frozen discovery or acquisition evidence is absent, changed, or inconsistent."""


@dataclass(frozen=True, slots=True)
class DiscoveryArtifactExpectation:
    """Reviewed byte contract for one discovery-run artifact."""

    filename: str
    bytes: int
    sha256: str
    line_count: int | None = None


@dataclass(frozen=True, slots=True)
class ReviewedDiscoveryRun:
    """Reviewed run identity and complete artifact fingerprint set."""

    run_id: str
    artifacts: tuple[DiscoveryArtifactExpectation, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryRunInput:
    """Caller-supplied location for one reviewed frozen run."""

    run_id: str
    directory: Path


@dataclass(frozen=True, slots=True)
class DiscoveryOccurrence:
    """One record occurrence qualified by capture run and source line."""

    run_id: str
    source_line: int
    record: ProvisionalDiscoveryRecord


@dataclass(frozen=True, slots=True)
class DiscoveryEvidence:
    """Validated and deterministically ordered frozen discovery evidence."""

    occurrences: tuple[DiscoveryOccurrence, ...]
    artifact_fingerprints: tuple[ArtifactFingerprint, ...]


@dataclass(frozen=True, slots=True)
class ProtectedByteEvidence:
    """One expected protected raw report object."""

    report_number: int
    relative_path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CompletedReportEvidence:
    """One completed compare-only report outcome from the durable ledger."""

    report_number: int
    landing_url: str
    direct_url: str
    protected: ProtectedByteEvidence
    association_status: str
    acquisition_evidence_ids: tuple[str, ...]
    remote_observation_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AcquisitionClosure:
    """Read-only, fully validated M1-03B.2 durable evidence closure."""

    authorization_id: str
    run_id: str
    terminal_status: str
    terminal_reason: str
    authorization_spent: bool
    reports: tuple[CompletedReportEvidence, ...]
    protected_bytes: tuple[ProtectedByteEvidence, ...]
    operational_fingerprints: tuple[ArtifactFingerprint, ...]


@dataclass(frozen=True, slots=True)
class DataRootSnapshot:
    """Read-only inventory proof for the completed M1 research-data root."""

    directory_count: int
    file_count: int
    total_bytes: int
    protected_source_count: int
    derived_file_count: int


COMPLETED_AUTHORIZATION_ID = "m1-03b2-reports-260-269-compare-v2"
COMPLETED_RUN_ID = "m103b-1dff6ef0b40dec88e4382932a8c5cf48"
COMPLETED_LEDGER_NAME = "authorization-1dff6ef0b40dec88e4382932a8c5cf48.v2.jsonl"
COMPLETED_OPERATIONAL_ARTIFACTS: Mapping[str, tuple[int, str, int | None]] = {
    "m1-03b-namespace-v2.json": (
        167,
        "91e25b85356693c5b2502a0f420354fdf73be7f4336c0366c6d69ea99a0a2f49",
        None,
    ),
    "authorization-use-index-v2.jsonl": (
        54_535,
        "cbf5999c2a0011583d05e1d833815f1fc739a6fa0584b7c77ef638d3225e94a5",
        127,
    ),
    COMPLETED_LEDGER_NAME: (
        95_867,
        "a39d0b64462a7e5a9f956874462faa5403278abe0e988e7ea95498098c2d50b0",
        124,
    ),
    ".m1-03b-v2.lock": (
        1,
        "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
        None,
    ),
}

REVIEWED_DISCOVERY_RUNS: Mapping[str, ReviewedDiscoveryRun] = {
    "reconnaissance-24df69cdc9ef9156": ReviewedDiscoveryRun(
        run_id="reconnaissance-24df69cdc9ef9156",
        artifacts=(
            DiscoveryArtifactExpectation(
                "records.jsonl",
                1_970_685,
                "dd3d4e71245e0d7e94459f7b318fa5245cb731b05cc57ad5f98cfa9ecf52d5de",
                746,
            ),
            DiscoveryArtifactExpectation(
                "requests.jsonl",
                163_939,
                "9b5aab045a81808f462655b907c59f90f9b0d86ffb45ef73271f3b80b044772f",
                166,
            ),
            DiscoveryArtifactExpectation(
                "summary.json",
                14_597,
                "27aebe5abbbc62c3f644c619c84c0914dc55497f89749da45337daa74b9dead1",
            ),
        ),
    ),
    "reconnaissance-155898df773d1808": ReviewedDiscoveryRun(
        run_id="reconnaissance-155898df773d1808",
        artifacts=(
            DiscoveryArtifactExpectation(
                "records.jsonl",
                692_970,
                "c05afd73f85986a281c5fad1b38ac0ab00e7ea7da0d7836644bb89515484ac6e",
                249,
            ),
            DiscoveryArtifactExpectation(
                "requests.jsonl",
                2_964,
                "e5a325c59f91fc6156bc7f5f64cd7bab938f0961a3fa00ba77258464843f370a",
                3,
            ),
            DiscoveryArtifactExpectation(
                "summary.json",
                1_758,
                "22e2464616c67989881fbeec0d4a1975c13b65dec1b3e1cfba346b93e6024474",
            ),
        ),
    ),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _portable_path(path: Path, repository_root: Path) -> str:
    resolved = path.resolve()
    root = repository_root.resolve()
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return path.as_posix()


def _validate_artifact(
    directory: Path,
    expectation: DiscoveryArtifactExpectation,
    *,
    repository_root: Path,
    run_id: str,
) -> tuple[bytes, ArtifactFingerprint]:
    path = directory / expectation.filename
    if not path.is_file():
        raise EvidenceError(f"missing frozen discovery artifact: {path}")
    raw = path.read_bytes()
    digest = _sha256(raw)
    lines = len(raw.splitlines())
    if (
        len(raw) != expectation.bytes
        or digest != expectation.sha256
        or (expectation.line_count is not None and lines != expectation.line_count)
    ):
        raise EvidenceError(f"frozen discovery artifact fingerprint mismatch: {path}")
    return raw, ArtifactFingerprint(
        artifact_role=f"discovery_{expectation.filename}:{run_id}",
        path=_portable_path(path, repository_root),
        bytes=len(raw),
        sha256=digest,
        record_count=(lines if expectation.line_count is not None else None),
    )


def load_discovery_runs(
    inputs: Sequence[DiscoveryRunInput],
    *,
    reviewed_runs: Mapping[str, ReviewedDiscoveryRun],
    repository_root: Path,
) -> DiscoveryEvidence:
    """Load exact reviewed discovery runs without collapsing capture occurrences."""

    supplied = [item.run_id for item in inputs]
    if len(supplied) != len(set(supplied)):
        raise EvidenceError("each reviewed discovery run may be supplied only once")
    if set(supplied) != set(reviewed_runs):
        unknown = sorted(set(supplied).difference(reviewed_runs))
        missing = sorted(set(reviewed_runs).difference(supplied))
        if unknown:
            raise EvidenceError(f"discovery run is not a reviewed frozen run: {unknown[0]}")
        raise EvidenceError(f"reviewed frozen discovery run was not supplied: {missing[0]}")

    occurrences: list[DiscoveryOccurrence] = []
    fingerprints: list[ArtifactFingerprint] = []
    for item in sorted(inputs, key=lambda value: value.run_id):
        reviewed = reviewed_runs[item.run_id]
        raw_by_name: dict[str, bytes] = {}
        for expectation in sorted(reviewed.artifacts, key=lambda value: value.filename):
            raw, fingerprint = _validate_artifact(
                item.directory,
                expectation,
                repository_root=repository_root,
                run_id=item.run_id,
            )
            raw_by_name[expectation.filename] = raw
            fingerprints.append(fingerprint)

        required = {"records.jsonl", "requests.jsonl", "summary.json"}
        if set(raw_by_name) != required:
            raise EvidenceError("reviewed discovery run must contain exactly three artifacts")
        summary = ReconnaissanceSummary.model_validate_json(raw_by_name["summary.json"])
        if summary.run_id != item.run_id:
            raise EvidenceError("discovery summary run ID differs from reviewed run ID")

        record_lines = raw_by_name["records.jsonl"].splitlines()
        request_lines = raw_by_name["requests.jsonl"].splitlines()
        if summary.records_written != len(record_lines):
            raise EvidenceError("discovery summary record count differs from records.jsonl")
        if summary.request_attempt_count != len(request_lines):
            raise EvidenceError("discovery summary request count differs from requests.jsonl")
        for line in request_lines:
            RequestAttemptReceipt.model_validate_json(line)
        for source_line, line in enumerate(record_lines, start=1):
            occurrences.append(
                DiscoveryOccurrence(
                    run_id=item.run_id,
                    source_line=source_line,
                    record=ProvisionalDiscoveryRecord.model_validate_json(line),
                )
            )

    return DiscoveryEvidence(
        occurrences=tuple(
            sorted(
                occurrences,
                key=lambda item: (
                    item.run_id,
                    item.record.discovery_record_id,
                    item.source_line,
                ),
            )
        ),
        artifact_fingerprints=tuple(
            sorted(fingerprints, key=lambda item: (item.artifact_role, item.path))
        ),
    )


def validate_protected_file_inventory(
    reports_root: Path,
    protected: Sequence[ProtectedByteEvidence],
    *,
    raw_root: Path,
) -> None:
    """Require exact protected report closure and reject unreferenced raw files."""

    expected_paths = {Path(item.relative_path).as_posix() for item in protected}
    actual_paths = {
        path.relative_to(raw_root).as_posix() for path in reports_root.rglob("*") if path.is_file()
    }
    unexpected = sorted(actual_paths.difference(expected_paths))
    missing = sorted(expected_paths.difference(actual_paths))
    if unexpected:
        raise EvidenceError(f"unexpected raw report files: {', '.join(unexpected)}")
    if missing:
        raise EvidenceError(f"protected raw report files are missing: {', '.join(missing)}")

    for item in protected:
        path = raw_root / Path(item.relative_path)
        raw = path.read_bytes()
        if len(raw) != item.bytes or _sha256(raw) != item.sha256:
            raise EvidenceError(f"protected raw report fingerprint mismatch: {item.relative_path}")


def _operational_fingerprint(
    path: Path,
    *,
    data_root: Path,
    artifact_role: str,
    expected: tuple[int, str, int | None],
) -> tuple[bytes, ArtifactFingerprint]:
    raw = path.read_bytes()
    expected_bytes, expected_sha, expected_records = expected
    if len(raw) != expected_bytes or _sha256(raw) != expected_sha:
        raise EvidenceError(f"completed operational artifact fingerprint mismatch: {path.name}")
    line_count = len(raw.splitlines()) if expected_records is not None else None
    if expected_records is not None and line_count != expected_records:
        raise EvidenceError(f"completed operational artifact record count mismatch: {path.name}")
    return raw, ArtifactFingerprint(
        artifact_role=artifact_role,
        path=path.relative_to(data_root).as_posix(),
        bytes=len(raw),
        sha256=_sha256(raw),
        record_count=line_count,
    )


def load_completed_acquisition_closure(
    *,
    repository_root: Path,
    data_root: Path,
    plan_path: Path,
) -> AcquisitionClosure:
    """Validate and load the spent M1-03B.2 evidence without opening a writer."""

    manifests = data_root / "01_raw" / "manifests"
    if not manifests.is_dir():
        raise EvidenceError("completed operational manifest directory is missing")
    actual_names = {path.name for path in manifests.iterdir() if path.is_file()}
    expected_names = set(COMPLETED_OPERATIONAL_ARTIFACTS)
    if actual_names != expected_names:
        raise EvidenceError("operational manifest file set differs from completed run closure")

    raw_by_name: dict[str, bytes] = {}
    fingerprints: list[ArtifactFingerprint] = []
    role_by_name = {
        "m1-03b-namespace-v2.json": "storage_namespace_marker",
        "authorization-use-index-v2.jsonl": "authorization_use_index",
        COMPLETED_LEDGER_NAME: "operational_ledger",
        ".m1-03b-v2.lock": "operational_writer_lock",
    }
    for name, expected in COMPLETED_OPERATIONAL_ARTIFACTS.items():
        raw, fingerprint = _operational_fingerprint(
            manifests / name,
            data_root=data_root,
            artifact_role=role_by_name[name],
            expected=expected,
        )
        raw_by_name[name] = raw
        fingerprints.append(fingerprint)

    try:
        marker = StorageNamespaceMarkerV2.model_validate_json(
            raw_by_name["m1-03b-namespace-v2.json"]
        )
    except ValueError as error:
        raise EvidenceError("completed storage marker is structurally invalid") from error
    if marker_bytes(marker) != raw_by_name["m1-03b-namespace-v2.json"]:
        raise EvidenceError("completed storage marker is not canonical")

    try:
        ledger_records, ledger_hashes = _parse_chain(
            raw_by_name[COMPLETED_LEDGER_NAME],
            adapter=_LEDGER_ADAPTER,
            sequence_field="sequence",
            previous_field="previous_record_sha256",
        )
        index_records, _ = _parse_chain(
            raw_by_name["authorization-use-index-v2.jsonl"],
            adapter=_INDEX_ADAPTER,
            sequence_field="index_sequence",
            previous_field="previous_index_sha256",
        )
        validate_durable_ledger_graph(ledger_records)
    except ValueError as error:
        raise EvidenceError("completed acquisition hash chain is invalid") from error

    ledger_counts = Counter(record.record_type for record in ledger_records)
    expected_ledger_counts = {
        "run_opened": 1,
        "attempt_started": 21,
        "attempt_finished": 21,
        "landing_association": 10,
        "byte_object": 10,
        "comparison": 10,
        "cleanup": 10,
        "source_rehash": 40,
        "run_terminal": 1,
    }
    if dict(ledger_counts) != expected_ledger_counts:
        raise EvidenceError("completed ledger record classes differ from reviewed closure")
    if any(isinstance(record, DurableIssueV2) for record in ledger_records):
        raise EvidenceError("completed ledger unexpectedly contains issue records")

    index_counts = Counter(record.record_type for record in index_records)
    if dict(index_counts) != {
        "authorization_claim": 1,
        "ledger_created": 1,
        "ledger_anchor": 124,
        "authorization_terminal": 1,
    }:
        raise EvidenceError("completed use-index record classes differ from reviewed closure")
    if not isinstance(index_records[0], UseIndexClaimV2) or not isinstance(
        index_records[1], UseIndexLedgerCreatedV2
    ):
        raise EvidenceError("completed use-index origin is invalid")
    if index_records[1].ledger_name != COMPLETED_LEDGER_NAME:
        raise EvidenceError("completed use-index ledger identity differs")
    anchors = tuple(
        record for record in index_records if isinstance(record, UseIndexLedgerAnchorV2)
    )
    if tuple(record.ledger_sequence for record in anchors) != tuple(range(1, 125)):
        raise EvidenceError("completed use-index anchors are not contiguous")
    if any(
        record.ledger_head_sha256 != ledger_hashes[record.ledger_sequence - 1] for record in anchors
    ):
        raise EvidenceError("completed use-index anchor differs from ledger hash chain")
    terminal_index = index_records[-1]
    terminal_ledger = ledger_records[-1]
    if (
        not isinstance(terminal_index, UseIndexTerminalV2)
        or not isinstance(terminal_ledger, DurableRunTerminalV2)
        or terminal_index.terminal_status != "completed"
        or terminal_index.ledger_sequence != 124
        or terminal_index.ledger_head_sha256 != ledger_hashes[-1]
        or terminal_ledger.terminal_status != "completed"
        or terminal_ledger.reason_code != "all_ten_remote_bytes_identical"
    ):
        raise EvidenceError("completed terminal evidence differs from reviewed closure")

    run_opened = ledger_records[0]
    if (
        not isinstance(run_opened, DurableRunOpenedV2)
        or run_opened.authorization_id != COMPLETED_AUTHORIZATION_ID
        or run_opened.run_id != COMPLETED_RUN_ID
        or index_records[0].authorization_id != COMPLETED_AUTHORIZATION_ID
        or index_records[0].run_id != COMPLETED_RUN_ID
    ):
        raise EvidenceError("completed authorization/run identity differs")

    loaded_plan = load_reviewed_pilot_plan(
        plan_path,
        required_sha256=REVIEWED_V2_PLAN_FILE_SHA256,
    )
    targets = {target.report_number: target for target in loaded_plan.plan.targets}
    landings = {
        record.report_number: record
        for record in ledger_records
        if isinstance(record, DurableLandingAssociationV2)
    }
    byte_objects = {
        record.report_number: record
        for record in ledger_records
        if isinstance(record, DurableByteObjectV2)
    }
    comparisons = {
        record.report_number: record
        for record in ledger_records
        if isinstance(record, DurableComparisonV2)
    }
    cleanups = {
        record.report_number: record
        for record in ledger_records
        if isinstance(record, DurableCleanupV2)
    }
    source_rehashes = tuple(
        record for record in ledger_records if isinstance(record, DurableSourceRehashV2)
    )
    starts = tuple(
        record for record in ledger_records if isinstance(record, DurableAttemptStartedV2)
    )
    finishes = tuple(
        record for record in ledger_records if isinstance(record, DurableAttemptFinishedV2)
    )
    if len(starts) != 21 or len(finishes) != 21:
        raise EvidenceError("completed request-attempt closure differs")

    protected: list[ProtectedByteEvidence] = []
    completed_reports: list[CompletedReportEvidence] = []
    for report_number in range(260, 270):
        target = targets[report_number]
        landing = landings[report_number]
        byte_object = byte_objects[report_number]
        comparison = comparisons[report_number]
        cleanup = cleanups[report_number]
        expected_association = (
            "unresolved_opaque_filename" if report_number in {261, 263} else "visibly_associated"
        )
        relevant_rehashes = tuple(
            record for record in source_rehashes if record.report_number == report_number
        )
        if (
            landing.identity_association_status != expected_association
            or byte_object.observed_sha256 != target.existing_local_sha256
            or byte_object.observed_bytes != target.existing_local_byte_count
            or comparison.relationship != "identical_bytes"
            or comparison.disposition != "identical_no_duplicate"
            or comparison.observed_sha256 != target.existing_local_sha256
            or comparison.observed_bytes != target.existing_local_byte_count
            or cleanup.cleanup_status != "removed"
            or len(relevant_rehashes) != 4
            or {record.phase for record in relevant_rehashes}
            != {"pre_network", "comparison_before", "comparison_after", "terminal"}
            or any(
                record.observed_sha256 != target.existing_local_sha256
                or record.expected_sha256 != target.existing_local_sha256
                for record in relevant_rehashes
            )
        ):
            raise EvidenceError(f"completed report evidence differs for report {report_number}")
        protected_item = ProtectedByteEvidence(
            report_number=report_number,
            relative_path=target.existing_local_relative_path,
            bytes=target.existing_local_byte_count,
            sha256=target.existing_local_sha256,
        )
        protected.append(protected_item)
        completed_reports.append(
            CompletedReportEvidence(
                report_number=report_number,
                landing_url=target.landing_page_url,
                direct_url=target.direct_download_url,
                protected=protected_item,
                association_status=expected_association,
                acquisition_evidence_ids=(
                    byte_object.record_id,
                    comparison.record_id,
                    cleanup.record_id,
                ),
                remote_observation_evidence_ids=(landing.record_id, byte_object.record_id),
            )
        )

    validate_protected_file_inventory(
        data_root / "01_raw" / "reports",
        protected,
        raw_root=data_root,
    )
    return AcquisitionClosure(
        authorization_id=COMPLETED_AUTHORIZATION_ID,
        run_id=COMPLETED_RUN_ID,
        terminal_status=terminal_ledger.terminal_status,
        terminal_reason=terminal_ledger.reason_code,
        authorization_spent=True,
        reports=tuple(completed_reports),
        protected_bytes=tuple(protected),
        operational_fingerprints=tuple(
            sorted(fingerprints, key=lambda item: (item.artifact_role, item.path))
        ),
    )


def validate_completed_data_root_snapshot(data_root: Path) -> DataRootSnapshot:
    """Require the exact post-M1-03 data-root inventory without writing it."""

    paths = tuple(data_root.rglob("*"))
    files = tuple(path for path in paths if path.is_file())
    directories = tuple(path for path in paths if path.is_dir())
    total_bytes = sum(path.stat().st_size for path in files)
    if (len(directories), len(files), total_bytes) != (82, 115, 33_603_763):
        raise EvidenceError("completed research-data inventory differs from reviewed closure")

    workbook = data_root / "00_external" / "defensoria_provided" / "Base15-26.xlsx"
    workbook_raw = workbook.read_bytes()
    if (
        len(workbook_raw) != 238_489
        or _sha256(workbook_raw)
        != "4fb9e973b5a063527e7e9ccce4634daa07139a14116a926eb0f76b72377b19fb"
    ):
        raise EvidenceError("protected external workbook differs from reviewed closure")

    derived_files = tuple(
        path
        for zone in (
            "02_extracted",
            "03_parsed",
            "04_linked",
            "05_database",
            "06_validation",
            "07_releases",
        )
        for path in (data_root / zone).rglob("*")
        if path.is_file()
    )
    if derived_files:
        raise EvidenceError("derived research-data layers must remain empty for M1-04A")
    if (data_root / "01_raw" / ".staging").exists():
        raise EvidenceError("raw staging unexpectedly exists")
    return DataRootSnapshot(
        directory_count=len(directories),
        file_count=len(files),
        total_bytes=total_bytes,
        protected_source_count=11,
        derived_file_count=0,
    )
