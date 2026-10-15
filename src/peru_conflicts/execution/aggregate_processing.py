"""Explicit, additive aggregate consumption; no scientific acceptance or imputation."""

from __future__ import annotations

import json
from typing import cast

from peru_conflicts.models import (
    SCHEMA_VERSION,
    ReportMonthAggregate,
    ReportMonthAggregateObservationV1,
)


def parse_report_month_aggregate(raw: str | bytes) -> ReportMonthAggregate:
    """Select a supported contract, then validate the unchanged JSON input."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("aggregate input must be one JSON object")
    payload = cast(dict[str, object], payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"aggregate schema_version must explicitly be {SCHEMA_VERSION}")
    if "aggregate_contract" not in payload:
        return ReportMonthAggregate.model_validate_json(raw)
    if payload["aggregate_contract"] != "report_month_observation_v1":
        raise ValueError("unsupported aggregate_contract")
    return ReportMonthAggregateObservationV1.model_validate_json(raw)
