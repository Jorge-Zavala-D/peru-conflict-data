"""Deterministic JSON Schema export for provisional discovery records."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.discovery.models import DISCOVERY_SCHEMA_VERSION, ProvisionalDiscoveryRecord
from peru_conflicts.discovery.pilot import PilotAcquisitionPlan, load_pilot_acquisition_plan
from peru_conflicts.discovery.receipts import ReconnaissanceSummary, RequestAttemptReceipt

DISCOVERY_SCHEMA_FILENAME = "provisional_discovery_record.schema.json"
REQUEST_RECEIPT_SCHEMA_FILENAME = "request_attempt_receipt.schema.json"
RECONNAISSANCE_SUMMARY_SCHEMA_FILENAME = "reconnaissance_summary.schema.json"
PILOT_ACQUISITION_PLAN_SCHEMA_FILENAME = "pilot_acquisition_plan.schema.json"


def _qualified_evidence_condition(
    *, candidate_field: str, candidate_type: str, subject: str
) -> dict[str, object]:
    return {
        "if": {
            "properties": {candidate_field: {"type": candidate_type}},
            "required": [candidate_field],
        },
        "then": {
            "properties": {
                "identity_evidence": {
                    "contains": {
                        "properties": {
                            "evidence_type": {"enum": ["document_visible", "official_metadata"]},
                            "subject": {"const": subject},
                        },
                        "required": ["subject", "evidence_type"],
                        "type": "object",
                    },
                    "minContains": 1,
                    "minItems": 1,
                }
            },
            "required": ["identity_evidence"],
        },
    }


def rendered_discovery_schemas() -> dict[str, str]:
    """Render the complete discovery schema registry deterministically."""

    provisional_schema = ProvisionalDiscoveryRecord.model_json_schema(mode="validation")
    provisional_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    provisional_schema["$id"] = (
        "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
        f"schemas/discovery/v{DISCOVERY_SCHEMA_VERSION}/{DISCOVERY_SCHEMA_FILENAME}"
    )
    provisional_schema["$comment"] = (
        "JSON Schema enforces subject/type evidence sufficiency; Pydantic additionally "
        "requires candidate_value to equal the corresponding candidate identity exactly."
    )
    provisional_schema.setdefault("allOf", []).extend(
        [
            _qualified_evidence_condition(
                candidate_field="candidate_report_number",
                candidate_type="integer",
                subject="report_number",
            ),
            _qualified_evidence_condition(
                candidate_field="candidate_reference_period",
                candidate_type="string",
                subject="reference_period",
            ),
        ]
    )
    pilot_schema = PilotAcquisitionPlan.model_json_schema(mode="validation")
    repository_root = Path(__file__).resolve().parents[3]
    reviewed_pilot = load_pilot_acquisition_plan(
        repository_root / "config" / "acquisition_pilots" / "m1_03_reports_260_269_v1.yaml"
    ).model_dump(mode="json")
    pilot_schema["properties"]["approved_hosts"]["const"] = reviewed_pilot["approved_hosts"]
    pilot_schema["properties"]["targets"]["const"] = reviewed_pilot["targets"]

    models = {
        DISCOVERY_SCHEMA_FILENAME: provisional_schema,
        REQUEST_RECEIPT_SCHEMA_FILENAME: RequestAttemptReceipt.model_json_schema(mode="validation"),
        RECONNAISSANCE_SUMMARY_SCHEMA_FILENAME: ReconnaissanceSummary.model_json_schema(
            mode="validation"
        ),
        PILOT_ACQUISITION_PLAN_SCHEMA_FILENAME: pilot_schema,
    }
    for filename, schema in models.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/discovery/v{DISCOVERY_SCHEMA_VERSION}/{filename}"
        )
    return {
        filename: json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        for filename, schema in models.items()
    }


def export_discovery_schemas(output_dir: Path) -> list[Path]:
    """Write only the current discovery version beneath a schema root."""

    version_dir = output_dir / "discovery" / f"v{DISCOVERY_SCHEMA_VERSION}"
    version_dir.mkdir(parents=True, exist_ok=True)
    expected = rendered_discovery_schemas()
    for stale in version_dir.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()

    written: list[Path] = []
    for filename, content in expected.items():
        destination = version_dir / filename
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def discovery_schemas_are_current(output_dir: Path) -> bool:
    """Return whether the discovery schema tree exactly matches its models."""

    version_dir = output_dir / "discovery" / f"v{DISCOVERY_SCHEMA_VERSION}"
    expected = rendered_discovery_schemas()
    existing = {path.name for path in version_dir.glob("*.schema.json")}
    if existing != set(expected):
        return False
    return all(
        (version_dir / filename).read_text(encoding="utf-8") == content
        for filename, content in expected.items()
    )
