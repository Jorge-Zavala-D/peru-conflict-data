"""Historical byte custody and the owner's closed additive date correction."""

import ast
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from peru_conflicts.benchmark import metrics
from peru_conflicts.benchmark.schema_export import rendered_benchmark_schemas
from peru_conflicts.schema_export import rendered_schemas

ROOT = Path(__file__).resolve().parents[2]


def tree_digest(folder: Path) -> str:
    return hashlib.sha256(
        "\n".join(
            f"{p.name}:{hashlib.sha256(p.read_bytes()).hexdigest()}"
            for p in sorted(folder.glob("*.schema.json"))
        ).encode()
    ).hexdigest()


def assert_metric_correction_scope() -> None:
    tree = ast.parse((ROOT / "src/peru_conflicts/benchmark/metrics.py").read_bytes())
    algorithms = ast.Module(
        body=[n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))],
        type_ignores=[],
    )
    assert hashlib.sha256(ast.dump(algorithms, include_attributes=False).encode()).hexdigest() == (
        "d0e51dca0bf146a3cd6e9d4e905d7604a092852866b426474fab70725756846c"
    )
    old, new = metrics.OBJECT_MATCH_FIELDS_V010, metrics.OBJECT_MATCH_FIELDS_V011
    assert metrics.CURRENT_BENCHMARK_METRIC_CONTRACT_VERSION == "0.1.1"
    assert metrics.OBJECT_MATCH_FIELDS is new
    assert set(old) == set(new)
    assert {f for f in old if old[f] != new[f]} == {"dp_action", "alert"}
    for family, prefix in (("dp_action", "action"), ("alert", "alert")):
        assert old[family][0] == f"{prefix}_date"
        assert new[family] == (
            f"{prefix}_date_original",
            f"{prefix}_date_precision_original",
            *old[family][1:],
        )


def test_only_owner_authorized_metric_fields_changed_not_arithmetic() -> None:
    assert_metric_correction_scope()


def test_historical_schemas_remain_exact() -> None:
    assert (
        tree_digest(ROOT / "schemas/v0.3.0")
        == "cd5bdea78e6314242685ea89d43850f8ff42e639ba74606aba3d929b2e81444d"
    )
    assert (
        tree_digest(ROOT / "schemas/benchmark/v0.1.0")
        == "23a5ee953541c93b9e51898872901f8b9432588f8c9ea03758ea85a5a1ff28fa"
    )


def test_scientific_successor_changes_only_four_optional_fields_and_version() -> None:
    for name, text in rendered_schemas().items():
        normalized = json.loads(text.replace("0.3.1", "0.3.0"))
        prefix = {"dp_action.schema.json": "action", "alert.schema.json": "alert"}.get(name)
        if prefix:
            for field in (f"{prefix}_date_original", f"{prefix}_date_precision_original"):
                prop = normalized["properties"].pop(field)
                assert prop["anyOf"] == [{"type": "string"}, {"type": "null"}]
                assert prop["default"] is None
                assert field not in normalized["required"]
        assert normalized == json.loads((ROOT / "schemas/v0.3.0" / name).read_bytes())


def test_benchmark_successor_preserves_structure_except_version_identity() -> None:
    for name, text in rendered_benchmark_schemas().items():
        assert json.loads(text.replace("0.1.1", "0.1.0")) == json.loads(
            (ROOT / "schemas/benchmark/v0.1.0" / name).read_bytes()
        )


@pytest.mark.parametrize("family,field", [("dp_action", "action_date"), ("alert", "alert_date")])
def test_historical_date_contract_rejects_source_prose_and_mismatches_iso(
    family: str, field: str
) -> None:
    schema = json.loads((ROOT / f"schemas/v0.3.0/{family}.schema.json").read_bytes())
    assert schema["properties"][field]["anyOf"][0]["format"] == "date"
    with pytest.raises(ValidationError):
        TypeAdapter(date).validate_json('"15 de enero de 2026"')
    fields = metrics.OBJECT_MATCH_FIELDS_V010[family]
    old = dict.fromkeys(fields)
    old[field] = "15 de enero de 2026"
    result = metrics.multiset_object_metrics(
        [old], [old | {field: "2026-01-15"}], match_fields=fields
    )
    assert (result.true_positive, result.false_positive, result.false_negative) == (0, 1, 1)


def test_owner_correction_does_not_approve_readiness_or_expand_critical_set() -> None:
    record = yaml.safe_load(
        (ROOT / "config/benchmark/m2_01_date_semantics_correction_approval_v1.yaml").read_bytes()
    )
    assert record["owner"] == "Jorge Zavala"
    assert record["approval_id"] == "M2-DATE-SOURCE-PRESERVATION-CORRECTION-V1"
    assert datetime.fromisoformat(record["recorded_at"]).utcoffset() is not None
    assert record["reviewed_head"] == "38433b5f0e682513f76c28f38db55140b6b3a014"
    assert record["reviewed_tree"] == "11886ec7f81b391bb8c69305049e3f78f5eabffb"
    assert set(record["new_source_fields"]) == {
        "DefensoriaAction.action_date_original",
        "DefensoriaAction.action_date_precision_original",
        "Alert.alert_date_original",
        "Alert.alert_date_precision_original",
    }
    assert record["retained_derivative_fields"] == [
        "DefensoriaAction.action_date",
        "Alert.alert_date",
    ]
    for key in (
        "critical_field_set_expanded",
        "readiness_approved",
        "annotation_launch_approved",
        "human_gold_created",
        "m3_approved",
        "evaluator_arithmetic_changed",
    ):
        assert record[key] is False
    config = yaml.safe_load((ROOT / "config/benchmark/m2_critical_fields_v1.yaml").read_bytes())
    assert sum(len(g["fields"]) for g in config["source_value_critical"].values()) == 40


def test_current_readiness_index_binds_active_contracts_without_approval() -> None:
    from peru_conflicts.execution.evidence_index import (
        AlignmentEvidenceIndex,
        validate_evidence_index,
    )

    index = validate_evidence_index(
        (ROOT / "docs/m2_02a_readiness_evidence_index_v2.yaml").read_bytes()
    )
    assert isinstance(index, AlignmentEvidenceIndex)
    config = yaml.safe_load((ROOT / "config/benchmark/m2_02a_readiness_v2.yaml").read_bytes())
    assert config["benchmark_schema"] == "v0.1.1"
    assert config["scientific_schema"] == "v0.3.1"
    assert (
        index.benchmark_digest
        == config["benchmark_digest"]
        == tree_digest(ROOT / "schemas/benchmark/v0.1.1")
    )
    assert (
        index.scientific_digest
        == config["scientific_digest"]
        == tree_digest(ROOT / "schemas/v0.3.1")
    )
    assert (
        index.evaluator_sha256
        == config["normative_evaluator_sha256"]
        == hashlib.sha256(
            (ROOT / "src/peru_conflicts/benchmark/metrics.py").read_bytes()
        ).hexdigest()
    )
    assert index.owner_readiness_approved is config["owner_readiness_approved"] is False
    assert index.correction.pending_readiness_decisions == 15
    assert (
        index.correction.owner_correction_sha256
        == hashlib.sha256(
            (
                ROOT / "config/benchmark/m2_01_date_semantics_correction_approval_v1.yaml"
            ).read_bytes()
        ).hexdigest()
    )
