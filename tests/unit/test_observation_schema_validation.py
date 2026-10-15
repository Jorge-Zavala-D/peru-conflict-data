"""Real, offline Draft 2020-12 checks of exported schemas using invented inputs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.protocols import Validator
from referencing import Registry
from referencing.exceptions import NoSuchResource
from test_aggregate_processing import consume, payload

from peru_conflicts.models import ReportMonthAggregate, ReportMonthAggregateObservationV1

ROOT = Path(__file__).resolve().parents[2]


def no_remote_resource(uri: str) -> Any:
    raise NoSuchResource(ref=uri)


def validator(extension: bool = True) -> Validator:
    relative = (
        "schemas/extensions/report_month_observation_v1.schema.json"
        if extension
        else "schemas/v0.3.1/report_month.schema.json"
    )
    schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)
    # Bundled fragment refs resolve locally; any other retrieval is refused.
    return Draft202012Validator(schema, registry=Registry(retrieve=no_remote_resource))


@pytest.mark.parametrize("month", [None, "0001-01", "2030-12", "2031-01", "9999-12"])
def test_exported_extension_accepts_supported_months_without_rewriting(month: str | None) -> None:
    original = payload(aggregate_contract="report_month_observation_v1", observation_period=month)
    before = copy.deepcopy(original)
    validator().validate(original)
    result = consume(original)
    assert isinstance(result, ReportMonthAggregateObservationV1)
    assert result.observation_period == month
    assert result.metric_original == original["metric_original"]
    assert result.value == original["value"]
    assert original == before


def test_exported_missing_month_stays_unspecified_and_equal_values_are_not_deduplicated() -> None:
    original = payload(aggregate_contract="report_month_observation_v1")
    validator().validate(original)
    assert consume(original).model_dump()["observation_period"] is None
    rows = [dict(original, observation_period=month) for month in ["2030-12", "2031-01"]]
    for row in rows:
        validator().validate(row)
    results = [consume(row).model_dump() for row in rows]
    assert [row["observation_period"] for row in results] == ["2030-12", "2031-01"]
    assert results[0]["value"] == results[1]["value"] == 7
    assert results[0]["report_id"] == results[1]["report_id"]
    assert results[0] != results[1]


@pytest.mark.parametrize(
    "changes",
    [
        {"observation_period": month}
        for month in [
            "0000-01",
            "2030-00",
            "2030-13",
            "2030-1",
            "2030",
            "2030-12-01",
            "\uff12\uff10\uff13\uff10-\uff11\uff12",
            "2030-12\n",
            203012,
        ]
    ]
    + [{"aggregate_contract": contract} for contract in [None, "unknown", 1]]
    + [{"schema_version": version} for version in [None, "0.3.0", "0.3.2", 1]]
    + [
        {"unexpected": True},
        {"value": [7]},
        {"value": {"number": 7}},
        {"provenance_ids": []},
        {"derivation_name": "invented"},
        {"indicator_basis": "invented"},
    ],
)
def test_exported_and_runtime_guards_reject_invalid_json_interface(changes: dict[str, Any]) -> None:
    original = payload(**{"aggregate_contract": "report_month_observation_v1", **changes})
    assert not validator().is_valid(original)
    with pytest.raises(ValueError):
        consume(original)


def test_exported_legacy_stays_legacy_and_extension_fields_are_not_dropped() -> None:
    original = payload()
    validator(False).validate(original)
    assert type(consume(original)) is ReportMonthAggregate
    extended = dict(
        original, aggregate_contract="report_month_observation_v1", observation_period="2030-12"
    )
    assert not validator(False).is_valid(extended)
    validator().validate(extended)
    del extended["aggregate_contract"]
    assert not validator(False).is_valid(extended)
    with pytest.raises(ValueError):
        consume(extended)


def test_schema_defaults_do_not_supply_consumer_dispatch_or_base_version() -> None:
    original = payload(
        aggregate_contract="report_month_observation_v1", observation_period="2030-12"
    )
    for key in ["aggregate_contract", "schema_version"]:
        omitted = dict(original)
        del omitted[key]
        validator().validate(omitted)
        assert key not in omitted
        with pytest.raises(ValueError):
            consume(omitted)


def test_derived_lineage_and_null_value_retain_existing_constraints() -> None:
    original = payload(
        aggregate_contract="report_month_observation_v1",
        indicator_basis="derived",
        provenance_ids=[],
        value=None,
    )
    assert not validator().is_valid(original)
    with pytest.raises(ValueError):
        consume(original)
    original.update(
        derivation_name="invented_sum",
        derivation_version="v1",
        upstream_record_ids=["invented:input"],
    )
    validator().validate(original)
    assert consume(original).value is None
