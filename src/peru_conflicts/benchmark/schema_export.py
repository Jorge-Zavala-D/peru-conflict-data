"""Deterministic JSON Schema export for benchmark technical models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from peru_conflicts.benchmark.models import BENCHMARK_MODEL_REGISTRY, BENCHMARK_SCHEMA_VERSION


def _apply_model_guards(model_name: str, schema: dict[str, object]) -> None:
    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, dict):
        return
    properties = cast(dict[str, dict[str, object]], raw_properties)
    if model_name == "FieldAnnotation":
        all_of = cast(list[object], schema.setdefault("allOf", []))
        all_of.append(
            {
                "if": {
                    "properties": {"state": {"enum": ["source_ambiguous", "annotation_uncertain"]}},
                    "required": ["state"],
                },
                "then": {
                    "properties": {"uncertainty_comment": {"type": "string", "minLength": 1}},
                    "required": ["uncertainty_comment"],
                },
            }
        )
    if model_name == "BenchmarkCoverageReceipt":
        for field in ("object_inventory", "observed_slots", "explicit_non_value_slots"):
            properties[field]["uniqueItems"] = True
    if model_name == "AnnotationObjectInstance":
        properties["required_field_names"]["uniqueItems"] = True
    if model_name == "EvidenceRequirement":
        for field in ("pages", "sections", "allowed_granularities"):
            properties[field]["uniqueItems"] = True
        properties["allowed_granularities"]["items"] = {
            "enum": ["span", "bounding_box", "table_cell", "page_only"],
            "type": "string",
        }


def rendered_benchmark_schemas() -> dict[str, str]:
    result: dict[str, str] = {}
    for name, model in sorted(BENCHMARK_MODEL_REGISTRY.items()):
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/benchmark/v{BENCHMARK_SCHEMA_VERSION}/{name}.schema.json"
        )
        _apply_model_guards(model.__name__, schema)
        definitions = cast(dict[str, dict[str, object]], schema.get("$defs", {}))
        for model_name, definition in definitions.items():
            _apply_model_guards(model_name, definition)
        result[f"{name}.schema.json"] = (
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return result


def export_benchmark_schemas(output_dir: Path) -> list[Path]:
    version_dir = output_dir / f"v{BENCHMARK_SCHEMA_VERSION}"
    version_dir.mkdir(parents=True, exist_ok=True)
    expected = rendered_benchmark_schemas()
    for stale in version_dir.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()
    written: list[Path] = []
    for filename, content in expected.items():
        path = version_dir / filename
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def benchmark_schemas_are_current(output_dir: Path) -> bool:
    version_dir = output_dir / f"v{BENCHMARK_SCHEMA_VERSION}"
    expected = rendered_benchmark_schemas()
    return {path.name for path in version_dir.glob("*.schema.json")} == set(expected) and all(
        (version_dir / name).read_text(encoding="utf-8") == content
        for name, content in expected.items()
    )
