"""Invented consumer inputs; no report, machine or PI data."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from peru_conflicts.execution.aggregate_processing import parse_report_month_aggregate
from peru_conflicts.models import (
    MODEL_REGISTRY,
    SCHEMA_VERSION,
    ReportMonthAggregate,
    ReportMonthAggregateObservationV1,
    ReportRecord,
)


def payload(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_month_id": "invented:observation",
        "report_id": "invented:later-report",
        "metric_original": "Medida inventada — conservar literal",
        "indicator_basis": "source_reported",
        "value": 7,
        "provenance_ids": ["invented:anchor"],
        **changes,
    }


def consume(original: dict[str, Any]) -> ReportMonthAggregate:
    return parse_report_month_aggregate(json.dumps(original, ensure_ascii=False))


def test_actual_consumer_dispatch_preserves_legacy_and_explicit_extension() -> None:
    legacy = consume(payload())
    assert type(legacy) is ReportMonthAggregate
    original = payload(
        aggregate_contract="report_month_observation_v1", observation_period="2030-12"
    )
    before = copy.deepcopy(original)
    extended = consume(original)
    assert type(extended) is ReportMonthAggregateObservationV1
    assert extended.observation_period == "2030-12"
    assert original == before
    assert extended.metric_original == original["metric_original"]
    assert extended.report_id == "invented:later-report"
    assert MODEL_REGISTRY["report_month"] is ReportMonthAggregate


@pytest.mark.parametrize("contract", [None, "", "unknown", "report_month_observation_v2", 1])
def test_unknown_or_mismatched_contract_is_rejected(contract: Any) -> None:
    with pytest.raises(ValueError, match="contract"):
        consume(payload(aggregate_contract=contract))


@pytest.mark.parametrize("version", [None, "", "0.3.0", "0.3.2", "report_month_observation_v1", 1])
@pytest.mark.parametrize("extension", [False, True])
def test_consumer_requires_supported_explicit_base_version(version: Any, extension: bool) -> None:
    original = payload(schema_version=version)
    if extension:
        original["aggregate_contract"] = "report_month_observation_v1"
    with pytest.raises(ValueError, match="schema_version"):
        consume(original)


def test_missing_version_and_base_version_alone_do_not_infer_extension() -> None:
    original = payload()
    del original["schema_version"]
    with pytest.raises(ValueError, match="schema_version"):
        consume(original)
    with pytest.raises(ValidationError):
        consume(payload(observation_period="2030-12"))
    with pytest.raises(ValidationError):
        ReportMonthAggregate.model_validate(
            payload(aggregate_contract="report_month_observation_v1")
        )


def test_unspecified_month_stays_unknown_and_rollover_observations_stay_distinct() -> None:
    missing = consume(payload(aggregate_contract="report_month_observation_v1"))
    assert isinstance(missing, ReportMonthAggregateObservationV1)
    assert missing.observation_period is None
    months = ["2030-12", "2031-01"]
    records = [
        consume(payload(aggregate_contract="report_month_observation_v1", observation_period=month))
        for month in months
    ]
    assert records[0].value == records[1].value == 7
    assert [record.model_dump()["observation_period"] for record in records] == months
    assert records[0].model_dump() != records[1].model_dump()


@pytest.mark.parametrize(
    "changes",
    [
        {"observation_period": "0000-01"},
        {"observation_period": "2030-00"},
        {"observation_period": "2030-13"},
        {"observation_period": "2030-1"},
        {"observation_period": "\uff12\uff10\uff13\uff10-\uff11\uff12"},
        {"observation_period": "2030-12\n"},
        {"observation_period": 203012},
        {"value": float("inf")},
        {"value": [7]},
        {"value": {"number": 7}},
        {"unexpected": True},
        {"provenance_ids": []},
        {"derivation_name": "invented"},
        {"indicator_basis": "invented"},
    ],
)
def test_dispatch_preserves_runtime_type_month_and_source_guards(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        consume(payload(aggregate_contract="report_month_observation_v1", **changes))


def test_observation_month_does_not_replace_or_come_from_report_reference_month() -> None:
    report = ReportRecord.model_validate_json(
        json.dumps(
            {
                "report_id": "invented:later-report",
                "source_version_id": "invented:source",
                "reference_period": "2031-01",
                "reference_period_evidence_types": ["document_visible"],
                "reference_period_provenance_ids": ["invented:cover"],
                "source_filename": "invented.pdf",
                "sha256": "0" * 64,
                "byte_size": 0,
            }
        )
    )
    before = report.model_dump()
    observed = consume(
        payload(aggregate_contract="report_month_observation_v1", observation_period="2030-12")
    )
    unspecified = consume(payload(aggregate_contract="report_month_observation_v1"))
    assert observed.report_id == unspecified.report_id == report.report_id
    assert observed.model_dump()["observation_period"] == "2030-12"
    assert unspecified.model_dump()["observation_period"] is None
    assert report.reference_period == "2031-01"
    assert report.model_dump() == before


def test_derived_lineage_is_required_and_unknown_value_is_not_zero() -> None:
    original = payload(
        aggregate_contract="report_month_observation_v1",
        indicator_basis="derived",
        provenance_ids=[],
    )
    with pytest.raises(ValidationError, match="derived indicators require"):
        consume(original)
    original.update(
        derivation_name="invented_sum",
        derivation_version="v1",
        upstream_record_ids=["invented:input"],
        value=None,
    )
    assert consume(original).value is None


def cli_command() -> list[str]:
    root = Path(__file__).resolve().parents[2]
    return [
        sys.executable,
        "-I",
        "-B",
        "-c",
        "import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); "
        "runpy.run_path(sys.argv[1], run_name='__main__')",
        str(root / "src"),
        str(root / "scripts" / "validate_report_month.py"),
    ]


def test_versioned_stdin_consumer_runs_without_private_helper() -> None:
    original = payload(
        aggregate_contract="report_month_observation_v1", observation_period="2030-12"
    )
    raw = (json.dumps(original, ensure_ascii=False) + "\n").encode("utf-8")
    result = subprocess.run(cli_command(), input=raw, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    extended = ReportMonthAggregateObservationV1.model_validate_json(result.stdout)
    assert extended.observation_period == "2030-12"
    assert extended.metric_original == original["metric_original"]
    assert extended.value == 7
    assert extended.report_id == original["report_id"]
    assert raw == (json.dumps(original, ensure_ascii=False) + "\n").encode("utf-8")


@pytest.mark.parametrize(
    "raw", [b"[]", b"{", json.dumps(payload(observation_period="2030-12")).encode("utf-8")]
)
def test_invalid_cli_input_emits_no_normalized_derivative(raw: bytes) -> None:
    result = subprocess.run(cli_command(), input=raw, capture_output=True, timeout=10, check=False)
    assert result.returncode != 0
    assert not result.stdout
