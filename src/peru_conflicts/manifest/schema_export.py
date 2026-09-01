"""Deterministic JSON Schema export for the M1 manifest contract."""

from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.manifest.models import (
    MANIFEST_SCHEMA_VERSION,
    ByteVersionRecord,
    CorpusReportManifestEntry,
    CoverageReport,
    GapRegisterEntry,
    MaterializationReceipt,
    SourceObservationRecord,
    VersionSourceRelationshipEdge,
)

MANIFEST_SCHEMA_FILENAMES = (
    "byte_version_record.schema.json",
    "corpus_report_manifest_entry.schema.json",
    "coverage_report.schema.json",
    "gap_register_entry.schema.json",
    "materialization_receipt.schema.json",
    "source_observation_record.schema.json",
    "version_source_relationship_edge.schema.json",
)


def rendered_manifest_schemas() -> dict[str, str]:
    """Render the complete manifest schema registry deterministically."""

    models = {
        "byte_version_record.schema.json": ByteVersionRecord,
        "corpus_report_manifest_entry.schema.json": CorpusReportManifestEntry,
        "coverage_report.schema.json": CoverageReport,
        "gap_register_entry.schema.json": GapRegisterEntry,
        "materialization_receipt.schema.json": MaterializationReceipt,
        "source_observation_record.schema.json": SourceObservationRecord,
        "version_source_relationship_edge.schema.json": VersionSourceRelationshipEdge,
    }
    rendered: dict[str, str] = {}
    for filename, model in models.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/manifest/v{MANIFEST_SCHEMA_VERSION}/{filename}"
        )
        rendered[filename] = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return rendered


def export_manifest_schemas(output_dir: Path) -> list[Path]:
    """Write only the current manifest version beneath a schema root."""

    version_dir = output_dir / "manifest" / f"v{MANIFEST_SCHEMA_VERSION}"
    version_dir.mkdir(parents=True, exist_ok=True)
    expected = rendered_manifest_schemas()
    for stale in version_dir.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()

    written: list[Path] = []
    for filename, content in expected.items():
        destination = version_dir / filename
        destination.write_text(content, encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def manifest_schemas_are_current(output_dir: Path) -> bool:
    """Return whether the manifest schema tree exactly matches its models."""

    version_dir = output_dir / "manifest" / f"v{MANIFEST_SCHEMA_VERSION}"
    expected = rendered_manifest_schemas()
    existing = {path.name for path in version_dir.glob("*.schema.json")}
    if existing != set(expected):
        return False
    return all(
        (version_dir / filename).read_text(encoding="utf-8") == content
        for filename, content in expected.items()
    )
