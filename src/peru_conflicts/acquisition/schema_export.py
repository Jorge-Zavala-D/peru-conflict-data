"""Deterministic JSON Schema export for the acquisition contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from peru_conflicts.acquisition.models import (
    AcquisitionAttemptReceipt,
    AcquisitionFailureReceipt,
    AcquisitionPilotPlan,
    DryRunResult,
    NetworkAuthorizationArtifact,
    OperationalLedgerRecord,
)
from peru_conflicts.acquisition.plan import (
    REVIEWED_V2_PLAN_FILE_SHA256,
    load_reviewed_pilot_plan,
)

ACQUISITION_SCHEMA_VERSION = "0.1.0"
PILOT_SCHEMA_FILENAME = "pilot_acquisition_plan.schema.json"
DRY_RUN_SCHEMA_FILENAME = "dry_run_result.schema.json"
AUTHORIZATION_SCHEMA_FILENAME = "network_authorization_artifact.schema.json"
ATTEMPT_SCHEMA_FILENAME = "acquisition_attempt_receipt.schema.json"
FAILURE_SCHEMA_FILENAME = "acquisition_failure_receipt.schema.json"
LEDGER_SCHEMA_FILENAME = "operational_ledger_record.schema.json"


def _harden_safe_response_header_definition(schema: dict[str, object]) -> None:
    definitions = cast(dict[str, object], schema["$defs"])
    safe_headers = cast(dict[str, object], definitions["SafeResponseHeaders"])
    safe_headers["allOf"] = [
        {
            "if": {
                "required": ["location_sanitized"],
                "properties": {"location_sanitized": {"type": "string"}},
            },
            "then": {
                "required": ["location_sha256"],
                "properties": {"location_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}},
            },
        },
        {
            "if": {
                "required": ["location_sha256"],
                "properties": {"location_sha256": {"type": "string"}},
            },
            "then": {
                "required": ["location_sanitized"],
                "properties": {"location_sanitized": {"type": "string", "minLength": 1}},
            },
        },
    ]


def _attempt_schema() -> dict[str, object]:
    schema = AcquisitionAttemptReceipt.model_json_schema(mode="validation")
    _harden_safe_response_header_definition(schema)
    shared_failure = {
        "required": ["error_code"],
        "properties": {
            "error_code": {"type": "string", "minLength": 1},
            "complete_body_sha256": {"const": None},
            "redirect_target_url": {"const": None},
        },
    }
    schema["allOf"] = [
        {
            "if": {"properties": {"outcome": {"const": "success"}}},
            "then": {
                "required": ["status_code", "complete_body_sha256"],
                "properties": {
                    "status_code": {"type": "integer", "minimum": 200, "maximum": 299},
                    "complete_body_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "redirect_target_url": {"const": None},
                    "error_code": {"const": None},
                    "error_message": {"const": None},
                },
            },
        },
        {
            "if": {"properties": {"outcome": {"const": "redirect"}}},
            "then": {
                "required": ["status_code", "redirect_target_url", "response_headers"],
                "properties": {
                    "status_code": {"enum": [301, 302, 303, 307, 308]},
                    "redirect_target_url": {"type": "string", "minLength": 1},
                    "complete_body_sha256": {"const": None},
                    "error_code": {"const": None},
                    "error_message": {"const": None},
                    "transferred_bytes": {"const": 0},
                    "response_headers": {
                        "allOf": [
                            {"$ref": "#/$defs/SafeResponseHeaders"},
                            {
                                "required": ["location_sanitized", "location_sha256"],
                                "properties": {
                                    "location_sanitized": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "location_sha256": {
                                        "type": "string",
                                        "pattern": "^[a-f0-9]{64}$",
                                    },
                                },
                            },
                        ]
                    },
                },
            },
        },
        *[
            {
                "if": {"properties": {"outcome": {"const": outcome}}},
                "then": shared_failure,
            }
            for outcome in ("retryable_failure", "rejected", "interrupted")
        ],
    ]
    return schema


def _null_properties(*names: str) -> dict[str, object]:
    return {name: {"const": None} for name in names}


def _failure_schema() -> dict[str, object]:
    schema = AcquisitionFailureReceipt.model_json_schema(mode="validation")
    schema["allOf"] = [
        {
            "if": {
                "properties": {"stage": {"enum": ["robots_body", "response_close", "temp_cleanup"]}}
            },
            "then": {
                "required": ["related_attempt_id"],
                "properties": {"related_attempt_id": {"type": "string", "minLength": 1}},
            },
        },
        {
            "if": {"properties": {"stage": {"const": "robots_policy"}}},
            "then": {"properties": {"related_attempt_id": {"const": None}}},
        },
    ]
    return schema


def _ledger_schema() -> dict[str, object]:
    schema = OperationalLedgerRecord.model_json_schema(mode="validation")
    _harden_safe_response_header_definition(schema)
    properties = cast(dict[str, object], schema["properties"])
    local_path = cast(dict[str, object], properties["local_relative_path"])
    alternatives = cast(list[object], local_path["anyOf"])
    string_path = cast(dict[str, object], alternatives[0])
    string_path["pattern"] = (
        r"^01_raw/reports/(?!\.{1,2}(?:/|$))(?!.*\/\.{1,2}(?:/|$))"
        r"(?!.*//)(?!.*[\\:])[^/]+(?:/[^/]+)*$"
    )
    evidence = (
        "report_number",
        "url_role",
        "normalized_url",
        "observed_sha256",
        "observed_bytes",
        "expected_source_sha256",
        "disposition",
        "version_relationship",
        "local_relative_path",
        "source_attempt_id",
        "collision_evidence_summary",
    )
    schema["allOf"] = [
        {
            "if": {"properties": {"record_type": {"const": "attempt"}}},
            "then": {
                "required": ["attempt"],
                "properties": {
                    "attempt": {"not": {"type": "null"}},
                    "failure": {"const": None},
                    "terminal_status": {"const": None},
                    **_null_properties(*evidence),
                },
            },
        },
        {
            "if": {"properties": {"record_type": {"const": "failure"}}},
            "then": {
                "required": ["failure"],
                "properties": {
                    "failure": {"not": {"type": "null"}},
                    "attempt": {"const": None},
                    "terminal_status": {"const": None},
                    **_null_properties(*evidence),
                },
            },
        },
        {
            "if": {"properties": {"record_type": {"const": "url_observation"}}},
            "then": {
                "required": [
                    "report_number",
                    "url_role",
                    "normalized_url",
                    "observed_sha256",
                    "observed_bytes",
                    "expected_source_sha256",
                    "disposition",
                    "version_relationship",
                    "local_relative_path",
                    "source_attempt_id",
                ],
                "properties": {
                    "attempt": {"const": None},
                    "failure": {"const": None},
                    "terminal_status": {"const": None},
                    "collision_evidence_summary": {"const": None},
                    "disposition": {"const": "identical_no_duplicate_raw_file"},
                    "version_relationship": {"const": "identical_bytes"},
                },
            },
        },
        {
            "if": {"properties": {"record_type": {"const": "byte_object"}}},
            "then": {
                "required": ["observed_sha256", "observed_bytes"],
                "properties": {
                    "attempt": {"const": None},
                    "failure": {"const": None},
                    "terminal_status": {"const": None},
                    **_null_properties(
                        "report_number",
                        "url_role",
                        "normalized_url",
                        "expected_source_sha256",
                        "disposition",
                        "version_relationship",
                        "local_relative_path",
                        "source_attempt_id",
                        "collision_evidence_summary",
                    ),
                },
            },
        },
        {
            "if": {"properties": {"record_type": {"const": "collision"}}},
            "then": {
                "required": [
                    "report_number",
                    "url_role",
                    "normalized_url",
                    "observed_sha256",
                    "observed_bytes",
                    "expected_source_sha256",
                    "disposition",
                    "version_relationship",
                    "local_relative_path",
                    "source_attempt_id",
                    "collision_evidence_summary",
                ],
                "properties": {
                    "attempt": {"const": None},
                    "failure": {"const": None},
                    "terminal_status": {"const": None},
                    "disposition": {"const": "stop_for_review"},
                    "version_relationship": {"const": "candidate_alternate_official_bytes"},
                },
            },
        },
        {
            "if": {"properties": {"record_type": {"const": "run_terminal"}}},
            "then": {
                "required": ["terminal_status"],
                "properties": {
                    "attempt": {"const": None},
                    "failure": {"const": None},
                    **_null_properties(*evidence),
                },
            },
        },
    ]
    attempt = _attempt_schema()
    attempt.pop("$defs", None)
    failure = _failure_schema()
    failure.pop("$defs", None)
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    definitions["AcquisitionAttemptReceipt"] = attempt
    definitions["AcquisitionFailureReceipt"] = failure
    return schema


def rendered_acquisition_schemas() -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[3]
    reviewed = load_reviewed_pilot_plan(
        repository_root / "config" / "acquisition_pilots" / "m1_03_reports_260_269_v2.yaml",
        required_sha256=REVIEWED_V2_PLAN_FILE_SHA256,
    ).plan.model_dump(mode="json")
    plan_schema = AcquisitionPilotPlan.model_json_schema(mode="validation")
    plan_schema["const"] = reviewed
    models = {
        PILOT_SCHEMA_FILENAME: plan_schema,
        DRY_RUN_SCHEMA_FILENAME: DryRunResult.model_json_schema(mode="validation"),
        AUTHORIZATION_SCHEMA_FILENAME: NetworkAuthorizationArtifact.model_json_schema(
            mode="validation"
        ),
        ATTEMPT_SCHEMA_FILENAME: _attempt_schema(),
        FAILURE_SCHEMA_FILENAME: _failure_schema(),
        LEDGER_SCHEMA_FILENAME: _ledger_schema(),
    }
    for filename, schema in models.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/acquisition/v{ACQUISITION_SCHEMA_VERSION}/{filename}"
        )
    return {
        filename: json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        for filename, schema in models.items()
    }


def export_acquisition_schemas(output_dir: Path) -> list[Path]:
    version_dir = output_dir / "acquisition" / f"v{ACQUISITION_SCHEMA_VERSION}"
    version_dir.mkdir(parents=True, exist_ok=True)
    expected = rendered_acquisition_schemas()
    for stale in version_dir.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()
    written: list[Path] = []
    for filename, content in expected.items():
        destination = version_dir / filename
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def acquisition_schemas_are_current(output_dir: Path) -> bool:
    version_dir = output_dir / "acquisition" / f"v{ACQUISITION_SCHEMA_VERSION}"
    expected = rendered_acquisition_schemas()
    existing = {path.name for path in version_dir.glob("*.schema.json")}
    if existing != set(expected):
        return False
    return all(
        (version_dir / filename).read_text(encoding="utf-8") == content
        for filename, content in expected.items()
    )
