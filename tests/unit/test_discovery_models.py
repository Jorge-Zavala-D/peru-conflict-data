from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from peru_conflicts.discovery.models import (
    DISCOVERY_SCHEMA_VERSION,
    CandidateSourceRelation,
    CandidateSourceRelationType,
    CoverageExpectation,
    DiscoveryIssue,
    DiscoveryIssueType,
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
REDIRECT_ORIGIN_URL = "https://defensoria.gob.pe/download?id=269"
REDIRECT_INTERMEDIATE_URL = "https://www.defensoria.gob.pe/intermediate-download?id=269"
LANDING_OBSERVATION_ID = "landing-observation-1"
DOWNLOAD_OBSERVATION_ID = "download-observation-1"


def _identity_evidence(
    *,
    subject: IdentitySubject,
    candidate_value: str,
    observed_value: str,
    evidence_type: IdentityEvidenceType = IdentityEvidenceType.OFFICIAL_METADATA,
    evidence_id: str = "identity-evidence-1",
    source_observation_id: str = LANDING_OBSERVATION_ID,
    source_url: str = LANDING_URL,
) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=evidence_id,
        subject=subject,
        evidence_type=evidence_type,
        candidate_value=candidate_value,
        observed_value=observed_value,
        source_observation_id=source_observation_id,
        source_url=source_url,
        captured_at=CAPTURED_AT,
        source_excerpt="Reporte de conflictos sociales N.° 269 — julio 2026",
    )


def _landing_observation() -> UrlObservation:
    return UrlObservation(
        observation_id=LANDING_OBSERVATION_ID,
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
                evidence_id="identity-evidence-2",
            ),
        ),
        url_observations=(_landing_observation(),),
    )

    assert record.schema_version == DISCOVERY_SCHEMA_VERSION == "0.3.0"
    assert record.candidate_report_number == 269
    assert record.candidate_reference_period == "2026-07"


def test_source_page_and_entry_metadata_are_preserved_independently() -> None:
    record = ProvisionalDiscoveryRecord(
        discovery_record_id="candidate-269",
        candidate_report_number=269,
        identity_evidence=(
            _identity_evidence(
                subject=IdentitySubject.REPORT_NUMBER,
                candidate_value="269",
                observed_value="N.° 269",
            ),
        ),
        url_observations=(_landing_observation(),),
        source_page_title_original="Resultados de su búsqueda",
        entry_title_original="Reporte de conflictos sociales n.º 269 — julio 2026",
        entry_publication_date_original="13/08/2026",
        entry_description_original=("Reporte de conflictos sociales n.º 269 — julio 2026"),
    )

    assert record.source_page_title_original == "Resultados de su búsqueda"
    assert record.entry_title_original == "Reporte de conflictos sociales n.º 269 — julio 2026"
    assert record.entry_publication_date_original == "13/08/2026"
    assert record.entry_description_original == (
        "Reporte de conflictos sociales n.º 269 — julio 2026"
    )


def test_v030_rejects_ambiguous_v020_page_metadata_fields() -> None:
    with pytest.raises(ValidationError):
        ProvisionalDiscoveryRecord.model_validate(
            {
                "discovery_record_id": "candidate-unknown",
                "url_observations": [_landing_observation().model_dump()],
                "page_title_original": "Título ambiguo de v0.2.0",
                "publication_date_original": "13/08/2026",
            }
        )


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
        evidence_id="identity-evidence-2",
    )
    issue = DiscoveryIssue(
        issue_id="issue-1",
        issue_type=DiscoveryIssueType.SOURCE_INCONSISTENCY,
        evidence_ids=("identity-evidence-1", "identity-evidence-2"),
        classification_rationale="Official metadata and filename publish different numbers.",
    )

    record = ProvisionalDiscoveryRecord(
        discovery_record_id="candidate-269",
        candidate_report_number=269,
        identity_evidence=(official_value, contradictory_filename),
        url_observations=(_landing_observation(),),
        discovery_issues=(issue,),
        uncertainty_notes=("Official metadata and filename disagree.",),
    )

    assert [evidence.candidate_value for evidence in record.identity_evidence] == ["269", "268"]
    assert record.discovery_issues[0].issue_type is DiscoveryIssueType.SOURCE_INCONSISTENCY
    assert record.discovery_issues[0].evidence_ids == (
        "identity-evidence-1",
        "identity-evidence-2",
    )
    assert record.uncertainty_notes == ("Official metadata and filename disagree.",)


def test_url_roles_and_redirect_hops_remain_distinct_structured_records() -> None:
    redirect_chain = (
        RedirectHop(
            from_url=REDIRECT_ORIGIN_URL,
            to_url=REDIRECT_INTERMEDIATE_URL,
            status_code=301,
            captured_at=CAPTURED_AT,
        ),
        RedirectHop(
            from_url=REDIRECT_INTERMEDIATE_URL,
            to_url=DOWNLOAD_URL,
            status_code=302,
            captured_at=CAPTURED_AT,
        ),
    )
    observations = (
        UrlObservation(
            observation_id="catalogue-1",
            role=UrlRole.CATALOGUE_PAGE,
            url=CATALOGUE_URL,
            captured_at=CAPTURED_AT,
        ),
        UrlObservation(
            observation_id="search-1",
            role=UrlRole.SEARCH_RESULT_PAGE,
            url="https://www.defensoria.gob.pe/?s=conflictos+sociales",
            captured_at=CAPTURED_AT,
        ),
        UrlObservation(
            observation_id="thematic-1",
            role=UrlRole.THEMATIC_PAGE,
            url="https://www.defensoria.gob.pe/areas_tematicas/paz-social/",
            captured_at=CAPTURED_AT,
        ),
        _landing_observation(),
        UrlObservation(
            observation_id=DOWNLOAD_OBSERVATION_ID,
            role=UrlRole.DIRECT_DOWNLOAD,
            url=DOWNLOAD_URL,
            captured_at=CAPTURED_AT,
            redirect_hops=redirect_chain,
        ),
    )

    assert [observation.role for observation in observations] == [
        UrlRole.CATALOGUE_PAGE,
        UrlRole.SEARCH_RESULT_PAGE,
        UrlRole.THEMATIC_PAGE,
        UrlRole.LANDING_PAGE,
        UrlRole.DIRECT_DOWNLOAD,
    ]
    assert observations[4].redirect_hops[0].role == "redirect_hop"
    assert observations[4].redirect_hops[0].to_url == observations[4].redirect_hops[1].from_url
    assert observations[4].redirect_hops[-1].to_url == observations[4].url


def test_redirect_chain_must_end_at_the_parent_observation_url() -> None:
    unrelated_terminal = RedirectHop(
        from_url=REDIRECT_ORIGIN_URL,
        to_url=LANDING_URL,
        status_code=302,
        captured_at=CAPTURED_AT,
    )

    with pytest.raises(ValidationError, match="must end at the observation URL"):
        UrlObservation(
            observation_id=DOWNLOAD_OBSERVATION_ID,
            role=UrlRole.DIRECT_DOWNLOAD,
            url=DOWNLOAD_URL,
            captured_at=CAPTURED_AT,
            redirect_hops=(unrelated_terminal,),
        )


def test_multi_hop_redirect_chain_must_be_contiguous() -> None:
    broken_chain = (
        RedirectHop(
            from_url=REDIRECT_ORIGIN_URL,
            to_url=REDIRECT_INTERMEDIATE_URL,
            status_code=301,
            captured_at=CAPTURED_AT,
        ),
        RedirectHop(
            from_url=LANDING_URL,
            to_url=DOWNLOAD_URL,
            status_code=302,
            captured_at=CAPTURED_AT,
        ),
    )

    with pytest.raises(ValidationError, match="must be contiguous"):
        UrlObservation(
            observation_id=DOWNLOAD_OBSERVATION_ID,
            role=UrlRole.DIRECT_DOWNLOAD,
            url=DOWNLOAD_URL,
            captured_at=CAPTURED_AT,
            redirect_hops=broken_chain,
        )


def test_candidate_source_relation_allows_only_pre_hash_same_report_claims() -> None:
    relation = CandidateSourceRelation(
        relation_id="relation-1",
        source_observation_id=LANDING_OBSERVATION_ID,
        source_url=LANDING_URL,
        related_observation_id=DOWNLOAD_OBSERVATION_ID,
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
            }
        )
    with pytest.raises(ValidationError):
        CandidateSourceRelation.model_validate({**relation.model_dump(), "byte_identity": True})


def test_identity_evidence_requires_an_observed_matching_source_url() -> None:
    unobserved = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="269",
        observed_value="N.° 269",
        source_observation_id="missing-observation",
    )
    mismatched = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="269",
        observed_value="N.° 269",
        source_url=DOWNLOAD_URL,
    )

    with pytest.raises(ValidationError, match="unknown source observation"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            candidate_report_number=269,
            identity_evidence=(unobserved,),
            url_observations=(_landing_observation(),),
        )
    with pytest.raises(ValidationError, match="does not match source_url"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            candidate_report_number=269,
            identity_evidence=(mismatched,),
            url_observations=(_landing_observation(),),
        )


def test_stable_observation_and_evidence_ids_must_be_unique_within_a_record() -> None:
    duplicate_observation = UrlObservation(
        observation_id=LANDING_OBSERVATION_ID,
        role=UrlRole.DIRECT_DOWNLOAD,
        url=DOWNLOAD_URL,
        captured_at=CAPTURED_AT,
    )
    first_evidence = _identity_evidence(
        subject=IdentitySubject.REPORT_NUMBER,
        candidate_value="269",
        observed_value="N.° 269",
    )
    duplicate_evidence = _identity_evidence(
        subject=IdentitySubject.REFERENCE_PERIOD,
        candidate_value="2026-07",
        observed_value="julio 2026",
    )

    with pytest.raises(ValidationError, match="URL observation IDs must be unique"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-unknown",
            url_observations=(_landing_observation(), duplicate_observation),
        )
    with pytest.raises(ValidationError, match="identity evidence IDs must be unique"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-unknown",
            identity_evidence=(first_evidence, duplicate_evidence),
            url_observations=(_landing_observation(),),
        )


def test_candidate_source_relation_requires_observed_matching_endpoints() -> None:
    download = UrlObservation(
        observation_id=DOWNLOAD_OBSERVATION_ID,
        role=UrlRole.DIRECT_DOWNLOAD,
        url=DOWNLOAD_URL,
        captured_at=CAPTURED_AT,
    )
    relation = CandidateSourceRelation(
        relation_id="relation-1",
        source_observation_id=LANDING_OBSERVATION_ID,
        source_url=LANDING_URL,
        related_observation_id=DOWNLOAD_OBSERVATION_ID,
        related_source_url=DOWNLOAD_URL,
        relation_type=CandidateSourceRelationType.APPEARS_SAME_REPORT,
        captured_at=CAPTURED_AT,
        rationale="The official landing page links to this file URL.",
    )

    with pytest.raises(ValidationError, match="unknown related observation"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            url_observations=(_landing_observation(),),
            candidate_source_relations=(relation,),
        )

    mismatched = relation.model_copy(update={"related_source_url": CATALOGUE_URL})
    with pytest.raises(ValidationError, match="does not match related_source_url"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-269",
            url_observations=(_landing_observation(), download),
            candidate_source_relations=(mismatched,),
        )


def test_discovery_issue_types_have_distinct_evidence_requirements() -> None:
    with pytest.raises(ValidationError, match="at least two evidence IDs"):
        DiscoveryIssue(
            issue_id="issue-1",
            issue_type=DiscoveryIssueType.SOURCE_INCONSISTENCY,
            evidence_ids=("identity-evidence-1",),
            classification_rationale="Two published identity values conflict.",
        )

    ambiguity = DiscoveryIssue(
        issue_id="issue-2",
        issue_type=DiscoveryIssueType.SOURCE_AMBIGUITY,
        related_observation_ids=(LANDING_OBSERVATION_ID,),
        classification_rationale="The landing page does not identify the reference month.",
    )
    coverage_gap = DiscoveryIssue(
        issue_id="issue-3",
        issue_type=DiscoveryIssueType.COVERAGE_GAP,
        reference_periods=("2004-04",),
        classification_rationale="No official source has yet been observed for this grid month.",
    )

    assert ambiguity.issue_type is DiscoveryIssueType.SOURCE_AMBIGUITY
    assert coverage_gap.issue_type is DiscoveryIssueType.COVERAGE_GAP
    with pytest.raises(ValidationError):
        DiscoveryIssue.model_validate({**coverage_gap.model_dump(), "corrected_value": "269"})


def test_discovery_issue_evidence_links_must_exist_in_the_record() -> None:
    issue = DiscoveryIssue(
        issue_id="issue-1",
        issue_type=DiscoveryIssueType.SOURCE_INCONSISTENCY,
        evidence_ids=("missing-1", "missing-2"),
        classification_rationale="Two published identity values conflict.",
    )

    with pytest.raises(ValidationError, match="unknown identity evidence"):
        ProvisionalDiscoveryRecord(
            discovery_record_id="candidate-unknown",
            url_observations=(_landing_observation(),),
            discovery_issues=(issue,),
        )


def test_coverage_expectation_exists_independently_without_a_url_observation() -> None:
    expectation = CoverageExpectation(
        reference_period="2004-04",
        rationale="Monthly research grid begins at the project start month.",
    )

    assert expectation.expectation_kind == "research_coverage_grid"
    assert "url_observations" not in expectation.model_dump()
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
