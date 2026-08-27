"""Deterministic JSON Schema export for the registered domain models."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.models import MODEL_REGISTRY, SCHEMA_VERSION


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
