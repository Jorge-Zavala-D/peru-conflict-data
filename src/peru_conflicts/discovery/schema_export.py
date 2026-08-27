"""Deterministic JSON Schema export for provisional discovery records."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.discovery.models import DISCOVERY_SCHEMA_VERSION, ProvisionalDiscoveryRecord

DISCOVERY_SCHEMA_FILENAME = "provisional_discovery_record.schema.json"


def rendered_discovery_schemas() -> dict[str, str]:
    """Render the complete discovery schema registry deterministically."""

    schema = ProvisionalDiscoveryRecord.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
        f"schemas/discovery/v{DISCOVERY_SCHEMA_VERSION}/{DISCOVERY_SCHEMA_FILENAME}"
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
