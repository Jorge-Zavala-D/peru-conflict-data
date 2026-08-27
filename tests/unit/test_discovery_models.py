from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from peru_conflicts.discovery.models import (
    DISCOVERY_SCHEMA_VERSION,
    CandidateSourceRelation,
    CandidateSourceRelationType,
    CoverageExpectation,
    IdentityEvidence,
    IdentityEvidenceType,
    IdentitySubject,
    ProvisionalDiscoveryRecord,
    RedirectHop,
    UrlObservation,
    UrlRole,
)

CAPTURED_AT = datetime(2026, 8, 27, 10, 30, tzinfo=UTC)
CATALOGUE_URL = "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"
LANDING_URL = "https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-269/"
DOWNLOAD_URL = "https://www.defensoria.gob.pe/wp-content/uploads/2026/07/Reporte-269.pdf"


def _identity_evidence(
    *,
    subject: IdentitySubject,
    candidate_value: str,
    observed_value: str,
    evidence_type: IdentityEvidenceType = IdentityEvidenceType.OFFICIAL_METADATA,
) -> IdentityEvidence:
    return IdentityEvidence(
        subject=subject,
        evidence_type=evidence_type,
        candidate_value=candidate_value,
        observed_value=observed_value,
        source_url=LANDING_URL,
        captured_at=CAPTURED_AT,
        source_excerpt="Reporte de conflictos sociales N.° 269 — julio 2026",
    )


def _landing_observation() -> UrlObservation:
    return UrlObservation(
        observation_id="url-observation-1",
        role=UrlRole.LANDING_PAGE,
        url=LANDING_URL,
        captured_at=CAPTURED_AT,
        http_status=200,
    )


def test_report_number_requires_paired_evidence_for_the_exact_subject_and_value() -> None:
    wrong_subject = _identity_evidence(
        subject=IdentitySubject.REFERENCE_PERIOD,
        candidate_value="269",
        observed_value="269",
    )
    wrong_value = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="268",
        observed_value="N.° 268",
    )

    with pytest.raises(ValidationError, match="candidate report number"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            candidate_report_number=269,
            identity_evidence=(wrong_subject, wrong_value),
            url_observations=(_landing_observation(),),
        )


def test_reference_period_requires_paired_evidence_for_the_exact_subject_and_value() -> None:
    wrong_period = _identity_evidence(
        subject=IdentitySubject.REFERENCE_PERIOD,
        candidate_value="2026-06",
        observed_value="junio 2026",
    )

    with pytest.raises(ValidationError, match="candidate reference period"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-2026-07",
            candidate_reference_period="2026-07",
            identity_evidence=(wrong_period,),
            url_observations=(_landing_observation(),),
        )


@pytest.mark.parametrize(
    "evidence_type",
    [IdentityEvidenceType.FILENAME, IdentityEvidenceType.EMBEDDED_PDF_TITLE],
)
def test_weak_file_evidence_cannot_be_the_sole_identity_basis(
    evidence_type: IdentityEvidenceType,
) -> None:
    weak_evidence = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="269",
        observed_value="Reporte-269.pdf",
        evidence_type=evidence_type,
    )

    with pytest.raises(ValidationError, match="document-visible or official metadata evidence"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            candidate_report_number=269,
            identity_evidence=(weak_evidence,),
            url_observations=(_landing_observation(),),
        )


def test_qualifying_paired_evidence_supports_both_candidate_identity_values() -> None:
    record = ProvisionalDiscoveryRecord(
        discovery_record_id="candidate-269",
        candidate_report_number=269,
        candidate_reference_period="2026-07",
        identity_evidence=(
            _identity_evidence(
                subject=IdentitySubject.REPORT_NUMBER,
                candidate_value="269",
                observed_value="N.° 269",
            ),
            _identity_evidence(
                subject=IdentitySubject.REFERENCE_PERIOD,
                candidate_value="2026-07",
                observed_value="julio 2026",
                evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
            ),
        ),
        url_observations=(_landing_observation(),),
    )

    assert record.schema_version == DISCOVERY_SCHEMA_VERSION == "0.1.0"
    assert record.candidate_report_number == 269
    assert record.candidate_reference_period == "2026-07"


def test_null_candidates_are_valid_and_uncertainty_is_preserved() -> None:
    record = ProvisionalDiscoveryRecord(
        discovery_record_id="candidate-unknown",
        identity_evidence=(),
        url_observations=(_landing_observation(),),
        uncertainty_notes=("The official landing page does not state a reference month.",),
    )

    assert record.candidate_report_number is None
    assert record.candidate_reference_period is None
    assert record.uncertainty_notes == (
        "The official landing page does not state a reference month.",
    )


def test_contradictory_source_values_are_preserved_without_reconciliation() -> None:
    official_value = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="269",
        observed_value="N.° 269",
    )
    contradictory_filename = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="268",
        observed_value="Reporte-268.pdf",
        evidence_type=IdentityEvidenceType.FILENAME,
    )

    record = ProvisionalDiscoveryRecord(
        discovery_record_id="candidate-269",
        candidate_report_number=269,
        identity_evidence=(official_value, contradictory_filename),
        url_observations=(_landing_observation(),),
        uncertainty_notes=("Official metadata and filename disagree.",),
    )

    assert [evidence.candidate_value for evidence in record.identity_evidence] == ["269", "268"]
    assert record.uncertainty_notes == ("Official metadata and filename disagree.",)


def test_url_roles_and_redirect_hops_remain_distinct_structured_records() -> None:
    redirect = RedirectHop(
        from_url="https://defensoria.gob.pe/download?id=269",
        to_url=DOWNLOAD_URL,
        status_code=302,
        captured_at=CAPTURED_AT,
    )
    observations = (
        UrlObservation(
            observation_id="surface-1",
            role=UrlRole.DISCOVERY_SURFACE,
            url=CATALOGUE_URL,
            captured_at=CAPTURED_AT,
        ),
        _landing_observation(),
        UrlObservation(
            observation_id="download-1",
            role=UrlRole.DIRECT_DOWNLOAD,
            url=DOWNLOAD_URL,
            captured_at=CAPTURED_AT,
            redirect_hops=(redirect,),
        ),
    )

    assert [observation.role for observation in observations] == [
        UrlRole.DISCOVERY_SURFACE,
        UrlRole.LANDING_PAGE,
        UrlRole.DIRECT_DOWNLOAD,
    ]
    assert observations[2].redirect_hops[0].role == "redirect_hop"
    assert observations[2].redirect_hops[0].from_url != observations[2].redirect_hops[0].to_url


def test_candidate_source_relation_allows_only_pre_hash_same_report_claims() -> None:
    relation = CandidateSourceRelation(
        relation_id="relation-1",
        source_url=LANDING_URL,
        related_source_url=DOWNLOAD_URL,
        relation_type=CandidateSourceRelationType.APPEARS_SAME_REPORT,
        captured_at=CAPTURED_AT,
        rationale="The official landing page links to this file URL.",
    )

    assert relation.relation_type is CandidateSourceRelationType.APPEARS_SAME_REPORT
    with pytest.raises(ValidationError):
        CandidateSourceRelation.model_validate(
            {
                **relation.model_dump(),
                "relation_type": "alternate_byte_version",
                "byte_identity": True,
            }
        )


def test_coverage_expectation_is_a_research_hypothesis_not_an_observation() -> None:
    expectation = CoverageExpectation(
        reference_period="2004-04",
        rationale="Monthly research grid begins at the project start month.",
    )

    assert expectation.expectation_kind == "research_coverage_grid"
    with pytest.raises(ValidationError):
        CoverageExpectation.model_validate(
            {
                **expectation.model_dump(),
                "observed_source_url": LANDING_URL,
                "published": True,
            }
        )


def test_discovery_models_are_strict_frozen_and_reject_empty_identifiers() -> None:
    observation = _landing_observation()

    with pytest.raises(ValidationError, match="frozen"):
        observation.url = DOWNLOAD_URL
    with pytest.raises(ValidationError):
        UrlObservation.model_validate({**observation.model_dump(), "unexpected": "field"})
    with pytest.raises(ValidationError):
        ProvisionalDiscoveryRecord(
            discovery_record_id="   ",
            url_observations=(observation,),
        )
