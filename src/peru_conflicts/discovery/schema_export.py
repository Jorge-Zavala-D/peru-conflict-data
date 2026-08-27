"""Deterministic JSON Schema export for provisional discovery records."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.discovery.models import DISCOVERY_SCHEMA_VERSION, ProvisionalDiscoveryRecord

DISCOVERY_SCHEMA_FILENAME = "provisional_discovery_record.schema.json"


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

    schema = ProvisionalDiscoveryRecord.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
        f"schemas/discovery/v{DISCOVERY_SCHEMA_VERSION}/{DISCOVERY_SCHEMA_FILENAME}"
    )
    schema["$comment"] = (
        "JSON Schema enforces subject/type evidence sufficiency; Pydantic additionally "
        "requires candidate_value to equal the corresponding candidate identity exactly."
    )
    schema.setdefault("allOf", []).extend(
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
    return {
        DISCOVERY_SCHEMA_FILENAME: (
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
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
