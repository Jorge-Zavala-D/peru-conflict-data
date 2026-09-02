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
MANIFEST_V011_TREE_SHA256 = "883dd7062084daed198215ce5f22160608067b6e44b7b33ef4c074096ab8f3da"


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


def test_manifest_v011_snapshot_digest_is_frozen() -> None:
    repo_root = Path(__file__).parents[2]
    version_dir = repo_root / "schemas" / "manifest" / "v0.1.1"

    assert len(tuple(version_dir.glob("*.schema.json"))) == 7
    assert _schema_tree_digest(version_dir) == MANIFEST_V011_TREE_SHA256


def test_manifest_schema_registry_is_complete_and_deterministic(tmp_path: Path) -> None:
    expected = {
        "canonicalization_receipt.schema.json",
        "deferred_acquisition_policy.schema.json",
        "manifest_adjudication_record.schema.json",
        "owner_approval_artifact.schema.json",
        "reviewed_coverage_report.schema.json",
    }

    assert set(MANIFEST_SCHEMA_FILENAMES) == expected
    first = rendered_manifest_schemas()
    second = rendered_manifest_schemas()
    assert first == second
    assert set(first) == expected
    assert all('"additionalProperties": false' in content for content in first.values())

    written = export_manifest_schemas(tmp_path)
    assert {path.name for path in written} == expected
    assert {path.parent.name for path in written} == {"v0.2.0"}
    assert manifest_schemas_are_current(tmp_path)


def test_manifest_schema_drift_detects_changed_or_extra_file(tmp_path: Path) -> None:
    export_manifest_schemas(tmp_path)
    version_dir = tmp_path / "manifest" / "v0.2.0"

    (version_dir / "reviewed_coverage_report.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)

    export_manifest_schemas(tmp_path)
    (version_dir / "unexpected.schema.json").write_text("{}\n", encoding="utf-8")
    assert not manifest_schemas_are_current(tmp_path)


def test_manifest_export_does_not_touch_historical_v010_or_v011(tmp_path: Path) -> None:
    historical_v010 = tmp_path / "manifest" / "v0.1.0" / "sentinel.schema.json"
    historical_v011 = tmp_path / "manifest" / "v0.1.1" / "sentinel.schema.json"
    historical_v010.parent.mkdir(parents=True)
    historical_v011.parent.mkdir(parents=True)
    historical_v010.write_bytes(b'{"historical":"v0.1.0"}\n')
    historical_v011.write_bytes(b'{"historical":"v0.1.1"}\n')

    export_manifest_schemas(tmp_path)

    assert historical_v010.read_bytes() == b'{"historical":"v0.1.0"}\n'
    assert historical_v011.read_bytes() == b'{"historical":"v0.1.1"}\n'
    assert (tmp_path / "manifest" / "v0.2.0").is_dir()
