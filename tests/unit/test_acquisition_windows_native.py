from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.acquisition.storage import (
    PublishStatus,
    stage_copy_and_publish_no_replace,
)

pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="requires native Windows directory-handle operations",
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
