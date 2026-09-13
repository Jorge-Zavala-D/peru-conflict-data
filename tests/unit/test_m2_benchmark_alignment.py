"""Invented execution inventories must supply complete benchmark instances."""

import importlib
import json

import pytest
from test_m2_annotation import discovered, form, populated, validate

from peru_conflicts.benchmark.models import PartitionRole
from peru_conflicts.execution import annotation


def invented_complete_population() -> dict[str, bytes]:
    """One invented case, two names/actors/locations/demands and every metric family."""
    package = populated()
    counts = {
        "case_name": 2,
        "actor": 2,
        "location": 2,
        "demand": 2,
        "protest_event": 1,
        "violence_event": 1,
        "dialogue_event": 1,
        "mediation_observation": 1,
        "agreement": 1,
        "dp_action": 1,
        "alert": 1,
    }
    package["objects.csv"] = form(
        "objects.csv",
        [
            {"discovery_id": "local-1", "object_family": family, "cardinality_index": str(i)}
            for family, count in counts.items()
            for i in range(count)
        ],
    )
    values = annotation.empty_slots(package)
    for value in values:
        value.update(state="not_reported", evidence_id="e1")
        field = value["field_name"]
        if field in {
            "actor.name_original",
            "case_actor.role_original",
            "location.location_text_original",
            "case_location.relationship_original",
            "demand.text_original",
            "case_name.name_original",
        }:
            value.update(
                state="observed",
                value_type="string",
                original_value=field + ": invented " + value["cardinality_index"],
            )
        if field in {"dp_action.action_date_original", "alert.alert_date_original"}:
            value.update(
                state="observed", value_type="string", original_value="15 de enero de 2026"
            )
        if field in {
            "dp_action.action_date_precision_original",
            "alert.alert_date_precision_original",
        }:
            value.update(state="observed", value_type="string", original_value="day")
        if field == "violence_event.fatalities_total":
            value.update(state="explicit_zero", value_type="number", original_value="0")
        if field == "violence_event.casualty_components":
            value.update(
                state="observed",
                value_type="json",
                original_value=json.dumps(
                    [{"component_original": "invented group", "fatalities": 0, "injured": None}]
                ),
            )
        if field == "alert.risk_original":
            value.update(state="not_applicable")
    package["annotations.csv"] = form("annotations.csv", values)
    inspection = annotation.rows(package, "inspection.csv")
    for row in inspection:
        row["zero_discoveries_confirmed"] = "false"
    package["inspection.csv"] = form("inspection.csv", inspection)
    return package


def test_complete_invented_human_forms_roundtrip_all_metric_families() -> None:
    from peru_conflicts.benchmark.metrics import evaluate_benchmark

    module = importlib.import_module("peru_conflicts.execution.benchmark_projection")
    package = invented_complete_population()
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    projection = module.project_synthetic_benchmark(draft)
    result = evaluate_benchmark(
        projection.critical_annotations,
        projection.critical_annotations,
        gold_objects=projection.objects,
        predicted_objects=projection.objects,
        evidence_requirements=projection.evidence_requirements,
        predicted_evidence=projection.evidence,
    )
    expected = {
        "actor": 2,
        "location": 2,
        "demand": 2,
        "case_observation": 1,
        "protest_event": 1,
        "violence_event": 1,
        "dialogue_event": 1,
        "mediation_observation": 1,
        "agreement": 1,
        "dp_action": 1,
        "alert": 1,
    }
    assert {name: len(objects) for name, objects in projection.objects.items()} == expected
    for name, metric in result.object_metrics:
        assert metric.true_positive == expected[name]
        assert metric.false_positive == metric.false_negative == 0
        assert metric.precision == metric.recall == 1.0
    assert result.strict_fields.strict_exact_accuracy == 1.0
    assert result.evidence.completeness == 1.0
    assert projection.objects["actor"][1]["role_original"] == "case_actor.role_original: invented 1"
    assert projection.objects["dp_action"][0]["action_date_original"] == "15 de enero de 2026"
    assert not any(
        a.field_name.split(".")[-1] == "action_date" for a in projection.critical_annotations
    )


def test_complete_case_requires_declared_name_instance() -> None:
    package = populated()
    package["objects.csv"] = form("objects.csv", [])
    values = annotation.rows(package, "annotations.csv")
    package["annotations.csv"] = form(
        "annotations.csv", [v for v in values if v["object_family"] != "case_name"]
    )
    with pytest.raises(ValueError, match="case name"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


@pytest.mark.parametrize(
    "state,value_type,value",
    [
        ("explicit_zero", "number", "0"),
        ("observed", "number", "1"),
    ],
)
def test_human_date_form_rejects_zero_and_non_string(
    state: str, value_type: str, value: str
) -> None:
    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    row = next(v for v in values if v["field_name"] == "dp_action.action_date_original")
    row.update(state=state, value_type=value_type, original_value=value)
    package["annotations.csv"] = form("annotations.csv", values)
    with pytest.raises(ValueError, match="date"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


def test_precision_without_source_date_fails_closed() -> None:
    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    row = next(v for v in values if v["field_name"] == "alert.alert_date_original")
    row.update(state="not_reported", value_type="", original_value="")
    package["annotations.csv"] = form("annotations.csv", values)
    with pytest.raises(ValueError, match="precision"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


@pytest.mark.parametrize(
    "state", ["source_ambiguous", "annotation_uncertain", "illegible_uninspectable"]
)
def test_unresolved_annotation_cannot_become_confident_projection(state: str) -> None:
    from peru_conflicts.execution.benchmark_projection import project_synthetic_benchmark

    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    row = next(v for v in values if v["field_name"] == "actor.name_original")
    row.update(
        state=state, value_type="", original_value="", comment="invented unresolved evidence"
    )
    package["annotations.csv"] = form("annotations.csv", values)
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    with pytest.raises(ValueError, match="unresolved"):
        project_synthetic_benchmark(draft)


def test_crosswalk_refuses_an_unreviewed_field(monkeypatch: pytest.MonkeyPatch) -> None:
    from peru_conflicts.execution import benchmark_projection as bridge

    monkeypatch.setitem(bridge.OBJECT_MATCH_FIELDS, "actor", ("name_original", "invented_field"))
    with pytest.raises(ValueError, match="crosswalk"):
        bridge.field_crosswalk()


@pytest.mark.parametrize(
    "field", ["case_actor.role_original", "case_location.relationship_original"]
)
def test_missing_relational_slot_cannot_be_repaired_by_index(field: str) -> None:
    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    package["annotations.csv"] = form(
        "annotations.csv", [v for v in values if v["field_name"] != field]
    )
    with pytest.raises(ValueError, match="slot incomplete"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


def test_source_only_actor_cannot_claim_a_case_role() -> None:
    package = populated()
    source = annotation.rows(package, "discoveries.csv")[0]
    source.update(object_family="actor", unit_type="source_only_object")
    package["discoveries.csv"] = form("discoveries.csv", [source])
    package["objects.csv"] = form("objects.csv", [])
    slots = annotation.empty_slots(package)
    for slot in slots:
        slot.update(state="not_reported", evidence_id="e1")
    next(s for s in slots if s["field_name"] == "case_actor.role_original").update(
        state="observed", value_type="string", original_value="invented case role"
    )
    package["annotations.csv"] = form("annotations.csv", slots)
    with pytest.raises(ValueError, match="case scope"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT})


@pytest.mark.parametrize(
    "source,precision",
    [("15/01/2026", "day"), ("enero de 2026", "month"), ("2026", "year"), ("2026-01-15", "day")],
)
def test_date_forms_to_projection_preserve_exact_text(source: str, precision: str) -> None:
    from peru_conflicts.execution.benchmark_projection import project_synthetic_benchmark

    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    for row in values:
        if row["field_name"] == "dp_action.action_date_original":
            row["original_value"] = source
        if row["field_name"] == "dp_action.action_date_precision_original":
            row["original_value"] = precision
    package["annotations.csv"] = form("annotations.csv", values)
    result = project_synthetic_benchmark(
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    )
    assert result.objects["dp_action"][0]["action_date_original"] == source
    assert result.objects["dp_action"][0]["action_date_precision_original"] == precision
    assert "action_date" not in result.objects["dp_action"][0]


@pytest.mark.parametrize("state", ["not_reported", "not_applicable", "structurally_unavailable"])
def test_date_absence_has_null_projection_but_retains_annotation_state(state: str) -> None:
    from peru_conflicts.execution.benchmark_projection import project_synthetic_benchmark

    package = invented_complete_population()
    values = annotation.rows(package, "annotations.csv")
    for row in values:
        if row["field_name"] in {
            "alert.alert_date_original",
            "alert.alert_date_precision_original",
        }:
            row.update(state=state, value_type="", original_value="")
    package["annotations.csv"] = form("annotations.csv", values)
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    result = project_synthetic_benchmark(draft)
    assert result.objects["alert"][0]["alert_date_original"] is None
    assert result.objects["alert"][0]["alert_date_precision_original"] is None
    assert (
        next(
            a
            for a in draft.submissions[0].annotations
            if a.field_name == "alert.alert_date_original"
        ).state.value
        == state
    )


@pytest.mark.parametrize(
    "family,component",
    [("actor", "case_actor.role_original"), ("location", "case_location.relationship_original")],
)
def test_relational_component_belongs_to_same_human_instance(family: str, component: str) -> None:
    assert component in annotation.required_fields(family)


@pytest.mark.parametrize("family", ["case_month", "case_actor", "case_location"])
def test_no_independent_month_or_relational_cardinality_space(family: str) -> None:
    package = discovered()
    package["objects.csv"] = form(
        "objects.csv",
        [{"discovery_id": "local-1", "object_family": family, "cardinality_index": "4"}],
    )
    with pytest.raises(ValueError):
        annotation.empty_slots(package)


def test_names_are_repeated_instances_not_a_hidden_primary_name() -> None:
    assert "case_name.name_original" not in annotation.required_fields("case_observation")
    assert annotation.required_fields("case_name") == ("case_name.name_original",)


@pytest.mark.parametrize(
    "family",
    [
        "actor",
        "location",
        "demand",
        "protest_event",
        "violence_event",
        "dialogue_event",
        "mediation_observation",
        "agreement",
        "dp_action",
        "alert",
    ],
)
def test_subordinate_objects_invalidate_false_zero_inspection(family: str) -> None:
    package = populated()
    package["objects.csv"] = form(
        "objects.csv",
        [{"discovery_id": "local-1", "object_family": family, "cardinality_index": "2"}],
    )
    values = annotation.empty_slots(package)
    for value in values:
        value.update(state="not_reported", evidence_id="e1")
    package["annotations.csv"] = form("annotations.csv", values)
    with pytest.raises(ValueError, match="inspection incomplete"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


@pytest.mark.parametrize(
    "family,field", [("actor", "role_original"), ("location", "relationship_original")]
)
def test_relational_values_cannot_migrate_without_object_penalties(family: str, field: str) -> None:
    from peru_conflicts.benchmark.metrics import OBJECT_MATCH_FIELDS, multiset_object_metrics
    from peru_conflicts.execution.benchmark_projection import project_synthetic_benchmark

    draft = validate(
        invented_complete_population(), {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True
    )
    objects = project_synthetic_benchmark(draft).objects[family]
    swapped = [objects[0] | {field: objects[1][field]}, objects[1] | {field: objects[0][field]}]
    result = multiset_object_metrics(objects, swapped, match_fields=OBJECT_MATCH_FIELDS[family])
    assert result.true_positive == 0
    assert result.false_positive == result.false_negative == 2


def test_projection_rejects_uninspected_empty_family() -> None:
    from peru_conflicts.execution.benchmark_projection import project_synthetic_benchmark

    package = populated()
    package["inspection.csv"] = form("inspection.csv", [])
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT})
    with pytest.raises(ValueError, match="inspection"):
        project_synthetic_benchmark(draft)
