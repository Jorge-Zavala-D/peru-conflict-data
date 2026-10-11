from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from peru_conflicts import schema_export
from peru_conflicts.models import domain


def source_payload(**changes: Any) -> dict[str, Any]:
    return {
        "report_month_id": "synthetic:observation:1",
        "report_id": "synthetic:report:later",
        "metric_original": "Conteo inventado",
        "indicator_basis": "source_reported",
        "value": 3,
        "provenance_ids": ["synthetic:anchor:1"],
        **changes,
    }


def successor() -> type[domain.ReportMonthAggregate]:
    return domain.ReportMonthAggregateObservationV1


def test_historical_month_survives_later_report_serialization() -> None:
    record = successor().model_validate_json(
        json.dumps(source_payload(observation_period="2025-11"))
    )
    reloaded = successor().model_validate_json(record.model_dump_json())
    assert reloaded.model_dump()["observation_period"] == "2025-11"
    assert reloaded.report_id == "synthetic:report:later"


def test_legacy_contract_still_refuses_separate_month() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        domain.ReportMonthAggregate.model_validate_json(
            json.dumps(source_payload(observation_period="2025-11"))
        )


@pytest.mark.parametrize("period", ["2025-11", "2026-02", "9999-12", None])
def test_supported_month_is_explicitly_preserved(period: str | None) -> None:
    record = successor().model_validate_json(json.dumps(source_payload(observation_period=period)))
    assert record.model_dump()["observation_period"] == period
    assert record.model_dump()["aggregate_contract"] == "report_month_observation_v1"


def test_explicit_legacy_conversion_never_imputes_period() -> None:
    legacy = domain.ReportMonthAggregate.model_validate_json(json.dumps(source_payload()))
    record = successor().model_validate(legacy.model_dump())
    assert record.model_dump()["observation_period"] is None
    assert record.value == 3
    assert record.report_id == "synthetic:report:later"


@pytest.mark.parametrize(
    "period",
    [
        "2025-00",
        "2025-13",
        "0000-01",
        "2025-2",
        "2025-02-01",
        "\uff12\uff10\uff12\uff15-\uff10\uff12",
        "2025-02\n",
        "",
        202502,
        0,
        True,
    ],
)
def test_invalid_or_coerced_observation_month_is_rejected(period: Any) -> None:
    with pytest.raises(ValidationError):
        successor().model_validate_json(json.dumps(source_payload(observation_period=period)))


@pytest.mark.parametrize(
    "changes",
    [
        {"provenance_ids": []},
        {"derivation_name": "not-permitted"},
        {"derivation_version": "not-permitted"},
        {"upstream_record_ids": ["not-permitted"]},
        {"unexpected": "not-permitted"},
        {"value": float("inf")},
        {"aggregate_contract": "legacy"},
    ],
)
def test_extension_keeps_source_and_strict_guards(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        successor().model_validate_json(json.dumps(source_payload(**changes)))


def test_derived_controls_still_require_calculation_and_upstream_lineage() -> None:
    payload = source_payload(indicator_basis="derived", provenance_ids=[])
    with pytest.raises(ValidationError, match="derived indicators require"):
        successor().model_validate_json(json.dumps(payload))
    payload.update(
        derivation_name="synthetic_sum",
        derivation_version="v1",
        upstream_record_ids=["synthetic:input"],
    )
    assert (
        successor().model_validate_json(json.dumps(payload)).indicator_basis
        == domain.IndicatorBasis.DERIVED
    )


def test_missing_value_stays_unknown_not_zero() -> None:
    record = successor().model_validate_json(json.dumps(source_payload(value=None)))
    assert record.value is None


def test_month_field_runtime_matches_exported_keyword_constraints() -> None:
    schemas = schema_export.rendered_observation_schemas()
    assert "report_month_observation_v1.schema.json" in schemas
    schema = json.loads(schemas["report_month_observation_v1.schema.json"])
    month = schema["properties"]["observation_period"]["anyOf"][0]
    cases = [
        None,
        "2025-11",
        "9999-12",
        "0000-01",
        "2025-00",
        "2025-13",
        "2025-2",
        "2025-02-01",
        "\uff12\uff10\uff12\uff15-\uff10\uff12",
        "2025-02\n",
        202502,
        True,
    ]
    for value in cases:
        schema_accepts = value is None or (
            isinstance(value, str)
            and month["minLength"] <= len(value) <= month["maxLength"]
            and re.search(month["pattern"], value) is not None
            and re.search(month["not"]["pattern"], value) is None
        )
        try:
            successor().model_validate_json(json.dumps(source_payload(observation_period=value)))
        except ValidationError:
            runtime_accepts = False
        else:
            runtime_accepts = True
        assert schema_accepts == runtime_accepts, value


def test_extension_schema_currentness_refuses_missing_and_drift(tmp_path: Path) -> None:
    current = schema_export.observation_schemas_are_current
    export = schema_export.export_observation_schemas
    assert current(tmp_path) is False
    written = export(tmp_path)
    assert len(written) == 1
    assert current(tmp_path) is True
    assert written[0].parent == tmp_path / "extensions"
    first = written[0].read_bytes()
    export(tmp_path)
    assert written[0].read_bytes() == first
    written[0].write_bytes(first + b" ")
    assert current(tmp_path) is False


def test_all_legacy_scientific_schema_bytes_remain_unchanged() -> None:
    root = Path(__file__).resolve().parents[2]
    for name, content in schema_export.rendered_schemas().items():
        assert (root / "schemas" / "v0.3.1" / name).read_bytes() == content.encode("utf-8")


def test_extension_schema_retains_legacy_indicator_basis_guards() -> None:
    extension = json.loads(
        schema_export.rendered_observation_schemas()["report_month_observation_v1.schema.json"]
    )
    legacy = json.loads(schema_export.rendered_schemas()["report_month.schema.json"])
    assert extension["allOf"] == legacy["allOf"]
    assert extension["additionalProperties"] is False
    assert extension["$id"].endswith("/schemas/extensions/report_month_observation_v1.schema.json")
    assert extension["properties"]["aggregate_contract"]["const"] == "report_month_observation_v1"
