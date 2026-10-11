"""Deterministic JSON Schema export for the registered domain models."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.models import MODEL_REGISTRY, SCHEMA_VERSION, ReportMonthAggregateObservationV1


def rendered_schemas() -> dict[str, str]:
    result: dict[str, str] = {}
    for name, model in sorted(MODEL_REGISTRY.items()):
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/v{SCHEMA_VERSION}/{name}.schema.json"
        )
        if name == "provenance":
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {"extraction_method": {"const": "probabilistic_model"}},
                        "required": ["extraction_method"],
                    },
                    "then": {"required": ["model_invocation"]},
                }
            )
        if name == "report_month":
            schema.setdefault("allOf", []).extend(
                [
                    {
                        "if": {
                            "properties": {"indicator_basis": {"const": "source_reported"}},
                            "required": ["indicator_basis"],
                        },
                        "then": {
                            "required": ["provenance_ids"],
                            "properties": {
                                "provenance_ids": {"minItems": 1},
                                "derivation_name": {"type": "null"},
                                "derivation_version": {"type": "null"},
                                "upstream_record_ids": {"maxItems": 0},
                            },
                        },
                    },
                    {
                        "if": {
                            "properties": {"indicator_basis": {"const": "derived"}},
                            "required": ["indicator_basis"],
                        },
                        "then": {
                            "required": [
                                "derivation_name",
                                "derivation_version",
                                "upstream_record_ids",
                            ],
                            "properties": {
                                "derivation_name": {"type": "string", "minLength": 1},
                                "derivation_version": {"type": "string", "minLength": 1},
                                "upstream_record_ids": {"minItems": 1},
                            },
                        },
                    },
                ]
            )
        if name == "dialogue_event":
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {
                            "mediation_process_id": {
                                "type": "string",
                                "minLength": 1,
                            }
                        },
                        "required": ["mediation_process_id"],
                    },
                    "then": {
                        "required": ["provenance_ids"],
                        "properties": {"provenance_ids": {"minItems": 1}},
                    },
                }
            )
        if name == "mediation_process":
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {"case_id": {"type": "string", "minLength": 1}},
                        "required": ["case_id"],
                    },
                    "then": {
                        "required": ["provenance_ids"],
                        "properties": {"provenance_ids": {"minItems": 1}},
                    },
                }
            )
        if name == "mediation_observation":
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "anyOf": [
                            {
                                "properties": {"case_id": {"type": "string", "minLength": 1}},
                                "required": ["case_id"],
                            },
                            {
                                "properties": {
                                    "mediation_process_id": {"type": "string", "minLength": 1}
                                },
                                "required": ["mediation_process_id"],
                            },
                        ]
                    },
                    "then": {
                        "required": ["provenance_ids"],
                        "properties": {"provenance_ids": {"minItems": 1}},
                    },
                }
            )
        if name == "case_reported_indicator":
            schema.setdefault("allOf", []).append(
                {
                    "properties": {
                        "value": {"not": {"type": "null"}},
                        "provenance_ids": {"minItems": 1},
                    },
                    "required": ["value", "provenance_ids"],
                }
            )
        if name == "demand":
            schema.setdefault("allOf", []).append(
                {
                    "anyOf": [
                        {
                            "properties": {field: {"type": "string", "minLength": 1}},
                            "required": [field],
                        }
                        for field in (
                            "text_original",
                            "theme_original",
                            "category_original",
                            "competent_entity_original",
                        )
                    ]
                }
            )
        if name == "report":
            schema.setdefault("allOf", []).extend(
                [
                    {
                        "if": {
                            "properties": {"report_number": {"type": "integer"}},
                            "required": ["report_number"],
                        },
                        "then": {
                            "required": [
                                "report_number_evidence_types",
                                "report_number_provenance_ids",
                            ],
                            "properties": {
                                "report_number_evidence_types": {
                                    "contains": {"enum": ["document_visible", "official_metadata"]}
                                },
                                "report_number_provenance_ids": {"minItems": 1},
                            },
                        },
                    },
                    {
                        "if": {
                            "properties": {"reference_period": {"type": "string"}},
                            "required": ["reference_period"],
                        },
                        "then": {
                            "required": [
                                "reference_period_evidence_types",
                                "reference_period_provenance_ids",
                            ],
                            "properties": {
                                "reference_period_evidence_types": {
                                    "contains": {"enum": ["document_visible", "official_metadata"]}
                                },
                                "reference_period_provenance_ids": {"minItems": 1},
                            },
                        },
                    },
                ]
            )
        result[f"{name}.schema.json"] = (
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return result


def export_json_schemas(output_dir: Path) -> list[Path]:
    version_dir = output_dir / f"v{SCHEMA_VERSION}"
    version_dir.mkdir(parents=True, exist_ok=True)
    expected = rendered_schemas()
    for stale in version_dir.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()

    written: list[Path] = []
    for filename, content in expected.items():
        destination = version_dir / filename
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def schemas_are_current(output_dir: Path) -> bool:
    version_dir = output_dir / f"v{SCHEMA_VERSION}"
    expected = rendered_schemas()
    existing = {path.name for path in version_dir.glob("*.schema.json")}
    if existing != set(expected):
        return False
    return all(
        (version_dir / name).read_text(encoding="utf-8") == content
        for name, content in expected.items()
    )


def rendered_observation_schemas() -> dict[str, str]:
    """Export the additive contract without repinning legacy scientific schemas."""
    name = "report_month_observation_v1.schema.json"
    schema = ReportMonthAggregateObservationV1.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://github.com/Jorge-Zavala-D/peru-conflict-data/schemas/extensions/" + name
    )
    schema["allOf"] = json.loads(rendered_schemas()["report_month.schema.json"])["allOf"]
    # Runtime ReferencePeriod rejects year zero; JSON Schema must express that guard too.
    month_schema = schema["properties"]["observation_period"]["anyOf"][0]
    month_schema["pattern"] = r"^[0-9]{4}-(0[1-9]|1[0-2])$"
    month_schema["not"] = {"pattern": "^0000-"}
    return {name: json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"}


def export_observation_schemas(output_dir: Path) -> list[Path]:
    extension_dir = output_dir / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in rendered_observation_schemas().items():
        path = extension_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def observation_schemas_are_current(output_dir: Path) -> bool:
    return all(
        (output_dir / "extensions" / name).is_file()
        and (output_dir / "extensions" / name).read_text(encoding="utf-8") == content
        for name, content in rendered_observation_schemas().items()
    )
