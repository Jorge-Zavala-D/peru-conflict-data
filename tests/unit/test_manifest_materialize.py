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
GIT_SHA_A = "a" * 40
GIT_SHA_B = "b" * 40
TREE_SHA = "c" * 40
OTHER_TREE_SHA = "d" * 40


def _package(
    *, implementation_tree_sha: str = TREE_SHA
) -> tuple[CandidatePackage, AcquisitionClosure]:
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
        ReconciliationContext(
            repository_base_sha=GIT_SHA,
            implementation_tree_sha=implementation_tree_sha,
        ),
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
    assert receipt.repository_head_sha == GIT_SHA
    assert receipt.implementation_tree_sha == TREE_SHA
    assert receipt.record_counts
    assert hashlib.sha256(first_receipt.read_bytes()).hexdigest()


def test_same_tree_different_execution_commits_keep_research_outputs_stable(
    tmp_path: Path,
) -> None:
    package, acquisition = _package()
    first = tmp_path / ".cache" / "commit-a"
    second = tmp_path / ".cache" / "commit-b"

    first_receipt_path = materialize_candidate_package(
        package,
        acquisition=acquisition,
        output_dir=first,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA_A,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )
    second_receipt_path = materialize_candidate_package(
        package,
        acquisition=acquisition,
        output_dir=second,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA_B,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )

    research_outputs = {
        "byte_versions_candidate.jsonl",
        "corpus_manifest_candidate.jsonl",
        "coverage_report_candidate.json",
        "gap_register_candidate.jsonl",
        "source_observations_candidate.jsonl",
        "version_edges_candidate.jsonl",
    }
    assert {
        name: (first / name).read_bytes() == (second / name).read_bytes()
        for name in sorted(research_outputs)
    } == {name: True for name in sorted(research_outputs)}

    first_receipt = MaterializationReceipt.model_validate_json(first_receipt_path.read_bytes())
    second_receipt = MaterializationReceipt.model_validate_json(second_receipt_path.read_bytes())
    assert first_receipt_path.read_bytes() != second_receipt_path.read_bytes()
    assert first_receipt.repository_head_sha == GIT_SHA_A
    assert second_receipt.repository_head_sha == GIT_SHA_B
    assert first_receipt.implementation_tree_sha == TREE_SHA
    assert second_receipt.implementation_tree_sha == TREE_SHA
    assert first_receipt.output_artifacts == second_receipt.output_artifacts


def test_different_implementation_trees_change_research_coverage(tmp_path: Path) -> None:
    first_package, acquisition = _package(implementation_tree_sha=TREE_SHA)
    second_package, _ = _package(implementation_tree_sha=OTHER_TREE_SHA)
    first = tmp_path / ".cache" / "tree-a"
    second = tmp_path / ".cache" / "tree-b"

    materialize_candidate_package(
        first_package,
        acquisition=acquisition,
        output_dir=first,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )
    materialize_candidate_package(
        second_package,
        acquisition=acquisition,
        output_dir=second,
        repository_root=tmp_path,
        repository_base_sha=GIT_SHA,
        repository_head_sha=GIT_SHA,
        protected_source_receipt_refs=("docs/source_integrity_receipt.md:sha256",),
    )

    assert (first / "coverage_report_candidate.json").read_bytes() != (
        second / "coverage_report_candidate.json"
    ).read_bytes()


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
