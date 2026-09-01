from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from peru_conflicts.manifest.models import (
    AcquisitionState,
    ArtifactFingerprint,
    AssociationStatus,
    ByteVersionRecord,
    CandidateCompletenessStatus,
    CorpusReportManifestEntry,
    CoverageReport,
    EdgeRelationType,
    EvidenceReference,
    GapClassification,
    GapDimension,
    GapDisposition,
    GapRegisterEntry,
    ObservationEvidenceStatus,
    ReviewStatus,
    SourceObservationRecord,
    SourceTitleObservation,
    VersionSourceRelationshipEdge,
)

SHA_A = "a" * 64
GIT_SHA = "b" * 40


def _evidence_reference(evidence_id: str = "evidence-example") -> EvidenceReference:
    return EvidenceReference(
        discovery_run_id="reconnaissance-example",
        discovery_record_id="discovery-example",
        evidence_id=evidence_id,
    )


def _fingerprint() -> ArtifactFingerprint:
    return ArtifactFingerprint(
        artifact_role="discovery_records",
        path=".cache/example/records.jsonl",
        bytes=10,
        sha256=SHA_A,
    )


def _manifest_entry(**overrides: object) -> CorpusReportManifestEntry:
    values: dict[str, object] = {
        "manifest_report_id": "manifest-report-23",
        "source_institution": "Defensoría del Pueblo",
        "source_series": "Reporte Mensual de Conflictos Sociales",
        "report_number": 23,
        "reference_month": "2006-01",
        "source_titles": (
            SourceTitleObservation(
                title_original="Reporte N° 23 — enero 2006",
                evidence_refs=(_evidence_reference(),),
            ),
        ),
        "preferred_title_original": "Reporte N° 23 — enero 2006",
        "preferred_title_evidence_refs": (_evidence_reference(),),
        "identity_evidence_refs": (
            _evidence_reference("evidence-report-number"),
            _evidence_reference("evidence-reference-month"),
        ),
        "discovery_record_refs": ("reconnaissance-example:discovery-example",),
        "source_observation_record_ids": ("source-observation-example",),
        "acquisition_state": AcquisitionState.OFFICIAL_SOURCE_DISCOVERED,
        "known_byte_version_count": 0,
        "preferred_protected_local_path": None,
        "association_status": AssociationStatus.NOT_APPLICABLE,
        "review_status": ReviewStatus.CANDIDATE,
        "gap_ids": (),
        "discovery_run_ids": ("reconnaissance-example",),
        "input_artifact_fingerprints": (_fingerprint(),),
    }
    values.update(overrides)
    return CorpusReportManifestEntry.model_validate(values)


def test_manifest_entry_is_strict_and_preferred_title_is_source_original() -> None:
    entry = _manifest_entry()

    assert entry.report_number == 23
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CorpusReportManifestEntry.model_validate(
            {**entry.model_dump(mode="python"), "manufactured": True}
        )
    with pytest.raises(ValidationError, match="preferred title must be one of the source titles"):
        _manifest_entry(preferred_title_original="Corrected title")


def test_byte_verified_manifest_entry_requires_actual_byte_reference() -> None:
    with pytest.raises(
        ValidationError, match="byte-verified entry requires one or more byte versions"
    ):
        _manifest_entry(acquisition_state=AcquisitionState.BYTE_VERIFIED_IDENTICAL)

    entry = _manifest_entry(
        acquisition_state=AcquisitionState.BYTE_VERIFIED_IDENTICAL,
        known_byte_version_count=1,
        preferred_protected_local_path="01_raw/reports/report-260.pdf",
        association_status=AssociationStatus.UNRESOLVED_OPAQUE_FILENAME,
        review_status=ReviewStatus.REQUIRES_HUMAN_REVIEW,
    )
    assert entry.association_status is AssociationStatus.UNRESOLVED_OPAQUE_FILENAME


def test_exact_byte_edge_requires_byte_and_acquisition_evidence() -> None:
    with pytest.raises(
        ValidationError, match="exact byte relation requires byte and acquisition evidence"
    ):
        VersionSourceRelationshipEdge(
            edge_id="edge-example",
            manifest_report_id="manifest-report-260",
            relation_type=EdgeRelationType.EXACT_IDENTICAL_BYTES,
            source_observation_record_ids=(),
            byte_version_ids=(),
            acquisition_evidence_ids=(),
            rationale="No evidence",
            review_status=ReviewStatus.VERIFIED,
        )

    edge = VersionSourceRelationshipEdge(
        edge_id="edge-example",
        manifest_report_id="manifest-report-260",
        relation_type=EdgeRelationType.EXACT_IDENTICAL_BYTES,
        source_observation_record_ids=(),
        byte_version_ids=(f"byte-version-{SHA_A}",),
        acquisition_evidence_ids=("byte-object-260", "comparison-260"),
        rationale="The official remote observation and protected object share exact SHA-256.",
        review_status=ReviewStatus.VERIFIED,
    )
    assert edge.relation_type is EdgeRelationType.EXACT_IDENTICAL_BYTES


def test_multiple_url_edge_does_not_claim_byte_identity() -> None:
    edge = VersionSourceRelationshipEdge(
        edge_id="edge-multiple-urls",
        manifest_report_id="manifest-report-69",
        relation_type=EdgeRelationType.MULTIPLE_OFFICIAL_URLS_ONE_OBSERVED_IDENTITY,
        source_observation_record_ids=("observation-a", "observation-b"),
        byte_version_ids=(),
        acquisition_evidence_ids=(),
        rationale="Two distinct official direct URLs are associated with report 69.",
        review_status=ReviewStatus.REQUIRES_HUMAN_REVIEW,
    )
    assert edge.byte_version_ids == ()

    with pytest.raises(ValidationError, match="multiple-URL relation cannot assert byte identity"):
        VersionSourceRelationshipEdge.model_validate(
            {**edge.model_dump(mode="python"), "byte_version_ids": (f"byte-version-{SHA_A}",)}
        )


def test_gap_record_keeps_expectation_separate_from_report_identity() -> None:
    gap = GapRegisterEntry(
        gap_id="gap-reference-month-2004-04",
        gap_dimension=GapDimension.REFERENCE_MONTH,
        expected_value="2004-04",
        observed_evidence_status=ObservationEvidenceStatus.UNOBSERVED,
        classification=GapClassification.HISTORICAL_MONTH_UNRESOLVED,
        evidence_refs=(),
        rationale=(
            "Research coverage starts in April 2004, but no qualifying monthly identity was "
            "observed."
        ),
        manual_review_required=True,
        disposition=GapDisposition.PENDING_HUMAN_REVIEW,
        related_manifest_report_ids=(),
    )

    assert not hasattr(gap, "report_number")
    assert gap.expected_value == "2004-04"


def test_coverage_report_cannot_claim_final_completeness() -> None:
    report = CoverageReport(
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
        historical_bundle_lead_years=(2004, 2005),
        reports_1_22_status="unobserved_report_number_hypotheses",
        byte_verified_report_min=260,
        byte_verified_report_max=269,
        byte_verified_report_count=10,
        unresolved_gap_counts=((GapClassification.HISTORICAL_MONTH_UNRESOLVED, 21),),
        candidate_completeness_status=(CandidateCompletenessStatus.CANDIDATE_REQUIRES_HUMAN_REVIEW),
        human_review_required=True,
        input_artifact_fingerprints=(_fingerprint(),),
        implementation_git_sha=GIT_SHA,
        manifest_schema_version="0.1.0",
        materializer_version="m1-04a-v1",
    )

    assert report.candidate_completeness_status is (
        CandidateCompletenessStatus.CANDIDATE_REQUIRES_HUMAN_REVIEW
    )


def test_source_observation_and_byte_version_preserve_original_evidence() -> None:
    observation = SourceObservationRecord(
        source_observation_record_id="source-observation-example",
        discovery_run_id="reconnaissance-example",
        discovery_record_id="discovery-example",
        original_observation_id="observation-example",
        manifest_report_id="manifest-report-122",
        source_url_original="https://defensoria.gob.pe/example",
        normalized_transport_url="https://defensoria.gob.pe/example",
        url_role="catalogue_page",
        containing_source_url="https://defensoria.gob.pe/example",
        containing_surface_role="catalogue_page",
        source_page_title_original="Informes y Publicaciones",
        entry_title_original="Reporte Mensual",
        entry_publication_date_original="mayo 15,2014",
        entry_description_original="Reporte Mensual de Conflcitos Sociales N° 122 — abril 2014",
        observed_report_number=122,
        observed_reference_month="2014-04",
        identity_evidence_refs=(_evidence_reference(),),
        relation_ids=(),
        discovery_issue_ids=(),
        captured_at=datetime.fromisoformat("2026-08-27T22:52:57.279081+00:00"),
        uncertainty_notes=(),
    )
    byte_version = ByteVersionRecord(
        byte_version_id=f"byte-version-{SHA_A}",
        manifest_report_id="manifest-report-260",
        report_number=260,
        bytes=2_721_478,
        sha256=SHA_A,
        protected_local_path="01_raw/reports/report-260.pdf",
        acquisition_evidence_ids=("byte-object-260", "comparison-260"),
        official_remote_observation_evidence_ids=("landing-association-260",),
        first_seen_run_id="m103b-example",
        disposition="identical_no_duplicate",
        review_status=ReviewStatus.VERIFIED,
        association_status=AssociationStatus.VISIBLY_ASSOCIATED,
        comparison_authorization_spent=True,
    )

    assert "Conflcitos" in (observation.entry_description_original or "")
    assert byte_version.sha256 == SHA_A


def test_same_report_can_preserve_distinct_byte_versions_without_overwrite() -> None:
    first = ByteVersionRecord(
        byte_version_id=f"byte-version-{SHA_A}",
        manifest_report_id="manifest-report-260",
        report_number=260,
        bytes=100,
        sha256=SHA_A,
        protected_local_path="01_raw/reports/report-260-a.pdf",
        acquisition_evidence_ids=("comparison-a",),
        official_remote_observation_evidence_ids=("remote-a",),
        first_seen_run_id="run-a",
        disposition="identical_no_duplicate",
        review_status=ReviewStatus.VERIFIED,
        association_status=AssociationStatus.VISIBLY_ASSOCIATED,
        comparison_authorization_spent=True,
    )
    sha_b = "b" * 64
    second = first.model_copy(
        update={
            "byte_version_id": f"byte-version-{sha_b}",
            "sha256": sha_b,
            "protected_local_path": "01_raw/reports/report-260-b.pdf",
        }
    )
    edge = VersionSourceRelationshipEdge(
        edge_id="edge-distinct-bytes-260",
        manifest_report_id="manifest-report-260",
        relation_type=EdgeRelationType.DIFFERENT_BYTES_REQUIRING_REVIEW,
        source_observation_record_ids=(),
        byte_version_ids=(first.byte_version_id, second.byte_version_id),
        acquisition_evidence_ids=("comparison-a", "comparison-b"),
        rationale="Two distinct authoritative byte observations require review.",
        review_status=ReviewStatus.REQUIRES_HUMAN_REVIEW,
    )

    assert len(set(edge.byte_version_ids)) == 2
