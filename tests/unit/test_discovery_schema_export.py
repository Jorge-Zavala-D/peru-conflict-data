from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from peru_conflicts.discovery.schema_export import (
    PILOT_ACQUISITION_PLAN_SCHEMA_FILENAME,
    discovery_schemas_are_current,
    export_discovery_schemas,
    rendered_discovery_schemas,
)
from peru_conflicts.schema_export import export_json_schemas

PROVISIONAL_SCHEMA_FILENAME = "provisional_discovery_record.schema.json"
REQUEST_SCHEMA_FILENAME = "request_attempt_receipt.schema.json"
SUMMARY_SCHEMA_FILENAME = "reconnaissance_summary.schema.json"
SCHEMA_FILENAMES = {
    PROVISIONAL_SCHEMA_FILENAME,
    REQUEST_SCHEMA_FILENAME,
    SUMMARY_SCHEMA_FILENAME,
    PILOT_ACQUISITION_PLAN_SCHEMA_FILENAME,
}
DISCOVERY_V010_TREE_DIGEST = "28fc05feae0d71ce9a681e3929c8d751a2a7c4134baa4b8b5a73a6402186660f"
DISCOVERY_V020_TREE_DIGEST = "83f1a25cc72830c69491b5df26451a2f7091e9dfa1c649aa942cd92564244e01"


def _schema_tree_digest(version_dir: Path) -> str:
    rows = [
        f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(version_dir.glob("*.schema.json"))
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_repository_discovery_v010_snapshot_digest_is_retained() -> None:
    repo_root = Path(__file__).parents[2]
    assert (
        _schema_tree_digest(repo_root / "schemas" / "discovery" / "v0.1.0")
        == DISCOVERY_V010_TREE_DIGEST
    )


def test_repository_discovery_v020_snapshot_digest_is_retained() -> None:
    repo_root = Path(__file__).parents[2]
    assert (
        _schema_tree_digest(repo_root / "schemas" / "discovery" / "v0.2.0")
        == DISCOVERY_V020_TREE_DIGEST
    )


def test_discovery_export_writes_strict_v030_schemas(tmp_path: Path) -> None:
    written = export_discovery_schemas(tmp_path)

    assert {path.name for path in written} == SCHEMA_FILENAMES
    assert {path.parent for path in written} == {tmp_path / "discovery" / "v0.3.0"}
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == (
            "https://github.com/Jorge-Zavala-D/peru-conflict-data/"
            f"schemas/discovery/v0.3.0/{path.name}"
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
    first_bytes = {path.name: path.read_bytes() for path in first_written}

    second_written = export_discovery_schemas(tmp_path)

    assert expected == {name: content.decode("utf-8") for name, content in first_bytes.items()}
    assert {path.name: path.read_bytes() for path in second_written} == first_bytes
    assert discovery_schemas_are_current(tmp_path) is True


def test_discovery_schema_encodes_qualified_identity_evidence_conditions(
    tmp_path: Path,
) -> None:
    written = export_discovery_schemas(tmp_path)
    schema_path = next(path for path in written if path.name == PROVISIONAL_SCHEMA_FILENAME)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

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


def test_pilot_schema_pins_reviewed_hosts_targets_and_null_remote_hashes(
    tmp_path: Path,
) -> None:
    written = export_discovery_schemas(tmp_path)
    schema_path = next(
        path for path in written if path.name == PILOT_ACQUISITION_PLAN_SCHEMA_FILENAME
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["properties"]["approved_hosts"]["const"] == [
        "defensoria.gob.pe",
        "www.defensoria.gob.pe",
    ]
    assert len(schema["properties"]["targets"]["const"]) == 10
    assert [target["report_number"] for target in schema["properties"]["targets"]["const"]] == list(
        range(260, 270)
    )
    assert schema["$defs"]["PilotTarget"]["properties"]["expected_remote_sha256"] == {
        "default": None,
        "title": "Expected Remote Sha256",
        "type": "null",
    }


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

    target = next(path for path in written if path.name == PROVISIONAL_SCHEMA_FILENAME)
    target.write_text("{}\n", encoding="utf-8")
    assert discovery_schemas_are_current(tmp_path) is False

    written = export_discovery_schemas(tmp_path)
    target = next(path for path in written if path.name == PROVISIONAL_SCHEMA_FILENAME)
    target.unlink()
    assert discovery_schemas_are_current(tmp_path) is False

    export_discovery_schemas(tmp_path)
    (schema_dir / "stale.schema.json").write_text("{}\n", encoding="utf-8")
    assert discovery_schemas_are_current(tmp_path) is False


def test_discovery_export_preserves_prior_discovery_schema_version(tmp_path: Path) -> None:
    prior_v010 = tmp_path / "discovery" / "v0.1.0" / PROVISIONAL_SCHEMA_FILENAME
    prior_v020 = tmp_path / "discovery" / "v0.2.0" / PROVISIONAL_SCHEMA_FILENAME
    for prior in (prior_v010, prior_v020):
        prior.parent.mkdir(parents=True, exist_ok=True)
        prior.write_bytes(f'{{"version":"{prior.parent.name}"}}\n'.encode())

    export_discovery_schemas(tmp_path)

    assert prior_v010.read_bytes() == b'{"version":"v0.1.0"}\n'
    assert prior_v020.read_bytes() == b'{"version":"v0.2.0"}\n'
    assert {path.name for path in (tmp_path / "discovery" / "v0.3.0").glob("*.json")} == (
        SCHEMA_FILENAMES
    )


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
    next(path for path in written if path.name == PROVISIONAL_SCHEMA_FILENAME).write_text(
        "{}\n", encoding="utf-8"
    )
    drifted = subprocess.run(command, cwd=repo_root, check=False, capture_output=True, text=True)

    assert current.returncode == 0, current.stdout + current.stderr
    assert drifted.returncode == 1
    assert "discovery" in drifted.stdout.lower()
