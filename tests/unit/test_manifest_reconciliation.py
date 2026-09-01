from __future__ import annotations

from datetime import UTC, datetime

import pytest

from peru_conflicts.discovery.models import (
    CandidateSourceRelation,
    CandidateSourceRelationType,
    IdentityEvidence,
    IdentityEvidenceType,
    IdentitySubject,
    ProvisionalDiscoveryRecord,
    UrlObservation,
    UrlRole,
)
from peru_conflicts.manifest.evidence import (
    AcquisitionClosure,
    CompletedReportEvidence,
    DiscoveryEvidence,
    DiscoveryOccurrence,
    ProtectedByteEvidence,
)
from peru_conflicts.manifest.models import (
    ArtifactFingerprint,
    GapClassification,
)
from peru_conflicts.manifest.reconcile import (
    ReconciliationContext,
    ReconciliationError,
    reconcile_manifest,
)

SHA_A = "a" * 64
GIT_SHA = "b" * 40
CAPTURED = datetime(2026, 8, 27, tzinfo=UTC)


def _fingerprint(role: str = "discovery_records") -> ArtifactFingerprint:
    return ArtifactFingerprint(
        artifact_role=role,
        path=f".cache/{role}.jsonl",
        bytes=10,
        sha256=SHA_A,
        record_count=1,
    )


def _record(
    *,
    record_id: str,
    report_number: int | None,
    month: str | None,
    host: str = "www.defensoria.gob.pe",
    title: str | None = None,
    direct_urls: tuple[str, ...] = (),
) -> ProvisionalDiscoveryRecord:
    surface_url = f"https://{host}/{record_id}/"
    surface = UrlObservation(
        observation_id=f"surface-{record_id}",
        role=UrlRole.CATALOGUE_PAGE,
        url=surface_url,
        captured_at=CAPTURED,
        http_status=200,
        content_type="text/html",
    )
    observations: list[UrlObservation] = [surface]
    relations: list[CandidateSourceRelation] = []
    for index, direct_url in enumerate(direct_urls, start=1):
        direct = UrlObservation(
            observation_id=f"direct-{record_id}-{index}",
            role=UrlRole.DIRECT_DOWNLOAD,
            url=direct_url,
            captured_at=CAPTURED,
        )
        observations.append(direct)
        relations.append(
            CandidateSourceRelation(
                relation_id=f"relation-{record_id}-{index}",
                source_observation_id=surface.observation_id,
                source_url=surface.url,
                related_observation_id=direct.observation_id,
                related_source_url=direct.url,
                relation_type=CandidateSourceRelationType.APPEARS_SAME_REPORT,
                captured_at=CAPTURED,
                rationale="Official HTML entry visibly links this candidate URL.",
            )
        )

    evidence: list[IdentityEvidence] = []
    if report_number is not None:
        evidence.append(
            IdentityEvidence(
                evidence_id=f"number-{record_id}",
                subject=IdentitySubject.REPORT_NUMBER,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value=str(report_number),
                observed_value=f"N° {report_number}",
                source_observation_id=surface.observation_id,
                source_url=surface.url,
                captured_at=CAPTURED,
            )
        )
    if month is not None:
        evidence.append(
            IdentityEvidence(
                evidence_id=f"month-{record_id}",
                subject=IdentitySubject.REFERENCE_PERIOD,
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                candidate_value=month,
                observed_value=month,
                source_observation_id=surface.observation_id,
                source_url=surface.url,
                captured_at=CAPTURED,
            )
        )
    return ProvisionalDiscoveryRecord(
        discovery_record_id=record_id,
        candidate_report_number=report_number,
        candidate_reference_period=month,
        source_page_title_original=title,
        entry_title_original=title,
        identity_evidence=tuple(evidence),
        url_observations=tuple(observations),
        candidate_source_relations=tuple(relations),
        uncertainty_notes=("No numbered identity was inferred.",) if report_number is None else (),
    )


def _discovery(*occurrences: DiscoveryOccurrence) -> DiscoveryEvidence:
    return DiscoveryEvidence(
        occurrences=occurrences,
        artifact_fingerprints=(_fingerprint(),),
    )


def _empty_acquisition() -> AcquisitionClosure:
    return AcquisitionClosure(
        authorization_id="m1-03b2-reports-260-269-compare-v2",
        run_id="m103b-example",
        terminal_status="completed",
        terminal_reason="all_ten_remote_bytes_identical",
        authorization_spent=True,
        reports=(),
        protected_bytes=(),
        operational_fingerprints=(_fingerprint("ledger"),),
    )


def _context() -> ReconciliationContext:
    return ReconciliationContext(
        repository_base_sha=GIT_SHA,
        implementation_git_sha=GIT_SHA,
    )


def test_reconciliation_builds_only_observed_paired_number_month_identity() -> None:
    paired = _record(
        record_id="paired",
        report_number=23,
        month="2006-01",
        title="Reporte N° 23 — enero 2006",
    )
    number_only = _record(
        record_id="number-only",
        report_number=24,
        month=None,
        title="Reporte N° 24",
    )
    numberless = _record(
        record_id="historical-2004",
        report_number=None,
        month=None,
        title="Reporte Mensual de Conflictos Sociales 2004",
    )

    package = reconcile_manifest(
        _discovery(
            DiscoveryOccurrence("run-a", 1, paired),
            DiscoveryOccurrence("run-a", 2, number_only),
            DiscoveryOccurrence("run-a", 3, numberless),
        ),
        _empty_acquisition(),
        _context(),
    )

    assert [(item.report_number, item.reference_month) for item in package.manifest] == [
        (23, "2006-01")
    ]
    assert all(item.report_number != 24 for item in package.manifest)
    assert all(item.report_number not in range(1, 23) for item in package.manifest)
    assert package.manifest[0].review_status.value == "candidate"
    assert (
        sum(
            gap.classification is GapClassification.HISTORICAL_MONTH_UNRESOLVED
            for gap in package.gaps
        )
        == 21
    )
    assert (
        sum(
            gap.classification is GapClassification.UNOBSERVED_REPORT_NUMBER for gap in package.gaps
        )
        == 22
    )
    assert any(
        gap.classification is GapClassification.HISTORICAL_UNNUMBERED_SOURCE_LEAD
        for gap in package.gaps
    )


def test_reconciliation_rejects_both_mapping_conflict_directions() -> None:
    same_number_a = _record(record_id="a", report_number=23, month="2006-01")
    same_number_b = _record(record_id="b", report_number=23, month="2006-02")
    with pytest.raises(ReconciliationError, match="report number maps to multiple months"):
        reconcile_manifest(
            _discovery(
                DiscoveryOccurrence("run-a", 1, same_number_a),
                DiscoveryOccurrence("run-a", 2, same_number_b),
            ),
            _empty_acquisition(),
            _context(),
        )

    same_month = _record(record_id="c", report_number=24, month="2006-01")
    with pytest.raises(ReconciliationError, match="reference month maps to multiple reports"):
        reconcile_manifest(
            _discovery(
                DiscoveryOccurrence("run-a", 1, same_number_a),
                DiscoveryOccurrence("run-a", 2, same_month),
            ),
            _empty_acquisition(),
            _context(),
        )


def test_source_observation_multiplicity_and_host_originals_are_preserved() -> None:
    first = _record(
        record_id="same-record",
        report_number=23,
        month="2006-01",
        host="defensoria.gob.pe",
        title="Reporte N° 23",
    )
    second = _record(
        record_id="same-record",
        report_number=23,
        month="2006-01",
        host="www.defensoria.gob.pe",
        title="Reporte N° 23",
    )

    package = reconcile_manifest(
        _discovery(
            DiscoveryOccurrence("run-a", 1, first),
            DiscoveryOccurrence("run-b", 1, second),
        ),
        _empty_acquisition(),
        _context(),
    )

    assert len(package.source_observations) == 2
    assert {item.discovery_run_id for item in package.source_observations} == {
        "run-a",
        "run-b",
    }
    assert {item.source_url_original for item in package.source_observations} == {
        "https://defensoria.gob.pe/same-record/",
        "https://www.defensoria.gob.pe/same-record/",
    }
    assert len({item.source_observation_record_id for item in package.source_observations}) == 2


def test_multiple_direct_urls_remain_unknown_without_byte_evidence() -> None:
    record = _record(
        record_id="multiple-urls",
        report_number=69,
        month="2009-11",
        direct_urls=(
            "https://www.defensoria.gob.pe/files/report-69-a.pdf",
            "https://www.defensoria.gob.pe/files/report-69-b.pdf",
        ),
    )

    package = reconcile_manifest(
        _discovery(DiscoveryOccurrence("run-a", 1, record)),
        _empty_acquisition(),
        _context(),
    )

    matching = [
        edge
        for edge in package.version_edges
        if edge.relation_type.value == "multiple_official_urls_one_observed_identity"
    ]
    assert len(matching) == 1
    assert matching[0].byte_version_ids == ()
    assert (
        sum(
            edge.relation_type.value == "candidate_same_report_without_byte_evidence"
            for edge in package.version_edges
        )
        == 2
    )
    assert {item.url_role for item in package.source_observations} == {
        "catalogue_page",
        "direct_download",
    }
    assert any(
        gap.classification is GapClassification.MULTIPLE_DIRECT_URL_BYTES_UNKNOWN
        for gap in package.gaps
    )


def test_completed_acquisition_adds_exact_bytes_without_upgrading_opaque_association() -> None:
    record = _record(
        record_id="report-261",
        report_number=261,
        month="2025-11",
        title="Reporte N° 261 — noviembre 2025",
        direct_urls=("https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf",),
    )
    protected = ProtectedByteEvidence(
        report_number=261,
        relative_path="01_raw/reports/2025/report-261.pdf",
        bytes=100,
        sha256=SHA_A,
    )
    acquisition = AcquisitionClosure(
        authorization_id="m1-03b2-reports-260-269-compare-v2",
        run_id="m103b-example",
        terminal_status="completed",
        terminal_reason="all_ten_remote_bytes_identical",
        authorization_spent=True,
        reports=(
            CompletedReportEvidence(
                report_number=261,
                landing_url="https://www.defensoria.gob.pe/documentos/report-261/",
                direct_url="https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf",
                protected=protected,
                association_status="unresolved_opaque_filename",
                acquisition_evidence_ids=("byte-object-261", "comparison-261", "cleanup-261"),
                remote_observation_evidence_ids=("landing-association-261",),
            ),
        ),
        protected_bytes=(protected,),
        operational_fingerprints=(_fingerprint("ledger"),),
    )

    package = reconcile_manifest(
        _discovery(DiscoveryOccurrence("run-a", 1, record)), acquisition, _context()
    )

    assert len(package.byte_versions) == 1
    assert package.byte_versions[0].sha256 == SHA_A
    assert package.byte_versions[0].association_status.value == "unresolved_opaque_filename"
    assert package.manifest[0].association_status.value == "unresolved_opaque_filename"
    assert any(
        edge.relation_type.value == "exact_identical_bytes" for edge in package.version_edges
    )
    assert any(
        gap.classification is GapClassification.OPAQUE_DIRECT_FILE_ASSOCIATION
        for gap in package.gaps
    )


def test_stale_embedded_title_cannot_replace_visible_title() -> None:
    record = _record(
        record_id="report-260",
        report_number=260,
        month="2025-10",
        title="Reporte N° 260 — octubre 2025",
    )
    embedded = IdentityEvidence(
        evidence_id="embedded-stale-title",
        subject=IdentitySubject.REPORT_NUMBER,
        evidence_type=IdentityEvidenceType.EMBEDDED_PDF_TITLE,
        candidate_value="260",
        observed_value="RCS N° 126",
        source_observation_id=record.url_observations[0].observation_id,
        source_url=record.url_observations[0].url,
        captured_at=CAPTURED,
        uncertainty_note="Stale embedded metadata is not identity evidence.",
    )
    record = record.model_copy(update={"identity_evidence": (*record.identity_evidence, embedded)})

    package = reconcile_manifest(
        _discovery(DiscoveryOccurrence("run-a", 1, record)),
        _empty_acquisition(),
        _context(),
    )

    assert package.manifest[0].preferred_title_original == "Reporte N° 260 — octubre 2025"
    assert all(
        reference.evidence_id != "embedded-stale-title"
        for reference in package.manifest[0].identity_evidence_refs
    )


def test_conflicting_source_titles_remain_preserved_without_preferred_selection() -> None:
    first = _record(
        record_id="report-117-a",
        report_number=117,
        month="2013-11",
        title="Reporte N° 117",
    )
    second = _record(
        record_id="report-117-b",
        report_number=117,
        month="2013-11",
        title="Reporte Mensual de Conflictos Sociales N° 117 — noviembre 2013",
    )

    package = reconcile_manifest(
        _discovery(
            DiscoveryOccurrence("run-a", 1, first),
            DiscoveryOccurrence("run-a", 2, second),
        ),
        _empty_acquisition(),
        _context(),
    )

    assert len(package.manifest[0].source_titles) == 2
    assert package.manifest[0].preferred_title_original is None
    assert any(
        gap.classification is GapClassification.SOURCE_METADATA_REQUIRES_REVIEW
        for gap in package.gaps
    )


def test_input_occurrence_order_does_not_change_candidate_records() -> None:
    first = DiscoveryOccurrence(
        "run-a", 1, _record(record_id="report-23", report_number=23, month="2006-01")
    )
    second = DiscoveryOccurrence(
        "run-b", 1, _record(record_id="report-23", report_number=23, month="2006-01")
    )

    forward = reconcile_manifest(_discovery(first, second), _empty_acquisition(), _context())
    reverse = reconcile_manifest(_discovery(second, first), _empty_acquisition(), _context())

    assert forward == reverse
