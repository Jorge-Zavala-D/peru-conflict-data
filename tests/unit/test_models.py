from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from peru_conflicts.models import (
    MODEL_REGISTRY,
    Actor,
    AdjudicationRecord,
    CaseMonth,
    CaseProtestLink,
    CaseRelationship,
    CasualtyComponent,
    ConflictCase,
    DiscrepancyRecord,
    DiscrepancyType,
    ExtractionMethod,
    ManualReviewItem,
    ModelInvocation,
    ProtestEvent,
    ProvenanceRecord,
    ReportRecord,
    SourceBBox,
    TransitionEvidence,
    ViolenceEvent,
)

SHA = "a" * 64


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        ReportRecord.model_validate(
            {
                "report_id": "report_260",
                "source_version_id": "source_260_a",
                "source_filename": "report-260.pdf",
                "sha256": SHA,
                "byte_size": 10,
                "unexpected": "silent schema drift",
            }
        )


def test_original_and_normalized_actor_values_are_distinct() -> None:
    actor = Actor(
        actor_id="actor_1",
        name_original="Federación Nativa",
        name_normalized="federacion nativa",
    )

    assert actor.name_original == "Federación Nativa"
    assert actor.name_normalized == "federacion nativa"


def test_stock_status_and_transitions_are_distinct_and_nullable() -> None:
    case_month = CaseMonth(
        case_month_id="case_month_1",
        case_id="case_1",
        report_id="report_260",
        reference_period="2025-10",
        stock_status_original="Activo",
        transitions=(
            TransitionEvidence(
                transition_original="Pasó a estado latente",
                transition_normalized="became_latent",
                provenance_ids=("prov_transition",),
            ),
        ),
    )

    assert case_month.stock_status_original == "Activo"
    assert case_month.transitions[0].transition_original == "Pasó a estado latente"
    assert case_month.transitions[0].transition_normalized == "became_latent"
    assert case_month.phase_original is None


def test_unknown_casualty_components_remain_null() -> None:
    violence = ViolenceEvent(
        violence_event_id="violence_1",
        report_id="report_260",
        description_original="El reporte menciona hechos de violencia.",
    )

    assert violence.fatalities_total is None
    assert violence.injured_total is None
    assert violence.casualty_components == ()


def test_conflict_cases_and_protests_require_an_explicit_link() -> None:
    case = ConflictCase(case_id="case_1")
    protest = ProtestEvent(protest_event_id="protest_1", report_id="report_260")
    link = CaseProtestLink(
        case_protest_link_id="link_1",
        case_id=case.case_id,
        protest_event_id=protest.protest_event_id,
        link_method="explicit_source_reference",
        provenance_ids=("prov_link",),
    )

    assert link.case_id == "case_1"
    assert link.protest_event_id == "protest_1"


def test_source_bbox_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError, match="x1"):
        SourceBBox(x0=10, y0=0, x1=2, y1=4)


def test_probabilistic_provenance_requires_model_and_prompt_metadata() -> None:
    with pytest.raises(ValidationError, match="model_invocation"):
        ProvenanceRecord(
            provenance_id="prov_1",
            object_type="case_month",
            object_id="case_month_1",
            field_name="facts_original",
            source_report_id="report_260",
            source_sha256=SHA,
            extraction_method=ExtractionMethod.PROBABILISTIC_MODEL,
            source_page=7,
            source_text="Hecho mensual segmentado.",
        )

    invocation = ModelInvocation(
        provider="openai",
        model="model-name",
        prompt_version="facts-v1",
        output_schema_version="0.1.0",
        source_span_hash=SHA,
        output_hash="b" * 64,
    )
    provenance = ProvenanceRecord(
        provenance_id="prov_1",
        object_type="case_month",
        object_id="case_month_1",
        field_name="facts_original",
        source_report_id="report_260",
        source_sha256=SHA,
        extraction_method=ExtractionMethod.PROBABILISTIC_MODEL,
        source_page=7,
        source_text="Hecho mensual segmentado.",
        model_invocation=invocation,
    )

    assert provenance.model_invocation is not None
    assert provenance.model_invocation.prompt_version == "facts-v1"


def test_parser_error_and_source_inconsistency_are_distinct() -> None:
    parser = DiscrepancyRecord(
        discrepancy_id="disc_1",
        report_id="report_260",
        discrepancy_type=DiscrepancyType.PARSER_ERROR,
        provenance_a_ids=("prov_parser",),
        classification_rationale="La salida difiere de la evidencia publicada.",
        parser_version="m0-test",
    )
    source = DiscrepancyRecord(
        discrepancy_id="disc_2",
        report_id="report_260",
        discrepancy_type=DiscrepancyType.SOURCE_INCONSISTENCY,
        provenance_a_ids=("prov_source_a",),
        provenance_b_ids=("prov_source_b",),
        classification_rationale="Dos valores publicados no coinciden.",
        parser_version="m0-test",
    )

    assert parser.discrepancy_type != source.discrepancy_type


def test_adjudication_is_versioned_append_only_data() -> None:
    decision = AdjudicationRecord(
        adjudication_id="adj_2",
        review_id="review_1",
        decision_original="Mantener ambas versiones",
        decision_action="retain_both",
        rationale="La fuente publicada contiene valores contradictorios.",
        reviewer_id="reviewer_a",
        decided_at=datetime(2026, 8, 27, tzinfo=UTC),
        parser_version="none-m0",
        evidence_provenance_ids=("prov_a", "prov_b"),
        supersedes_adjudication_id="adj_1",
    )

    assert decision.supersedes_adjudication_id == "adj_1"
    assert decision.schema_version == "0.1.0"


def test_adjudication_rejects_invalid_review_chain() -> None:
    payload = {
        "adjudication_id": "adj_1",
        "review_id": "review_1",
        "decision_original": "Mantener valor",
        "decision_action": "retain",
        "rationale": "La evidencia respalda el valor.",
        "reviewer_id": "reviewer_a",
        "decided_at": datetime(2026, 8, 27, tzinfo=UTC),
        "parser_version": "m0-test",
        "evidence_provenance_ids": ("prov_1",),
        "supersedes_adjudication_id": "adj_1",
    }

    with pytest.raises(ValidationError, match="supersede itself"):
        AdjudicationRecord.model_validate(payload)


def test_manual_machine_suggestion_requires_model_identity() -> None:
    with pytest.raises(ValidationError, match="supplied together"):
        ManualReviewItem.model_validate(
            {
                "review_id": "review_1",
                "object_type": "case_relationship",
                "issue_type": "candidate_link",
                "machine_suggestion_json": '{"candidate_id":"case_2"}',
                "evidence_provenance_ids": ("prov_1",),
                "review_status": "pending",
                "created_at": datetime(2026, 8, 27, tzinfo=UTC),
                "parser_version": "m0-test",
            }
        )


def test_relationship_types_remain_open_until_historical_evidence() -> None:
    relationship = CaseRelationship(
        relationship_id="relationship_1",
        case_id_from="case_1",
        case_id_to="case_2",
        relationship_type_original="Absorbido por el caso 2",
        relationship_type_normalized="source_specific_absorption",
        provenance_ids=("prov_relationship",),
    )

    assert relationship.relationship_type_normalized == "source_specific_absorption"


def test_registry_covers_every_canonical_foundation_entity() -> None:
    expected = {
        "actor",
        "adjudication",
        "agreement",
        "alert",
        "case",
        "case_actor",
        "case_demand",
        "case_location",
        "case_month",
        "case_name",
        "case_protest_link",
        "case_relationship",
        "demand",
        "dialogue_event",
        "discrepancy",
        "dp_action",
        "location",
        "manual_review",
        "protest_event",
        "provenance",
        "report",
        "report_month",
        "violence_event",
    }

    assert set(MODEL_REGISTRY) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [("report_number", "260"), ("byte_size", "10"), ("byte_size", False)],
)
def test_material_numeric_fields_reject_coercion(field: str, value: object) -> None:
    payload: dict[str, object] = {
        "report_id": "report_260",
        "source_version_id": "source_260_a",
        "source_filename": "report-260.pdf",
        "sha256": SHA,
        "byte_size": 10,
        field: value,
    }

    with pytest.raises(ValidationError):
        ReportRecord.model_validate(payload)


@pytest.mark.parametrize("period", ["2025-00", "2025-13", "2025-99"])
def test_reference_period_rejects_impossible_months(period: str) -> None:
    with pytest.raises(ValidationError, match="calendar month"):
        CaseMonth(
            case_month_id="case_month_1",
            case_id="case_1",
            report_id="report_260",
            reference_period=period,
        )


def test_open_transition_requires_original_text_and_provenance() -> None:
    transition = TransitionEvidence(
        transition_original="Clasificación futura no anticipada",
        transition_normalized="future_source_specific_transition",
        provenance_ids=("prov_1",),
    )

    assert transition.transition_normalized == "future_source_specific_transition"
    with pytest.raises(ValidationError):
        TransitionEvidence.model_validate(
            {
                "transition_original": "Sin evidencia",
                "transition_normalized": "future_transition",
                "provenance_ids": [],
            }
        )


def test_negative_casualty_components_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CasualtyComponent(
            component_original="Policías",
            fatalities=-1,
            injured=None,
        )


def test_case_links_require_source_evidence() -> None:
    with pytest.raises(ValidationError):
        CaseProtestLink.model_validate(
            {
                "case_protest_link_id": "link_1",
                "case_id": "case_1",
                "protest_event_id": "protest_1",
                "link_method": "explicit_source_reference",
            }
        )


def test_probabilistic_method_cannot_use_an_unregistered_alias() -> None:
    with pytest.raises(ValidationError):
        ProvenanceRecord.model_validate(
            {
                "provenance_id": "prov_1",
                "object_type": "case_month",
                "object_id": "case_month_1",
                "field_name": "facts_original",
                "source_report_id": "report_260",
                "source_sha256": SHA,
                "extraction_method": "structured_semantic_extraction",
            }
        )


def test_discrepancy_requires_type_appropriate_evidence() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        DiscrepancyRecord(
            discrepancy_id="disc_1",
            report_id="report_260",
            discrepancy_type=DiscrepancyType.PARSER_ERROR,
            classification_rationale="No coincide con la página.",
            parser_version="m0-test",
        )

    with pytest.raises(ValidationError, match="both provenance"):
        DiscrepancyRecord(
            discrepancy_id="disc_2",
            report_id="report_260",
            discrepancy_type=DiscrepancyType.SOURCE_INCONSISTENCY,
            provenance_a_ids=("prov_a",),
            classification_rationale="Dos valores no coinciden.",
            parser_version="m0-test",
        )


def test_nested_foundation_collections_are_immutable() -> None:
    violence = ViolenceEvent(
        violence_event_id="violence_1",
        report_id="report_260",
        casualty_components=(
            CasualtyComponent(component_original="Población", fatalities=None, injured=2),
        ),
    )

    with pytest.raises(TypeError):
        violence.casualty_components[0] = CasualtyComponent(  # type: ignore[index]
            component_original="Población", fatalities=None, injured=3
        )
