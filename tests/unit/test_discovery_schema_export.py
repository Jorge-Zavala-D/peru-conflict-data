from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from peru_conflicts.discovery.schema_export import (
    discovery_schemas_are_current,
    export_discovery_schemas,
    rendered_discovery_schemas,
)
from peru_conflicts.schema_export import export_json_schemas

SCHEMA_FILENAME = "provisional_discovery_record.schema.json"


def test_discovery_export_writes_one_strict_versioned_schema(tmp_path: Path) -> None:
    written = export_discovery_schemas(tmp_path)

    assert written == [tmp_path / "discovery" / "v0.1.0" / SCHEMA_FILENAME]
    schema = json.loads(written[0].read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == (
        "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
        "schemas/discovery/v0.1.0/provisional_discovery_record.schema.json"
    )
    assert schema["additionalProperties"] is False
    assert all(
        definition.get("additionalProperties") is False
        for definition in schema["$defs"].values()
        if definition.get("type") == "object"
    )


def test_discovery_schema_render_and_export_are_deterministic(tmp_path: Path) -> None:
    expected = rendered_discovery_schemas()
    first_written = export_discovery_schemas(tmp_path)
    first_bytes = first_written[0].read_bytes()

    second_written = export_discovery_schemas(tmp_path)

    assert expected == {SCHEMA_FILENAME: first_bytes.decode("utf-8")}
    assert second_written[0].read_bytes() == first_bytes
    assert discovery_schemas_are_current(tmp_path) is True


def test_discovery_schema_encodes_qualified_identity_evidence_conditions(
    tmp_path: Path,
) -> None:
    written = export_discovery_schemas(tmp_path)
    schema = json.loads(written[0].read_text(encoding="utf-8"))

    assert schema["$comment"] == (
        "JSON Schema enforces subject/type evidence sufficiency; Pydantic additionally "
        "requires candidate_value to equal the corresponding candidate identity exactly."
    )
    assert schema["allOf"] == [
        {
            "if": {
                "properties": {"candidate_report_number": {"type": "integer"}},
                "required": ["candidate_report_number"],
            },
            "then": {
                "properties": {
                    "identity_evidence": {
                        "contains": {
                            "properties": {
                                "evidence_type": {
                                    "enum": ["document_visible", "official_metadata"]
                                },
                                "subject": {"const": "report_number"},
                            },
                            "required": ["subject", "evidence_type"],
                            "type": "object",
                        },
                        "minContains": 1,
                        "minItems": 1,
                    }
                },
                "required": ["identity_evidence"],
            },
        },
        {
            "if": {
                "properties": {"candidate_reference_period": {"type": "string"}},
                "required": ["candidate_reference_period"],
            },
            "then": {
                "properties": {
                    "identity_evidence": {
                        "contains": {
                            "properties": {
                                "evidence_type": {
                                    "enum": ["document_visible", "official_metadata"]
                                },
                                "subject": {"const": "reference_period"},
                            },
                            "required": ["subject", "evidence_type"],
                            "type": "object",
                        },
                        "minContains": 1,
                        "minItems": 1,
                    }
                },
                "required": ["identity_evidence"],
            },
        },
    ]


def test_discovery_export_preserves_scientific_schema_directories(tmp_path: Path) -> None:
    immutable = {
        tmp_path / "v0.1.0" / "sentinel.schema.json": b'{"version":"0.1.0"}\n',
        tmp_path / "v0.2.0" / "sentinel.schema.json": b'{"version":"0.2.0"}\n',
    }
    for path, content in immutable.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    export_discovery_schemas(tmp_path)

    assert {path: path.read_bytes() for path in immutable} == immutable


def test_discovery_schema_check_detects_changed_missing_and_extra_files(tmp_path: Path) -> None:
    written = export_discovery_schemas(tmp_path)
    schema_dir = written[0].parent

    written[0].write_text("{}\n", encoding="utf-8")
    assert discovery_schemas_are_current(tmp_path) is False

    export_discovery_schemas(tmp_path)
    written[0].unlink()
    assert discovery_schemas_are_current(tmp_path) is False

    export_discovery_schemas(tmp_path)
    (schema_dir / "stale.schema.json").write_text("{}\n", encoding="utf-8")
    assert discovery_schemas_are_current(tmp_path) is False


def test_existing_schema_check_gate_includes_discovery_drift(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    export_json_schemas(tmp_path)
    written = export_discovery_schemas(tmp_path)
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
    assert "discovery" in drifted.stdout.lower()
