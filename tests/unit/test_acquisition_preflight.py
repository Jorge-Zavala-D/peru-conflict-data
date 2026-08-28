from __future__ import annotations

import hashlib
import http.client
import importlib
import importlib.util
import os
import socket
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import BinaryIO

import pytest
import yaml

from peru_conflicts.acquisition.models import AcquisitionPilotPlan
from peru_conflicts.acquisition.plan import LoadedPilotPlan
from peru_conflicts.paths import EXPECTED_TOP_LEVEL

V2_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml")


def _make_directory_alias(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    escaped_link = str(link).replace("'", "''")
    escaped_target = str(target).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop'; "
        f"New-Item -ItemType Junction -Path '{escaped_link}' "
        f"-Target '{escaped_target}' | Out-Null"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
    )


def _run_git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, Path, LoadedPilotPlan, tuple[bytes, ...]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "tests@example.invalid")
    _run_git(repo, "config", "user.name", "M1-03A Tests")
    _run_git(repo, "config", "core.autocrlf", "false")
    receipt_path = repo / "docs" / "source_integrity_receipt.md"
    receipt_path.parent.mkdir()
    receipt_bytes = b"synthetic source integrity receipt\n"
    receipt_path.write_bytes(receipt_bytes)
    _run_git(repo, "add", "docs/source_integrity_receipt.md")
    _run_git(repo, "commit", "-m", "Add synthetic baseline receipt")
    baseline_commit = _run_git(repo, "rev-parse", "HEAD")

    data_root = tmp_path / "external-data"
    for zone in EXPECTED_TOP_LEVEL:
        (data_root / zone).mkdir(parents=True)

    payload = yaml.safe_load(V2_PATH.read_text(encoding="utf-8"))
    payload["baseline_receipt_path"] = "docs/source_integrity_receipt.md"
    payload["baseline_receipt_git_commit"] = baseline_commit
    payload["baseline_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    source_bytes: list[bytes] = []
    for target in payload["targets"]:
        report_number = target["report_number"]
        content = f"%PDF-1.7\nsynthetic report {report_number}\n".encode()
        relative = f"01_raw/reports/2026/report-{report_number}.pdf"
        destination = data_root.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        target["existing_local_relative_path"] = relative
        target["existing_local_byte_count"] = len(content)
        target["existing_local_sha256"] = hashlib.sha256(content).hexdigest()
        source_bytes.append(content)
    plan = AcquisitionPilotPlan.model_validate(payload)
    loaded = LoadedPilotPlan(
        plan=plan,
        file_sha256="1" * 64,
        semantic_sha256="2" * 64,
        target_set_sha256="3" * 64,
    )
    return repo, data_root, loaded, tuple(source_bytes)


def _snapshot_tree(root: Path) -> tuple[tuple[str, str, int, int, str | None], ...]:
    rows: list[tuple[str, str, int, int, str | None]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            content = path.read_bytes()
            rows.append(
                (
                    relative,
                    "file",
                    len(content),
                    path.stat().st_mtime_ns,
                    hashlib.sha256(content).hexdigest(),
                )
            )
        else:
            rows.append((relative, "directory", 0, path.stat().st_mtime_ns, None))
    return tuple(rows)


def test_acquisition_preflight_module_exists() -> None:
    try:
        specification = importlib.util.find_spec("peru_conflicts.acquisition.preflight")
    except ModuleNotFoundError:
        specification = None
    assert specification is not None


def test_acquisition_preflight_api_exists() -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")

    assert callable(getattr(module, "run_dry_run_preflight", None))
    assert callable(getattr(module, "write_dry_run_result", None))


def test_preflight_verifies_ten_sources_and_builds_ordered_zero_side_effect_plan(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, source_bytes = _fixture(tmp_path)

    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )

    assert result.verified_source_count == 10
    assert result.verified_source_bytes == sum(map(len, source_bytes))
    assert result.logical_url_count == 20
    assert result.network_requests == 0
    assert result.dropbox_writes == 0
    assert [action.sequence for action in result.actions] == list(range(1, len(result.actions) + 1))
    assert [action.action for action in result.actions[:5]] == [
        "validate_plan_contract",
        "validate_merged_baseline",
        "validate_source_integrity_receipt",
        "validate_data_root",
        "validate_raw_write_protection",
    ]
    assert sum(action.action == "validate_existing_source" for action in result.actions) == 10
    assert sum(action.action == "request_landing_html" for action in result.actions) == 10
    assert sum(action.action == "stream_pdf_to_system_temp" for action in result.actions) == 10
    assert not (data_root / "01_raw" / ".staging").exists()


def test_preflight_cannot_open_a_network_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)

    def reject_network(*_: object, **__: object) -> None:
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(urllib.request, "urlopen", reject_network)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", reject_network)

    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )

    assert result.network_requests == 0
    assert result.dropbox_writes == 0


def test_preflight_never_probes_the_configured_system_temp_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    before = _snapshot_tree(data_root)
    monkeypatch.setenv("TEMP", str(data_root))
    monkeypatch.setenv("TMP", str(data_root))

    def forbidden_probe() -> str:
        raise AssertionError("dry-run called tempfile.gettempdir()")

    monkeypatch.setattr(tempfile, "gettempdir", forbidden_probe)

    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )

    assert result.network_requests == 0
    assert result.dropbox_writes == 0
    assert _snapshot_tree(data_root) == before


def test_tenth_source_mismatch_fails_without_creating_any_data_path(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    tenth = data_root.joinpath(*loaded.plan.targets[-1].existing_local_relative_path.split("/"))
    tenth.write_bytes(b"changed after plan review")
    before_paths = sorted(path.relative_to(data_root).as_posix() for path in data_root.rglob("*"))

    with pytest.raises(module.SourceFingerprintMismatch, match="269"):
        module.run_dry_run_preflight(
            loaded_plan=loaded,
            repo_root=repo,
            data_root=data_root,
        )

    assert (
        sorted(path.relative_to(data_root).as_posix() for path in data_root.rglob("*"))
        == before_paths
    )
    assert not (data_root / "01_raw" / "manifests").exists()
    assert not (data_root / "01_raw" / ".staging").exists()


def test_worktree_receipt_must_match_receipt_at_pinned_ancestor(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    (repo / loaded.plan.baseline_receipt_path).write_text("changed\n", encoding="utf-8")

    with pytest.raises(module.BaselineVerificationError, match="worktree receipt"):
        module.run_dry_run_preflight(
            loaded_plan=loaded,
            repo_root=repo,
            data_root=data_root,
        )


def test_resolved_source_alias_outside_raw_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    target = data_root.joinpath(*loaded.plan.targets[0].existing_local_relative_path.split("/"))
    original_resolve = Path.resolve

    def resolve_with_escape(path: Path, strict: bool = False) -> Path:
        if Path(path) == target:
            return (tmp_path / "outside.pdf").resolve()
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_escape)

    with pytest.raises(module.ProtectedSourcePathError, match="resolved"):
        module.run_dry_run_preflight(
            loaded_plan=loaded,
            repo_root=repo,
            data_root=data_root,
        )


def test_dry_run_result_writes_only_to_repository_cache_after_preflight(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    before = _snapshot_tree(data_root)
    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )
    output = repo / ".cache" / "m1-03a" / "dry-run.json"

    module.write_dry_run_result(
        output,
        result,
        repo_root=repo,
        data_root=data_root,
    )
    module.write_dry_run_result(
        output,
        result,
        repo_root=repo,
        data_root=data_root,
    )

    assert output.is_file()
    assert output.read_bytes().endswith(b"\n")
    assert b'"network_requests":0' in output.read_bytes()
    assert b'"dropbox_writes":0' in output.read_bytes()
    assert str(data_root).encode() not in output.read_bytes()
    assert _snapshot_tree(data_root) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
@pytest.mark.parametrize("operation", ["open", "publish"])
def test_dry_run_output_parent_swap_at_lease_boundary_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    from peru_conflicts.acquisition.fs_safety import DirectoryLease

    repo, data_root, loaded, _ = _fixture(tmp_path)
    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )
    output = repo / ".cache" / "m1-03a" / "dry-run.json"
    output.parent.mkdir(parents=True)
    saved_parent = repo / ".cache" / f"m1-03a-{operation}-saved"
    before = _snapshot_tree(data_root)
    real_open = DirectoryLease.open_child_exclusive
    real_publish = DirectoryLease.rename_child_no_replace
    swapped = False

    def swap_parent() -> None:
        nonlocal swapped
        swapped = True
        output.parent.rename(saved_parent)
        _make_directory_alias(output.parent, data_root)

    def restore_parent() -> None:
        if not saved_parent.exists():
            return
        if output.parent.exists():
            output.parent.rmdir()
        saved_parent.rename(output.parent)

    def open_with_parent_swap(lease: DirectoryLease, name: str) -> BinaryIO:
        if operation == "open" and not swapped and name.endswith(".tmp"):
            swap_parent()
            try:
                return real_open(lease, name)
            finally:
                restore_parent()
        return real_open(lease, name)

    def publish_with_parent_swap(
        lease: DirectoryLease, source_name: str, destination_name: str
    ) -> None:
        if operation == "publish" and not swapped and destination_name == output.name:
            swap_parent()
            try:
                real_publish(lease, source_name, destination_name)
            finally:
                restore_parent()
            return
        real_publish(lease, source_name, destination_name)

    monkeypatch.setattr(DirectoryLease, "open_child_exclusive", open_with_parent_swap)
    monkeypatch.setattr(DirectoryLease, "rename_child_no_replace", publish_with_parent_swap)

    try:
        with pytest.raises(module.DryRunOutputError, match="could not remain bound"):
            module.write_dry_run_result(
                output,
                result,
                repo_root=repo,
                data_root=data_root,
            )
    finally:
        restore_parent()

    assert swapped is True
    assert _snapshot_tree(data_root) == before
    assert not output.exists()
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_dry_run_output_rejects_outside_cache_and_cleans_interrupted_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.preflight")
    repo, data_root, loaded, _ = _fixture(tmp_path)
    result = module.run_dry_run_preflight(
        loaded_plan=loaded,
        repo_root=repo,
        data_root=data_root,
    )
    outside = tmp_path / "outside" / "dry-run.json"
    with pytest.raises(module.DryRunOutputError, match=r"repository \.cache"):
        module.write_dry_run_result(
            outside,
            result,
            repo_root=repo,
            data_root=data_root,
        )
    assert not outside.parent.exists()

    output = repo / ".cache" / "m1-03a" / "interrupted.json"

    from peru_conflicts.acquisition.fs_safety import DirectoryLease

    def interrupt_publish(_: DirectoryLease, __: str, ___: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(DirectoryLease, "rename_child_no_replace", interrupt_publish)
    with pytest.raises(KeyboardInterrupt):
        module.write_dry_run_result(
            output,
            result,
            repo_root=repo,
            data_root=data_root,
        )
    assert not output.exists()
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []
