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
from peru_conflicts.manifest.evidence import (
    AcquisitionClosure,
    DiscoveryEvidence,
    DiscoveryOccurrence,
)
from peru_conflicts.manifest.materialize import (
    MaterializationError,
    materialize_candidate_package,
)
from peru_conflicts.manifest.models import ArtifactFingerprint, MaterializationReceipt
from peru_conflicts.manifest.reconcile import (
    CandidatePackage,
    ReconciliationContext,
    reconcile_manifest,
)

SHA_A = "a" * 64
GIT_SHA = "b" * 40


def _package() -> tuple[CandidatePackage, AcquisitionClosure]:
    captured = datetime(2026, 8, 27, tzinfo=UTC)
    url = "https://www.defensoria.gob.pe/report-23/"
    observation = UrlObservation(
        observation_id="observation-23",
        role=UrlRole.LANDING_PAGE,
        url=url,
        captured_at=captured,
    )
    record = ProvisionalDiscoveryRecord(
        discovery_record_id="discovery-23",
        candidate_report_number=23,
        candidate_reference_period="2006-01",
        entry_title_original="Reporte N° 23 — enero 2006",
        identity_evidence=(
            IdentityEvidence(
                evidence_id="number-23",
                subject=IdentitySubject.REPORT_NUMBER,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value="23",
                observed_value="N° 23",
                source_observation_id=observation.observation_id,
                source_url=url,
                captured_at=captured,
            ),
            IdentityEvidence(
                evidence_id="month-2006-01",
                subject=IdentitySubject.REFERENCE_PERIOD,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value="2006-01",
                observed_value="enero 2006",
                source_observation_id=observation.observation_id,
                source_url=url,
                captured_at=captured,
            ),
        ),
        url_observations=(observation,),
    )
    fingerprint = ArtifactFingerprint(
        artifact_role="discovery_records",
        path=".cache/run/records.jsonl",
        bytes=10,
        sha256=SHA_A,
        record_count=1,
    )
    discovery = DiscoveryEvidence(
        occurrences=(DiscoveryOccurrence("reconnaissance-a", 1, record),),
        artifact_fingerprints=(fingerprint,),
    )
    acquisition = AcquisitionClosure(
        authorization_id="m1-03b2-reports-260-269-compare-v2",
        run_id="m103b-example",
        terminal_status="completed",
        terminal_reason="all_ten_remote_bytes_identical",
        authorization_spent=True,
        reports=(),
        protected_bytes=(),
        operational_fingerprints=(
            fingerprint.model_copy(update={"artifact_role": "operational_ledger"}),
        ),
    )
    package = reconcile_manifest(
        discovery,
        acquisition,
        ReconciliationContext(repository_base_sha=GIT_SHA, implementation_git_sha=GIT_SHA),
    )
    return package, acquisition


def test_candidate_materialization_is_byte_deterministic_and_receipted(tmp_path: Path) -> None:
    package, acquisition = _package()
    first = tmp_path / ".cache" / "first"
    second = tmp_path / ".cache" / "second"

    first_receipt = materialize_candidate_package(
        package,
        acquisition=acquisition,
        output_dir=first,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )
    second_receipt = materialize_candidate_package(
        package,
        acquisition=acquisition,
        output_dir=second,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )

    assert {path.name for path in first.iterdir()} == {
        "byte_versions_candidate.jsonl",
        "corpus_manifest_candidate.jsonl",
        "coverage_report_candidate.json",
        "gap_register_candidate.jsonl",
        "materialization_receipt.json",
        "source_observations_candidate.jsonl",
        "version_edges_candidate.jsonl",
    }
    for first_path in first.iterdir():
        second_path = second / first_path.name
        assert first_path.read_bytes() == second_path.read_bytes()
    receipt = MaterializationReceipt.model_validate_json(first_receipt.read_bytes())
    assert first_receipt.read_bytes() == second_receipt.read_bytes()
    assert receipt.no_network_assertion is True
    assert receipt.record_counts
    assert hashlib.sha256(first_receipt.read_bytes()).hexdigest()


def test_candidate_materializer_rejects_existing_or_non_cache_target(tmp_path: Path) -> None:
    package, acquisition = _package()
    existing = tmp_path / ".cache" / "existing"
    existing.mkdir(parents=True)
    with pytest.raises(MaterializationError, match="already exists"):
        materialize_candidate_package(
            package,
            acquisition=acquisition,
            output_dir=existing,
            repository_root=tmp_path,
            repository_base_sha=GIT_SHA,
            repository_head_sha=GIT_SHA,
            protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
        )
    with pytest.raises(MaterializationError, match="ignored repository cache"):
        materialize_candidate_package(
            package,
            acquisition=acquisition,
            output_dir=tmp_path / "05_database",
            repository_root=tmp_path,
            repository_base_sha=GIT_SHA,
            repository_head_sha=GIT_SHA,
            protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
        )
