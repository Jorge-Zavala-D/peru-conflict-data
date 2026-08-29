from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.authorization import compute_data_root_identity_sha256
from peru_conflicts.acquisition.compare_runner import (
    BoundProtectedSources,
    CompareTarget,
    LocalSourceMismatch,
)
from peru_conflicts.acquisition.engine import (
    TemporaryPathBoundaryError,
    lease_system_temp_run_directory,
)
from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.acquisition.models_v2 import DurableRunOpenedV2, StorageNamespaceMarkerV2
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.storage import (
    PublishStatus,
    stage_copy_and_publish_no_replace,
)

pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="requires native Windows directory-handle operations",
)


def _protected_target(data_root: Path) -> CompareTarget:
    content = b"%PDF-1.7\nnative protected-source binding\n"
    source = data_root / "01_raw" / "reports" / "2025" / "report-260.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    return CompareTarget(
        report_number=260,
        landing_url="https://www.defensoria.gob.pe/documentos/reporte-260/",
        direct_download_url=("https://www.defensoria.gob.pe/wp-content/uploads/report-260.pdf"),
        protected_source_path=source,
        expected_byte_count=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
        association_status="visibly_associated",
    )


def test_windows_directory_lease_native_child_lifecycle(tmp_path: Path) -> None:
    bound_directory = tmp_path / "bound"
    bound_directory.mkdir()
    payload = b"native Windows handle-relative child operations"

    with DirectoryLease.acquire(bound_directory) as lease:
        with lease.open_child_exclusive("source.partial") as child:
            child.write(payload)

        with lease.open_child_read("source.partial") as child:
            assert child.read() == payload

        lease.rename_child_no_replace("source.partial", "published.pdf")

        assert not lease.child_exists("source.partial")
        with lease.open_child_read("published.pdf") as child:
            assert child.read() == payload
        assert lease.child_path("published.pdf").resolve().parent == bound_directory.resolve()

        lease.unlink_child("published.pdf")
        assert not lease.child_exists("published.pdf")

    assert list(bound_directory.iterdir()) == []


def test_windows_native_protected_source_parent_and_file_binding(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    target = _protected_target(data_root)

    with BoundProtectedSources.open(data_root=data_root, targets=(target,)) as sources:
        assert sources.fingerprint(target) == (
            target.expected_byte_count,
            target.expected_sha256,
        )


def test_windows_native_protected_source_detects_bound_parent_replacement(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    target = _protected_target(data_root)
    year = data_root / "01_raw" / "reports" / "2025"
    displaced = tmp_path / "displaced-2025"
    original_bytes = target.protected_source_path.read_bytes()

    with BoundProtectedSources.open(data_root=data_root, targets=(target,)) as sources:
        try:
            year.rename(displaced)
        except PermissionError:
            assert sources.fingerprint(target) == (
                target.expected_byte_count,
                target.expected_sha256,
            )
            return
        year.mkdir()
        (year / target.protected_source_path.name).write_bytes(original_bytes)
        with pytest.raises(LocalSourceMismatch, match="parent binding"):
            sources.fingerprint(target)


def test_windows_native_protected_source_rejects_intermediate_junction(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    target = _protected_target(data_root)
    reports = data_root / "01_raw" / "reports"
    outside = tmp_path / "outside-reports"
    reports.rename(outside)
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(reports), str(outside)],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(LocalSourceMismatch, match="parent binding"):
        BoundProtectedSources.open(data_root=data_root, targets=(target,))


def test_windows_native_system_temp_chain_rejects_intermediate_junction(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-temp"
    outside.mkdir()
    redirected_parent = tmp_path / "redirected-temp-parent"
    subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(redirected_parent),
            str(outside),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with (
        pytest.raises(TemporaryPathBoundaryError),
        lease_system_temp_run_directory(
            redirected_parent / "system-temp",
            "native-junction-run",
            create=True,
        ),
    ):
        raise AssertionError("unsafe temporary junction was leased")


def test_windows_native_publication_smoke(tmp_path: Path) -> None:
    content = b"%PDF-1.7\n" + (b"synthetic native Windows publication\n" * 64)
    system_temp_root = tmp_path / "system-temp"
    system_temp_root.mkdir()
    source = system_temp_root / "download.pdf"
    source.write_bytes(content)

    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    staging = raw_root / ".staging" / "native-smoke"
    destination = raw_root / "reports" / "report.pdf"

    result = stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=system_temp_root,
        raw_root=raw_root,
        staging_dir=staging,
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert result.status is PublishStatus.PUBLISHED
    assert destination.read_bytes() == content
    assert destination.resolve().is_relative_to(raw_root.resolve())
    assert list(staging.iterdir()) == []


def test_windows_native_hash_chained_manifest_append_and_resume(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "01_raw" / "manifests").mkdir(parents=True)
    nonce = "a" * 64
    host_sha256 = "b" * 64
    marker = StorageNamespaceMarkerV2(
        schema_version="0.2.0",
        namespace_id="native-windows-smoke",
        owner_nonce_sha256=nonce,
    )
    identity = compute_data_root_identity_sha256(
        data_root,
        marker_nonce_sha256=nonce,
        execution_host_identity_sha256=host_sha256,
    )
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

    with ManifestLedgerStore.open(
        data_root=data_root,
        marker=marker,
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=host_sha256,
        expected_execution_tree_sha256="c" * 64,
        expected_authorization_artifact_sha256="d" * 64,
        authorization_id="native-authorization",
        run_id="native-run",
        plan_id="native-plan",
        recorded_at=now,
    ) as store:
        store.append(
            DurableRunOpenedV2(
                schema_version="0.2.0",
                record_type="run_opened",
                record_id="run-opened",
                authorization_id="native-authorization",
                run_id="native-run",
                plan_id="native-plan",
                sequence=store.next_sequence,
                previous_record_sha256=store.ledger_head_sha256,
                recorded_at=now,
                authorization_artifact_sha256="d" * 64,
                execution_tree_sha256="c" * 64,
                data_root_identity_sha256=identity,
                execution_host_identity_sha256=host_sha256,
            )
        )
        assert store.ledger_path.read_bytes().endswith(b"\n")
        assert store.index_path.read_bytes().endswith(b"\n")

    with ManifestLedgerStore.open(
        data_root=data_root,
        marker=marker,
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=host_sha256,
        expected_execution_tree_sha256="c" * 64,
        expected_authorization_artifact_sha256="d" * 64,
        authorization_id="native-authorization",
        run_id="native-run",
        plan_id="native-plan",
        recorded_at=now,
    ) as resumed:
        assert len(resumed.records) == 1
        assert resumed.records[0].record_type == "run_opened"
