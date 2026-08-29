"""Production composition helpers remain deterministic and fail closed."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import cast

import pytest

from peru_conflicts.acquisition.authorization import (
    LiveComparePlatformUnsupported,
    ReviewedNetworkAuthorizationV2,
)
from peru_conflicts.acquisition.live_compare import (
    EXECUTION_TREE_REQUIRED_PATHS,
    LiveComparisonPreflightError,
    build_compare_targets,
    default_git_blob_reader,
    derive_run_id,
    execute_live_compare,
    validate_execution_manifest_paths,
    verify_protected_source_receipt,
)
from peru_conflicts.acquisition.models_v2 import ExecutionTreeEntryV2, ExecutionTreeManifestV2
from peru_conflicts.acquisition.plan import (
    REVIEWED_V2_PLAN_FILE_SHA256,
    LoadedPilotPlan,
    load_reviewed_pilot_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "config/acquisition_pilots/m1_03_reports_260_269_v2.yaml"


def _loaded_plan() -> LoadedPilotPlan:
    return load_reviewed_pilot_plan(
        PLAN_PATH,
        required_sha256=REVIEWED_V2_PLAN_FILE_SHA256,
    )


def test_compare_targets_preserve_exact_order_paths_and_opaque_uncertainty(
    tmp_path: Path,
) -> None:
    targets = build_compare_targets(_loaded_plan(), data_root=tmp_path)

    assert tuple(target.report_number for target in targets) == tuple(range(260, 270))
    assert targets[1].association_status == "unresolved_opaque_filename"
    assert targets[3].association_status == "unresolved_opaque_filename"
    assert all(
        target.association_status == "visibly_associated"
        for index, target in enumerate(targets)
        if index not in {1, 3}
    )
    assert targets[0].protected_source_path == (
        tmp_path / "01_raw/reports/2025/Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf"
    )


def test_run_id_is_deterministic_bounded_and_authorization_specific() -> None:
    first = derive_run_id("authorization-one")
    assert first == derive_run_id("authorization-one")
    assert first != derive_run_id("authorization-two")
    assert first.startswith("m103b-")
    assert len(first) <= 64
    assert first.replace("-", "").isalnum()


@pytest.mark.skipif(os.name == "nt", reason="POSIX execution preflight boundary")
def test_posix_execute_live_compare_rejects_before_repo_or_data_root_access(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo-must-not-exist"
    data_root = tmp_path / "data-must-not-exist"

    with pytest.raises(LiveComparePlatformUnsupported):
        execute_live_compare(
            loaded_plan=cast(LoadedPilotPlan, object()),
            authorization=cast(ReviewedNetworkAuthorizationV2, object()),
            repo_root=repo_root,
            data_root=data_root,
        )

    assert not repo_root.exists()
    assert not data_root.exists()


def test_execution_manifest_requires_the_exact_closed_runtime_input_set() -> None:
    assert tuple(sorted(EXECUTION_TREE_REQUIRED_PATHS)) == EXECUTION_TREE_REQUIRED_PATHS
    entries = tuple(
        ExecutionTreeEntryV2(path=path, sha256="a" * 64, byte_count=1)
        for path in EXECUTION_TREE_REQUIRED_PATHS
    )
    manifest = ExecutionTreeManifestV2.from_entries(entries)
    validate_execution_manifest_paths(manifest)

    incomplete = ExecutionTreeManifestV2.from_entries(entries[:-1])
    with pytest.raises(LiveComparisonPreflightError, match="exact closed runtime"):
        validate_execution_manifest_paths(incomplete)


def test_receipt_requires_worktree_and_pinned_commit_bytes_to_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    receipt = repo / "docs/receipt.md"
    receipt.parent.mkdir()
    receipt.write_bytes(b"reviewed receipt\n")
    expected = hashlib.sha256(receipt.read_bytes()).hexdigest()

    def committed(commit: str, path: str) -> bytes:
        assert commit == "a" * 40
        assert path == "docs/receipt.md"
        return b"reviewed receipt\n"

    verify_protected_source_receipt(
        repo_root=repo,
        relative_path="docs/receipt.md",
        expected_git_commit="a" * 40,
        expected_sha256=expected,
        git_blob_reader=committed,
    )

    receipt.write_bytes(b"working tree drift\n")
    with pytest.raises(LiveComparisonPreflightError, match="working-tree"):
        verify_protected_source_receipt(
            repo_root=repo,
            relative_path="docs/receipt.md",
            expected_git_commit="a" * 40,
            expected_sha256=expected,
            git_blob_reader=committed,
        )


def test_receipt_rejects_commit_blob_drift_even_when_worktree_matches(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    receipt = repo / "docs/receipt.md"
    receipt.parent.mkdir()
    receipt.write_bytes(b"reviewed receipt\n")
    expected = hashlib.sha256(receipt.read_bytes()).hexdigest()

    with pytest.raises(LiveComparisonPreflightError, match="Git blob"):
        verify_protected_source_receipt(
            repo_root=repo,
            relative_path="docs/receipt.md",
            expected_git_commit="b" * 40,
            expected_sha256=expected,
            git_blob_reader=lambda _commit, _path: b"different committed receipt\n",
        )


def test_default_receipt_reader_ignores_path_git_and_hostile_git_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-git-ran"
    if os.name == "nt":
        fake = fake_bin / "git.cmd"
        fake.write_text(f"@echo off\r\necho ran>{marker}\r\n", encoding="utf-8")
    else:
        fake = fake_bin / "git"
        fake.write_text(f"#!/bin/sh\necho ran > {marker}\n", encoding="utf-8")
        fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "hostile-git-dir"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "hostile-git-config"))

    content = default_git_blob_reader(REPO_ROOT)(head, "README.md")

    assert content.startswith(b"# Peru social conflict data")
    assert not marker.exists()
