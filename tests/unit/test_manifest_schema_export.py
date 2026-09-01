from __future__ import annotations

from pathlib import Path

from peru_conflicts.manifest.schema_export import (
    MANIFEST_SCHEMA_FILENAMES,
    export_manifest_schemas,
    manifest_schemas_are_current,
    rendered_manifest_schemas,
)


def test_manifest_schema_registry_is_complete_and_deterministic(tmp_path: Path) -> None:
    expected = {
        "byte_version_record.schema.json",
        "corpus_report_manifest_entry.schema.json",
        "coverage_report.schema.json",
        "gap_register_entry.schema.json",
        "materialization_receipt.schema.json",
        "source_observation_record.schema.json",
        "version_source_relationship_edge.schema.json",
    }

    assert set(MANIFEST_SCHEMA_FILENAMES) == expected
    first = rendered_manifest_schemas()
    second = rendered_manifest_schemas()
    assert first == second
    assert set(first) == expected
    assert all('"additionalProperties": false' in content for content in first.values())

    written = export_manifest_schemas(tmp_path)
    assert {path.name for path in written} == expected
    assert manifest_schemas_are_current(tmp_path)


def test_manifest_schema_drift_detects_changed_or_extra_file(tmp_path: Path) -> None:
    export_manifest_schemas(tmp_path)
    version_dir = tmp_path / "manifest" / "v0.1.0"

    (version_dir / "coverage_report.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)

    export_manifest_schemas(tmp_path)
    (version_dir / "unexpected.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)
