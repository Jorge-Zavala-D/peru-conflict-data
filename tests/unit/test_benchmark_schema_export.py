from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from peru_conflicts.acquisition.schema_export import export_acquisition_schemas
from peru_conflicts.benchmark import BENCHMARK_MODEL_REGISTRY, BENCHMARK_SCHEMA_VERSION
from peru_conflicts.benchmark.schema_export import (
    benchmark_schemas_are_current,
    export_benchmark_schemas,
    rendered_benchmark_schemas,
)
from peru_conflicts.discovery.schema_export import export_discovery_schemas
from peru_conflicts.manifest.schema_export import export_manifest_schemas
from peru_conflicts.schema_export import export_json_schemas


def test_benchmark_schema_contract_is_independently_versioned() -> None:
    assert BENCHMARK_SCHEMA_VERSION == "0.1.0"


def test_benchmark_schema_export_matches_registry(tmp_path: Path) -> None:
    written = export_benchmark_schemas(tmp_path)
    assert {path.name.removesuffix(".schema.json") for path in written} == set(
        BENCHMARK_MODEL_REGISTRY
    )
    assert benchmark_schemas_are_current(tmp_path)


def test_tracked_benchmark_schemas_are_current() -> None:
    repo_root = Path(__file__).parents[2]
    assert benchmark_schemas_are_current(repo_root / "schemas" / "benchmark")


def test_benchmark_schemas_export_cross_field_and_uniqueness_guards() -> None:
    schemas = {name: json.loads(content) for name, content in rendered_benchmark_schemas().items()}
    annotation = schemas["field_annotation.schema.json"]
    coverage = schemas["benchmark_coverage_receipt.schema.json"]

    assert {
        "if": {
            "properties": {"state": {"enum": ["source_ambiguous", "annotation_uncertain"]}},
            "required": ["state"],
        },
        "then": {
            "properties": {"uncertainty_comment": {"type": "string", "minLength": 1}},
            "required": ["uncertainty_comment"],
        },
    } in annotation["allOf"]
    for field in (
        "required_field_keys",
        "observed_field_keys",
        "explicit_non_value_field_keys",
    ):
        assert coverage["properties"][field]["uniqueItems"] is True


def test_top_level_schema_check_includes_benchmark_drift(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    export_json_schemas(tmp_path)
    export_discovery_schemas(tmp_path)
    export_acquisition_schemas(tmp_path)
    export_manifest_schemas(tmp_path)
    written = export_benchmark_schemas(tmp_path / "benchmark")
    command = [
        sys.executable,
        "scripts/export_schemas.py",
        "--check",
        "--output",
        str(tmp_path),
    ]

    current = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)
    written[0].write_text("{}\n", encoding="utf-8")
    drifted = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)

    assert current.returncode == 0, current.stdout + current.stderr
    assert drifted.returncode == 1
    assert "benchmark" in drifted.stdout.lower()
