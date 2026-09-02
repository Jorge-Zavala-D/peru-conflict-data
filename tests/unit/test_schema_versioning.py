from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from peru_conflicts.models import MODEL_REGISTRY, SCHEMA_VERSION, ReportMonthAggregate
from peru_conflicts.schema_export import export_json_schemas, schemas_are_current

V010_SCHEMA_TREE_DIGEST = "da34082dabb4dc7020f078d7f5902c68cc2dd4ef6f430d7bf7cfe98e6e829f28"
V020_SCHEMA_TREE_DIGEST = "13302cbbe1127f54960cf478eda59ec18dc97f6d0c3e9a15c07798cb4ab0417d"


def _schema_tree_digest(version_dir: Path) -> str:
    rows: list[str] = []
    for path in sorted(version_dir.glob("*.schema.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.name}:{digest}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_v010_snapshot_digest_is_retained() -> None:
    repo_root = Path(__file__).parents[2]
    assert _schema_tree_digest(repo_root / "schemas" / "v0.1.0") == V010_SCHEMA_TREE_DIGEST


def test_v020_snapshot_digest_is_retained() -> None:
    repo_root = Path(__file__).parents[2]
    assert _schema_tree_digest(repo_root / "schemas" / "v0.2.0") == V020_SCHEMA_TREE_DIGEST


def test_v030_is_the_only_current_export_and_does_not_mutate_history(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    before_v010 = _schema_tree_digest(repo_root / "schemas" / "v0.1.0")
    before_v020 = _schema_tree_digest(repo_root / "schemas" / "v0.2.0")

    export_json_schemas(tmp_path)

    assert SCHEMA_VERSION == "0.3.0"
    assert schemas_are_current(tmp_path)
    assert (tmp_path / "v0.3.0").exists()
    assert _schema_tree_digest(repo_root / "schemas" / "v0.1.0") == before_v010
    assert _schema_tree_digest(repo_root / "schemas" / "v0.2.0") == before_v020


def test_v030_registry_and_exported_schema_names_are_aligned(tmp_path: Path) -> None:
    written = export_json_schemas(tmp_path)
    assert {path.name.removesuffix(".schema.json") for path in written} == set(MODEL_REGISTRY)
    assert not (tmp_path / "v0.1.0").exists()
    assert not (tmp_path / "v0.2.0").exists()


def test_v010_monthly_payload_requires_explicit_migration() -> None:
    with pytest.raises(ValidationError, match="indicator_basis"):
        ReportMonthAggregate.model_validate(
            {
                "schema_version": "0.1.0",
                "report_month_id": "indicator_1",
                "report_id": "report_269",
                "metric_original": "Violencia acumulada",
                "value": 12,
            }
        )
