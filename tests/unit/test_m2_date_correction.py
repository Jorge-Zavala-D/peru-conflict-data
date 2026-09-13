"""Invented source dates remain transcription, never implicit parsed derivatives."""

import json

import pytest

from peru_conflicts.benchmark.metrics import OBJECT_MATCH_FIELDS
from peru_conflicts.execution.annotation import required_fields
from peru_conflicts.models.domain import Alert, DefensoriaAction


@pytest.mark.parametrize("family,prefix", [("dp_action", "action"), ("alert", "alert")])
def test_later_parsed_derivative_cannot_change_source_signature(family: str, prefix: str) -> None:
    from peru_conflicts.benchmark.metrics import multiset_object_metrics

    model = DefensoriaAction if family == "dp_action" else Alert
    identity = "dp_action_id" if family == "dp_action" else "alert_id"
    raw = {
        identity: "invented",
        "report_id": "invented-report",
        f"{prefix}_date_original": "enero de 2026",
        f"{prefix}_date_precision_original": "month",
    }
    source = model.model_validate_json(json.dumps(raw)).model_dump(mode="json")
    derivative = model.model_validate_json(
        json.dumps(raw | {f"{prefix}_date": "2026-01-15"})
    ).model_dump(mode="json")
    fields = OBJECT_MATCH_FIELDS[family]
    result = multiset_object_metrics(
        [{k: source[k] for k in fields}],
        [{k: derivative[k] for k in fields}],
        match_fields=fields,
    )
    assert result.true_positive == 1
    assert result.false_positive == result.false_negative == 0


@pytest.mark.parametrize(
    "model,family,prefix,id_field",
    [
        (DefensoriaAction, "dp_action", "action", "dp_action_id"),
        (Alert, "alert", "alert", "alert_id"),
    ],
)
@pytest.mark.parametrize(
    "source,precision",
    [
        ("15/01/2026", "day"),
        ("15 de enero de 2026", "day"),
        ("enero de 2026", "month"),
        ("2026", "year"),
        ("2026-01-15", "day"),
    ],
)
def test_source_date_is_preserved_without_parsing(
    model: type[DefensoriaAction] | type[Alert],
    family: str,
    prefix: str,
    id_field: str,
    source: str,
    precision: str,
) -> None:
    value = model.model_validate_json(
        json.dumps(
            {
                id_field: "invented",
                "report_id": "invented-report",
                f"{prefix}_date_original": source,
                f"{prefix}_date_precision_original": precision,
            }
        )
    )
    assert getattr(value, f"{prefix}_date_original") == source
    assert getattr(value, f"{prefix}_date_precision_original") == precision
    assert getattr(value, f"{prefix}_date") is None


@pytest.mark.parametrize("family,prefix", [("dp_action", "action"), ("alert", "alert")])
def test_source_date_slots_and_matching_exclude_parsed_derivatives(
    family: str, prefix: str
) -> None:
    for field in (f"{prefix}_date_original", f"{prefix}_date_precision_original"):
        assert f"{family}.{field}" in required_fields(family)
        assert field in OBJECT_MATCH_FIELDS[family]
    assert f"{prefix}_date" not in OBJECT_MATCH_FIELDS[family]
    assert f"{family}.{prefix}_date" not in required_fields(family)
