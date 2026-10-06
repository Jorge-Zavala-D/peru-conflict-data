"""Synthetic checks for the actual successor plan and review interfaces."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from peru_conflicts.benchmark.models import (
    AnnotationSlot,
    AnnotationState,
    EvidenceAnchor,
    EvidenceGranularity,
    FieldAnnotation,
)
from peru_conflicts.execution.ai_pi import (
    CandidateVersion,
    PIDecision,
    RunEnvelope,
    SourceUnit,
    StrategyDecision,
    derive_version,
    evaluate_initial,
    main,
    plan_run,
    request_review,
    validate_candidate,
    worker_packet,
)
from peru_conflicts.models.common import SourceSpan
from peru_conflicts.models.domain import AdjudicationRecord

ROOT = Path(__file__).resolve().parents[2]


def fixture() -> tuple[RunEnvelope, CandidateVersion, dict[tuple[str, int], bytes]]:
    slot = AnnotationSlot(
        unit_id="toy-unit",
        domain_object_type="case_observation",
        cardinality_index=0,
        field_name="case_name.name_original",
    )
    anchor = EvidenceAnchor(
        report_id="toy-report",
        report_number=1,
        source_sha256="a" * 64,
        page=1,
        section="toy-section",
        granularity=EvidenceGranularity.SPAN,
        source_span=SourceSpan(start=0, end=4),
        source_text="Caso",
    )
    envelope = RunEnvelope(
        run_id="toy-run",
        purpose="synthetic",
        units=(
            SourceUnit(
                unit_id="toy-unit",
                report_id="toy-report",
                report_number=1,
                source_sha256="a" * 64,
                pages=(1,),
                sections=("toy-section",),
            ),
        ),
        eligible_slots=(slot,),
    )
    annotation = FieldAnnotation(
        annotation_id="toy-field",
        annotator_id="synthetic-machine",
        unit_id="toy-unit",
        domain_object_type="case_observation",
        field_name="case_name.name_original",
        state=AnnotationState.OBSERVED,
        raw_value_json='"initial wrong"',
        evidence_anchors=(anchor,),
    )
    candidate = CandidateVersion(
        version_id="toy-initial",
        run_id=envelope.run_id,
        envelope_sha256=envelope.fingerprint,
        origin="synthetic_fixture",
        annotations=(annotation,),
        processed_unit_ids=("toy-unit",),
    )
    return envelope, candidate, {("toy-unit", 1): b"Caso de prueba\n"}


def decision(
    envelope: RunEnvelope,
    candidate: CandidateVersion,
    *,
    mode: Literal["source_first", "assisted"] = "source_first",
) -> PIDecision:
    request = request_review(candidate, envelope, mode=mode)
    corrected = candidate.annotations[0].model_copy(update={"raw_value_json": '"Caso"'})
    return PIDecision.model_validate_json(
        json.dumps(
            {
                "decision_id": "toy-decision",
                "run_id": envelope.run_id,
                "request_sha256": request.fingerprint,
                "initial_candidate_sha256": candidate.fingerprint,
                "selection_sha256": envelope.selection_sha256,
                "mode": mode,
                "simulated": True,
                "reviewed_unit_ids": ["toy-unit"],
                "inventory_reviewed_unit_ids": [],
                "reference_annotations": [corrected.model_dump(mode="json")],
                "adjudication": AdjudicationRecord(
                    adjudication_id="toy-adjudication",
                    review_id=request.request_id,
                    decision_original="Corrección sintética",
                    decision_action="correct",
                    rationale="Invented source fixture only",
                    reviewer_id="simulated-pi",
                    decided_at=datetime(2026, 1, 1, tzinfo=UTC),
                    parser_version="toy-v1",
                    evidence_provenance_ids=("toy-evidence",),
                ).model_dump(mode="json"),
            }
        )
    )


def test_plan_reports_missing_real_parameters_without_legacy_gate() -> None:
    envelope, _, _ = fixture()
    real = envelope.model_copy(update={"purpose": "development"})
    plan = plan_run(StrategyDecision(), real)
    assert plan.executable is False
    assert set(plan.missing) == {
        "owner_execution_authority",
        "tool_configuration",
        "resource_budget",
    }
    assert not any(
        "annotator" in item or "108" in item or "witness" in item for item in plan.missing
    )


def test_actual_cli_is_plan_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    envelope, _, _ = fixture()
    path = tmp_path / "envelope.json"
    path.write_text(envelope.model_dump_json(), encoding="utf-8")
    assert (
        main(["--strategy", str(ROOT / "config/ai_pi/strategy_v1.json"), "--envelope", str(path)])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["executable"] is False
    assert result["permitted_operations"] == ["plan", "synthetic_validation"]
    assert list(tmp_path.iterdir()) == [path]


def test_unknown_strategy_and_extra_authority_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StrategyDecision.model_validate({"strategy_id": "unknown"})
    with pytest.raises(ValidationError):
        RunEnvelope.model_validate({"run_id": "fake", "human_gold_created": True})


def test_synthetic_roundtrip_preserves_initial_and_scores_initial_not_correction() -> None:
    envelope, candidate, pages = fixture()
    initial_bytes = candidate.model_dump_json()
    assert validate_candidate(candidate, envelope, pages) == ()
    request = request_review(candidate, envelope, mode="source_first")
    assert request.candidate_annotations == ()
    pi = decision(envelope, candidate)
    derived = derive_version(candidate, envelope, pi, request)
    summary = evaluate_initial(
        candidate,
        envelope,
        pi,
        request,
        expected_reference_sha256=pi.fingerprint,
        expected_selection_sha256=envelope.selection_sha256,
    )
    assert candidate.model_dump_json() == initial_bytes
    assert derived.annotations[0].raw_value_json == '"Caso"'
    assert summary["correct"] == 0
    assert summary["denominator"] == 1
    assert summary["discovery_recall"] is None
    assert summary["synthetic"] is True
    assert summary["real_pi_review_claim"] is False
    assert summary["unprocessed_unit_ids"] == []
    assert derived.release == "internal_draft"


def test_assisted_review_is_distinct_and_machine_cannot_supply_pi_decision() -> None:
    envelope, candidate, _ = fixture()
    request = request_review(candidate, envelope, mode="assisted")
    assert request.candidate_annotations == candidate.annotations
    pi = decision(envelope, candidate, mode="assisted")
    assert pi.mode == "assisted"
    with pytest.raises(ValidationError):
        PIDecision.model_validate(pi.model_dump(mode="json") | {"mode": "machine_consensus"})
    with pytest.raises(ValueError, match="simulated"):
        derive_version(candidate, envelope, pi.model_copy(update={"simulated": False}), request)


def test_empty_output_is_incomplete_not_zero_or_accuracy() -> None:
    envelope, candidate, pages = fixture()
    empty = candidate.model_copy(update={"annotations": (), "processed_unit_ids": ()})
    issues = validate_candidate(empty, envelope, pages)
    assert any("unprocessed" in issue for issue in issues)
    assert any("missing" in issue for issue in issues)
    pi = decision(envelope, candidate)
    with pytest.raises(ValueError, match="candidate"):
        evaluate_initial(
            empty,
            envelope,
            pi,
            request_review(candidate, envelope, mode="source_first"),
            expected_reference_sha256=pi.fingerprint,
            expected_selection_sha256=envelope.selection_sha256,
        )


def test_reserved_material_cannot_become_worker_packet() -> None:
    envelope, _, _ = fixture()
    with pytest.raises(ValueError, match="reserved"):
        worker_packet(
            envelope.model_copy(update={"purpose": "reserved_evaluation"}),
            permitted_source_sha256=frozenset({"a" * 64}),
        )
    with pytest.raises(ValueError, match="permitted"):
        worker_packet(envelope, permitted_source_sha256=frozenset())
    packet = worker_packet(envelope, permitted_source_sha256=frozenset({"a" * 64}))
    assert set(packet) == {"run_id", "units", "neutral_rules"}
    assert not any(
        word in json.dumps(packet) for word in ("eligible_slots", "reference_annotations")
    )


def test_reference_and_selection_mismatch_and_incomplete_review_rejected() -> None:
    envelope, candidate, _ = fixture()
    request = request_review(candidate, envelope, mode="source_first")
    pi = decision(envelope, candidate)
    for key in ("expected_reference_sha256", "expected_selection_sha256"):
        kwargs = {
            "expected_reference_sha256": pi.fingerprint,
            "expected_selection_sha256": envelope.selection_sha256,
        }
        kwargs[key] = "f" * 64
        with pytest.raises(ValueError, match="identity"):
            evaluate_initial(candidate, envelope, pi, request, **kwargs)
    incomplete = pi.model_copy(update={"reference_annotations": ()})
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_initial(
            candidate,
            envelope,
            incomplete,
            request,
            expected_reference_sha256=incomplete.fingerprint,
            expected_selection_sha256=envelope.selection_sha256,
        )


def test_multi_anchor_bounds_and_report_context_not_silently_admitted() -> None:
    envelope, candidate, pages = fixture()
    annotation = candidate.annotations[0]
    two = annotation.model_copy(update={"evidence_anchors": annotation.evidence_anchors * 2})
    valid = candidate.model_copy(update={"annotations": (two,)})
    assert validate_candidate(valid, envelope, pages) == ()
    wrong = annotation.evidence_anchors[0].model_copy(update={"page": 2})
    invalid = candidate.model_copy(
        update={"annotations": (annotation.model_copy(update={"evidence_anchors": (wrong,)}),)}
    )
    with pytest.raises(ValueError, match="boundary"):
        validate_candidate(invalid, envelope, pages)
    out_of_bounds = annotation.evidence_anchors[0].model_copy(
        update={"source_span": SourceSpan(start=0, end=999)}
    )
    with pytest.raises(ValueError, match="span"):
        validate_candidate(
            candidate.model_copy(
                update={
                    "annotations": (
                        annotation.model_copy(update={"evidence_anchors": (out_of_bounds,)}),
                    )
                }
            ),
            envelope,
            pages,
        )


def test_scientific_field_types_and_incomplete_reference_cannot_finalize() -> None:
    envelope, candidate, pages = fixture()
    field = candidate.annotations[0]
    wrong = field.model_copy(update={"raw_value_json": "123"})
    with pytest.raises(ValueError, match="scientific"):
        validate_candidate(candidate.model_copy(update={"annotations": (wrong,)}), envelope, pages)
    unknown = field.model_copy(update={"field_name": "case_name.invented_field"})
    with pytest.raises(ValueError, match="scientific"):
        validate_candidate(
            candidate.model_copy(update={"annotations": (unknown,)}), envelope, pages
        )
    incomplete = candidate.model_copy(update={"processed_unit_ids": ()})
    request = request_review(incomplete, envelope, mode="source_first")
    pi = decision(envelope, incomplete)
    assert derive_version(incomplete, envelope, pi, request).processing == "requires_review"


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("violence_event.fatalities_total", "-1"),
        ("report.report_number", "0"),
        ("report.page_count", "0"),
    ],
)
def test_existing_scientific_field_constraints_are_not_dropped(field_name: str, value: str) -> None:
    envelope, candidate, pages = fixture()
    invalid = candidate.annotations[0].model_copy(
        update={
            "field_name": field_name,
            "raw_value_json": value,
        }
    )
    with pytest.raises(ValueError, match="scientific"):
        validate_candidate(
            candidate.model_copy(update={"annotations": (invalid,)}), envelope, pages
        )
