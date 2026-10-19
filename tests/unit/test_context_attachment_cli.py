"""Invented CLI checks: exact bytes, portable imports and honest partial failures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from test_context_attachment import fixture

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/attach_source_context.py"


def inputs(tmp_path: Path) -> tuple[list[str], dict[str, Any], dict[str, bytes]]:
    request, documents = fixture()
    locations = {}
    for name, raw in documents.items():
        path = tmp_path / (name + ".json")
        path.write_bytes(raw)
        locations[name] = path.name
    (tmp_path / "request.json").write_text(json.dumps(request), encoding="utf-8")
    (tmp_path / "locations.json").write_text(json.dumps({"documents": locations}), encoding="utf-8")
    return (
        [
            sys.executable,
            "-I",
            "-B",
            str(SCRIPT),
            "--request",
            str(tmp_path / "request.json"),
            "--locations",
            str(tmp_path / "locations.json"),
            "--output-json",
            str(tmp_path / "view.json"),
            "--output-markdown",
            str(tmp_path / "view.md"),
        ],
        request,
        documents,
    )


def test_cli_populated_text_view_from_unrelated_cwd(tmp_path: Path) -> None:
    command, request, documents = inputs(tmp_path)
    run = subprocess.run(command, cwd=tmp_path, capture_output=True, check=False)
    assert run.returncode == 0, run.stderr.decode()
    view = json.loads((tmp_path / "view.json").read_bytes())
    assert (
        len(view["cell_references"]) == 3
        and view["context_node"]["kind"] == "introductory_paragraph"
    )
    assert "| Town | Issue | New |" in (tmp_path / "view.md").read_text(encoding="utf-8")
    assert view["permissions"]["automatic_dispatch"] is False
    assert view["source"]["native_sha256"] == hashlib.sha256(documents["native"]).hexdigest()
    assert (
        view["attachment_assertions"][0]["source_address"]
        == "sha256:" + request["documents"]["assertions"]["sha256"] + "#/attachment"
    )


def test_cli_existing_output_preserves_every_original(tmp_path: Path) -> None:
    command, _, documents = inputs(tmp_path)
    (tmp_path / "view.md").write_bytes(b"old output")
    run = subprocess.run(command, capture_output=True, check=False)
    assert run.returncode != 0
    assert (
        not (tmp_path / "view.json").exists()
        and (tmp_path / "view.md").read_bytes() == b"old output"
    )
    assert (tmp_path / "native.json").read_bytes() == documents["native"]


def test_cli_missing_or_wrong_documents_create_no_view(tmp_path: Path) -> None:
    command, _, _ = inputs(tmp_path)
    (tmp_path / "native.json").write_bytes(b"{}")
    run = subprocess.run(command, capture_output=True, check=False)
    assert run.returncode != 0 and b"hash_mismatch:native" in run.stderr
    assert not (tmp_path / "view.json").exists()
    (tmp_path / "native.json").unlink()
    run = subprocess.run(command, capture_output=True, check=False)
    assert run.returncode != 0 and not (tmp_path / "view.json").exists()


def test_cli_partial_write_failure_is_reported_without_rollback(tmp_path: Path) -> None:
    command, _, _ = inputs(tmp_path)
    command[-1] = str(tmp_path / "absent" / "view.md")
    run = subprocess.run(command, capture_output=True, check=False)
    assert run.returncode != 0 and (tmp_path / "view.json").exists()
    report = json.loads(run.stderr)
    assert str(tmp_path / "view.json") in report["output_paths_present"]
    assert report["transactionally_atomic"] is False


def test_pointer_root_and_escaped_properties_preserve_identity() -> None:
    from test_context_attachment import refresh

    from peru_conflicts.execution.context_attachment import attach_context

    request, documents = fixture()
    descriptor = json.loads(documents["descriptor"])
    documents["descriptor"] = json.dumps({"a/b~c": descriptor}).encode()
    request["descriptor_ref"]["pointer"] = "/a~1b~0c"
    refresh(request, documents)
    view = attach_context(request, documents)
    assert view["receiving_descriptor_address"].endswith("#/a~1b~0c")
    assert len(view["cell_references"]) == 3


def test_component_cli_runs_from_clean_source_only_tree(tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    files = [
        "src/peru_conflicts/__init__.py",
        "src/peru_conflicts/execution/__init__.py",
        "src/peru_conflicts/execution/context_attachment.py",
        "scripts/attach_source_context.py",
    ]
    for relative in files:
        target = clean / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / relative, target)
    command, _, _ = inputs(tmp_path)
    command[3] = str(clean / "scripts/attach_source_context.py")
    run = subprocess.run(command, cwd=clean, capture_output=True, check=False)
    assert run.returncode == 0, run.stderr.decode()
    assert len(json.loads((tmp_path / "view.json").read_bytes())["cell_references"]) == 3
    assert not (clean / "tests").exists()


def test_wrong_document_registry_fails_its_own_predicate() -> None:
    import pytest

    from peru_conflicts.execution.context_attachment import attach_context

    request, documents = fixture()
    documents.pop("profile")
    with pytest.raises(ValueError, match="document_registry_mismatch"):
        attach_context(request, documents)
