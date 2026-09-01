from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.discovery.models import (
    IdentityEvidence,
    IdentityEvidenceType,
    IdentitySubject,
    ProvisionalDiscoveryRecord,
    UrlObservation,
    UrlRole,
)
from peru_conflicts.discovery.receipts import (
    CorpusCompletenessStatus,
    LandingTraversalCounts,
    ReconnaissanceSummary,
    StopClass,
    SurfaceStopReason,
    SurfaceTraversalReceipt,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.manifest.evidence import (
    DiscoveryArtifactExpectation,
    DiscoveryRunInput,
    EvidenceError,
    ProtectedByteEvidence,
    ReviewedDiscoveryRun,
    load_discovery_runs,
    validate_protected_file_inventory,
)


def _record(*, observation_id: str, captured_at: datetime) -> ProvisionalDiscoveryRecord:
    url = "https://www.defensoria.gob.pe/example/"
    observation = UrlObservation(
        observation_id=observation_id,
        role=UrlRole.LANDING_PAGE,
        url=url,
        captured_at=captured_at,
        http_status=200,
        content_type="text/html",
    )
    return ProvisionalDiscoveryRecord(
        discovery_record_id="discovery-same-id",
        candidate_report_number=23,
        candidate_reference_period="2006-01",
        source_page_title_original="Reporte N° 23 — enero 2006",
        entry_title_original="Reporte N° 23 — enero 2006",
        identity_evidence=(
            IdentityEvidence(
                evidence_id="evidence-number",
                subject=IdentitySubject.REPORT_NUMBER,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value="23",
                observed_value="N° 23",
                source_observation_id=observation_id,
                source_url=url,
                captured_at=captured_at,
            ),
            IdentityEvidence(
                evidence_id="evidence-month",
                subject=IdentitySubject.REFERENCE_PERIOD,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value="2006-01",
                observed_value="enero 2006",
                source_observation_id=observation_id,
                source_url=url,
                captured_at=captured_at,
            ),
        ),
        url_observations=(observation,),
    )


def _write_run(
    directory: Path, *, run_id: str, record: ProvisionalDiscoveryRecord
) -> ReviewedDiscoveryRun:
    directory.mkdir()
    records = canonical_json_bytes(record.model_dump(mode="json")) + b"\n"
    requests = b""
    summary_model = ReconnaissanceSummary(
        schema_version="0.3.0",
        run_id=run_id,
        started_at=datetime(2026, 8, 27, tzinfo=UTC),
        completed_at=datetime(2026, 8, 27, 0, 1, tzinfo=UTC),
        start_urls=("https://www.defensoria.gob.pe/example/",),
        pages_visited=1,
        records_written=1,
        request_attempt_count=0,
        surface_traversals=(
            SurfaceTraversalReceipt(
                start_url="https://www.defensoria.gob.pe/example/",
                pages_visited=1,
                seen_urls=("https://www.defensoria.gob.pe/example/",),
                stop_reason=SurfaceStopReason.SINGLE_PAGE,
                stop_class=StopClass.LOCAL_TERMINAL,
                reached_local_terminal=True,
                pagination_contract_verified=True,
                pagination_exhausted=False,
            ),
        ),
        landing_pages=LandingTraversalCounts(
            discovered=0,
            selected=0,
            fetched=0,
            failed=0,
            skipped=0,
            cap_reached=False,
        ),
        all_surfaces_reached_local_terminal=True,
        corpus_completeness_status=CorpusCompletenessStatus.NOT_ASSESSED,
        boundary="HTML only",
    )
    summary = canonical_json_bytes(summary_model.model_dump(mode="json")) + b"\n"
    files = {"records.jsonl": records, "requests.jsonl": requests, "summary.json": summary}
    expectations: list[DiscoveryArtifactExpectation] = []
    for filename, content in files.items():
        (directory / filename).write_bytes(content)
        expectations.append(
            DiscoveryArtifactExpectation(
                filename=filename,
                bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                line_count=(len(content.splitlines()) if filename.endswith(".jsonl") else None),
            )
        )
    return ReviewedDiscoveryRun(run_id=run_id, artifacts=tuple(expectations))


def test_discovery_loader_preserves_cross_run_capture_occurrences_and_input_order(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    spec_a = _write_run(
        run_a,
        run_id="reconnaissance-a",
        record=_record(
            observation_id="observation-a",
            captured_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
    )
    spec_b = _write_run(
        run_b,
        run_id="reconnaissance-b",
        record=_record(
            observation_id="observation-b",
            captured_at=datetime(2026, 8, 28, tzinfo=UTC),
        ),
    )

    evidence = load_discovery_runs(
        (
            DiscoveryRunInput(run_id=spec_b.run_id, directory=run_b),
            DiscoveryRunInput(run_id=spec_a.run_id, directory=run_a),
        ),
        reviewed_runs={spec_a.run_id: spec_a, spec_b.run_id: spec_b},
        repository_root=tmp_path,
    )

    assert [item.run_id for item in evidence.occurrences] == [
        "reconnaissance-a",
        "reconnaissance-b",
    ]
    assert [item.record.discovery_record_id for item in evidence.occurrences] == [
        "discovery-same-id",
        "discovery-same-id",
    ]
    assert len(evidence.artifact_fingerprints) == 6


def test_discovery_loader_rejects_fingerprint_or_summary_run_mismatch(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    spec = _write_run(
        directory,
        run_id="reconnaissance-a",
        record=_record(
            observation_id="observation-a",
            captured_at=datetime(2026, 8, 27, tzinfo=UTC),
        ),
    )
    (directory / "records.jsonl").write_bytes(b"{}\n")

    with pytest.raises(EvidenceError, match="fingerprint mismatch"):
        load_discovery_runs(
            (DiscoveryRunInput(run_id=spec.run_id, directory=directory),),
            reviewed_runs={spec.run_id: spec},
            repository_root=tmp_path,
        )

    different_input = DiscoveryRunInput(run_id="reconnaissance-b", directory=directory)
    with pytest.raises(EvidenceError, match="is not a reviewed frozen run"):
        load_discovery_runs(
            (different_input,),
            reviewed_runs={spec.run_id: spec},
            repository_root=tmp_path,
        )


def test_protected_inventory_rejects_unreferenced_raw_file(tmp_path: Path) -> None:
    reports = tmp_path / "01_raw" / "reports"
    reports.mkdir(parents=True)
    expected_path = reports / "report-260.pdf"
    expected_path.write_bytes(b"expected")
    expected = ProtectedByteEvidence(
        report_number=260,
        relative_path="01_raw/reports/report-260.pdf",
        bytes=8,
        sha256=hashlib.sha256(b"expected").hexdigest(),
    )

    validate_protected_file_inventory(reports, (expected,), raw_root=tmp_path)
    (reports / "unexpected.pdf").write_bytes(b"unexpected")

    with pytest.raises(EvidenceError, match="unexpected raw report files"):
        validate_protected_file_inventory(reports, (expected,), raw_root=tmp_path)
