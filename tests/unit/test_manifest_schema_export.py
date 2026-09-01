from __future__ import annotations

import hashlib
from pathlib import Path

from peru_conflicts.manifest.schema_export import (
    MANIFEST_SCHEMA_FILENAMES,
    export_manifest_schemas,
    manifest_schemas_are_current,
    rendered_manifest_schemas,
)

MANIFEST_V010_TREE_SHA256 = "afd6e75d4bc16891c217f6bd672b44ec0187eb293a252f99592f2d4e34b8a978"


def _schema_tree_digest(version_dir: Path) -> str:
    rows = [
        f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(version_dir.glob("*.schema.json"))
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_manifest_v010_snapshot_digest_is_frozen() -> None:
    repo_root = Path(__file__).parents[2]
    version_dir = repo_root / "schemas" / "manifest" / "v0.1.0"

    assert len(tuple(version_dir.glob("*.schema.json"))) == 7
    assert _schema_tree_digest(version_dir) == MANIFEST_V010_TREE_SHA256


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
    assert {path.parent.name for path in written} == {"v0.1.1"}
    assert manifest_schemas_are_current(tmp_path)


def test_manifest_schema_drift_detects_changed_or_extra_file(tmp_path: Path) -> None:
    export_manifest_schemas(tmp_path)
    version_dir = tmp_path / "manifest" / "v0.1.1"

    (version_dir / "coverage_report.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)

    export_manifest_schemas(tmp_path)
    (version_dir / "unexpected.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)


def test_manifest_export_does_not_touch_historical_v010(tmp_path: Path) -> None:
    historical = tmp_path / "manifest" / "v0.1.0" / "sentinel.schema.json"
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b'{"historical":"v0.1.0"}\n')

    export_manifest_schemas(tmp_path)

    assert historical.read_bytes() == b'{"historical":"v0.1.0"}\n'
    assert (tmp_path / "manifest" / "v0.1.1").is_dir()
