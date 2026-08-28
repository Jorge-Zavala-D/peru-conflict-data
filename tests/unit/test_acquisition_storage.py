from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
from pathlib import Path

import pytest

from peru_conflicts.acquisition.fs_safety import DirectoryLease


def _pdf(marker: bytes = b"x") -> bytes:
    return b"%PDF-1.7\n" + marker * 1200


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


def test_copy_rehash_and_no_replace_publication(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.storage import PublishStatus, stage_copy_and_publish_no_replace

    content = _pdf()
    source = tmp_path / "system-temp" / "download.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    staging = tmp_path / "raw" / ".staging"
    raw = tmp_path / "raw"
    destination = raw / "reports" / "report.pdf"
    destination.parent.mkdir(parents=True)

    result = stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=staging,
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert result.status is PublishStatus.PUBLISHED
    assert destination.read_bytes() == content
    assert source.read_bytes() == content
    assert not list(staging.glob("*.stage"))


def test_shared_raw_staging_root_can_publish_to_nested_report_directory(
    tmp_path: Path,
) -> None:
    from peru_conflicts.acquisition.storage import PublishStatus, stage_copy_and_publish_no_replace

    content = _pdf()
    source = tmp_path / "system-temp" / "download.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "01_raw"
    raw.mkdir()
    destination = raw / "reports" / "2026" / "report-269.pdf"

    result = stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=raw / ".staging" / "m1-03-pilot",
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert result.status is PublishStatus.PUBLISHED
    assert destination.read_bytes() == content


def test_idempotent_existing_identical_object_is_not_rewritten(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.storage import PublishStatus, stage_copy_and_publish_no_replace

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    raw = tmp_path / "raw"
    destination = raw / "reports" / "report.pdf"
    destination.parent.mkdir(parents=True)
    source.write_bytes(content)
    destination.write_bytes(content)
    before = destination.stat().st_mtime_ns

    result = stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=tmp_path / "raw" / ".staging",
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert result.status is PublishStatus.ALREADY_PRESENT_IDENTICAL
    assert destination.stat().st_mtime_ns == before


def test_same_name_different_bytes_stops_without_overwrite(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.storage import (
        DestinationConflict,
        stage_copy_and_publish_no_replace,
    )

    content = _pdf(b"a")
    existing = _pdf(b"b")
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    raw = tmp_path / "raw"
    destination = raw / "reports" / "report.pdf"
    destination.parent.mkdir(parents=True)
    source.write_bytes(content)
    destination.write_bytes(existing)

    with pytest.raises(DestinationConflict, match="different bytes"):
        stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=tmp_path / "raw" / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert destination.read_bytes() == existing


def test_interrupted_copy_removes_only_owned_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    staging = tmp_path / "raw" / ".staging"
    staging.mkdir(parents=True)
    unrelated = staging / "other-run.stage"
    unrelated.write_bytes(b"preserve")

    def interrupted_copy(
        _source_directory: DirectoryLease,
        _source_name: str,
        stage_directory: DirectoryLease,
        stage_name: str,
    ) -> tuple[int, str]:
        with stage_directory.open_child_exclusive(stage_name) as stage:
            stage.write(b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(storage, "_copy_between_leases", interrupted_copy)
    with pytest.raises(KeyboardInterrupt):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=tmp_path / "raw",
            staging_dir=staging,
            destination=tmp_path / "raw" / "reports" / "report.pdf",
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert unrelated.read_bytes() == b"preserve"
    assert list(staging.glob("*.stage")) == [unrelated]


def test_stage_rehash_mismatch_cleans_stage_and_does_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    (tmp_path / "raw").mkdir()
    real_fingerprint = storage._fingerprint_bound_file  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def corrupt_second_fingerprint(directory: DirectoryLease, name: str) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        size, digest = real_fingerprint(directory, name)
        return (size, "0" * 64) if calls == 2 else (size, digest)

    monkeypatch.setattr(storage, "_fingerprint_bound_file", corrupt_second_fingerprint)
    destination = tmp_path / "raw" / "reports" / "report.pdf"
    with pytest.raises(storage.StageIntegrityError, match="rehash"):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=tmp_path / "raw",
            staging_dir=tmp_path / "raw" / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert not destination.exists()
    assert not list((tmp_path / "raw" / ".staging").glob("*.stage"))


def test_different_device_is_rejected_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    staging = tmp_path / "raw" / ".staging"
    destination = tmp_path / "raw" / "reports" / "report.pdf"
    destination.parent.mkdir(parents=True)
    staging.mkdir()
    real_device = storage.filesystem_device

    def different_device(path: Path) -> int:
        return real_device(path) + (1 if path == staging else 0)

    monkeypatch.setattr(storage, "filesystem_device", different_device)
    with pytest.raises(storage.CrossDeviceStageError):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=tmp_path / "raw",
            staging_dir=staging,
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert not destination.exists()


def test_destination_race_preserves_competing_file_and_cleans_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf(b"a")
    competing = _pdf(b"b")
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    (tmp_path / "raw").mkdir()
    destination = tmp_path / "raw" / "reports" / "report.pdf"

    def race(
        _stage_directory: DirectoryLease,
        _stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        with target_directory.open_child_exclusive(target_name) as target:
            target.write(competing)
        raise FileExistsError(target_name)

    monkeypatch.setattr(storage, "_publish_no_replace", race)
    with pytest.raises(storage.DestinationConflict):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=tmp_path / "raw",
            staging_dir=tmp_path / "raw" / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert destination.read_bytes() == competing
    assert not list((tmp_path / "raw" / ".staging").glob("*.stage"))


def test_destination_race_rejects_hardlink_alias_even_when_bytes_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = raw / "reports" / "report.pdf"
    external = tmp_path / "external.pdf"
    external.write_bytes(content)

    def race_with_hardlink(
        _stage_directory: DirectoryLease,
        _stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        target_directory.child_path(target_name).hardlink_to(external)
        raise FileExistsError(target_name)

    monkeypatch.setattr(storage, "_publish_no_replace", race_with_hardlink)
    with pytest.raises(storage.PathBoundaryError, match="hardlink"):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert external.read_bytes() == content
    assert destination.exists()


def test_destination_parent_swap_at_publish_cannot_create_outside_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = raw / "reports" / "report.pdf"
    outside = tmp_path / "outside"
    outside.mkdir()
    saved_reports = raw / "reports-saved"
    real_publish = storage._publish_no_replace  # pyright: ignore[reportPrivateUsage]
    swap_blocked = False

    def swap_then_publish(
        stage_directory: DirectoryLease,
        stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        nonlocal swap_blocked
        try:
            destination.parent.rename(saved_reports)
        except OSError:
            swap_blocked = True
            real_publish(stage_directory, stage_name, target_directory, target_name)
            return
        try:
            _make_directory_alias(destination.parent, outside)
            real_publish(stage_directory, stage_name, target_directory, target_name)
        finally:
            if destination.parent.is_symlink():
                destination.parent.unlink()
            elif destination.parent.exists():
                destination.parent.rmdir()
            saved_reports.rename(destination.parent)

    monkeypatch.setattr(storage, "_publish_no_replace", swap_then_publish)

    try:
        result = storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )
    except storage.PathBoundaryError:
        result = None

    assert swap_blocked or result is None
    assert not list(outside.iterdir())
    assert not list((raw / ".staging").glob("*.stage"))


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_parent_swap_inside_stage_open_cannot_escape_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    staging = raw / ".staging"
    saved_staging = raw / ".staging-saved"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = raw / "reports" / "report.pdf"
    real_open = fs_safety.os.open
    attacked = False

    def swap_only_inside_open(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal attacked
        candidate = Path(path)
        if not attacked and candidate.name.endswith(".stage"):
            attacked = True
            staging.rename(saved_staging)
            _make_directory_alias(staging, outside)
            try:
                return real_open(path, flags, mode, dir_fd=dir_fd)
            finally:
                staging.rmdir()
                saved_staging.rename(staging)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(fs_safety.os, "open", swap_only_inside_open)

    result = storage.stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=staging,
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert attacked is False
    assert result.status is storage.PublishStatus.PUBLISHED
    assert destination.read_bytes() == content
    assert not list(outside.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_native_relative_stage_open_remains_bound_during_parent_swap(
    tmp_path: Path,
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety

    content = _pdf()
    raw = tmp_path / "raw"
    staging = raw / ".staging"
    saved_staging = raw / ".staging-saved"
    outside = tmp_path / "outside"
    staging.mkdir(parents=True)
    outside.mkdir()
    stage_name = ".report.pdf.synthetic.stage"

    with DirectoryLease.acquire(staging) as lease:
        staging.rename(saved_staging)
        _make_directory_alias(staging, outside)
        try:
            descriptor = fs_safety._windows_open_relative_file_descriptor(  # pyright: ignore[reportPrivateUsage]
                lease.windows_handle,
                stage_name,
                write_exclusive=True,
            )
            try:
                os.write(descriptor, content)
            finally:
                os.close(descriptor)
            assert (saved_staging / stage_name).read_bytes() == content
        finally:
            staging.rmdir()
            saved_staging.rename(staging)

    assert (staging / stage_name).read_bytes() == content
    assert not list(outside.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_parent_swap_inside_publish_rename_cannot_escape_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    reports = raw / "reports"
    saved_reports = raw / "reports-saved"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = reports / "report.pdf"
    real_rename = fs_safety.os.rename
    attacked = False

    def swap_only_inside_rename(
        source_path: str | os.PathLike[str],
        destination_path: str | os.PathLike[str],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal attacked
        candidate = Path(source_path)
        if not attacked and candidate.name.endswith(".stage"):
            attacked = True
            reports.rename(saved_reports)
            _make_directory_alias(reports, outside)
            try:
                real_rename(
                    source_path,
                    destination_path,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )
            finally:
                reports.rmdir()
                saved_reports.rename(reports)
            return
        real_rename(
            source_path,
            destination_path,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(fs_safety.os, "rename", swap_only_inside_rename)

    result = storage.stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=raw / ".staging",
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert attacked is False
    assert result.status is storage.PublishStatus.PUBLISHED
    assert destination.read_bytes() == content
    assert not list(outside.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_native_relative_publish_remains_bound_during_parent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    reports = raw / "reports"
    saved_reports = raw / "reports-saved"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = reports / "report.pdf"
    real_rename = (
        fs_safety._windows_rename_relative_no_replace  # pyright: ignore[reportPrivateUsage]
    )
    attacked = False

    def swap_around_native_rename(
        source_root_handle: int,
        source_name: str,
        destination_root_handle: int,
        destination_name: str,
    ) -> None:
        nonlocal attacked
        if not attacked and source_name.endswith(".stage"):
            attacked = True
            reports.rename(saved_reports)
            _make_directory_alias(reports, outside)
            try:
                real_rename(
                    source_root_handle,
                    source_name,
                    destination_root_handle,
                    destination_name,
                )
            finally:
                reports.rmdir()
                saved_reports.rename(reports)
            return
        real_rename(
            source_root_handle,
            source_name,
            destination_root_handle,
            destination_name,
        )

    monkeypatch.setattr(
        fs_safety,
        "_windows_rename_relative_no_replace",
        swap_around_native_rename,
    )

    result = storage.stage_copy_and_publish_no_replace(
        source_temp=source,
        system_temp_root=tmp_path / "system-temp",
        raw_root=raw,
        staging_dir=raw / ".staging",
        destination=destination,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
    )

    assert attacked is True
    assert result.status is storage.PublishStatus.PUBLISHED
    assert destination.read_bytes() == content
    assert not list(outside.iterdir())


def test_interrupt_after_atomic_publish_is_reconciled_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = raw / "reports" / "report.pdf"
    real_publish = storage._publish_no_replace  # pyright: ignore[reportPrivateUsage]

    def publish_then_interrupt(
        stage_directory: DirectoryLease,
        stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        real_publish(stage_directory, stage_name, target_directory, target_name)
        raise KeyboardInterrupt

    monkeypatch.setattr(storage, "_publish_no_replace", publish_then_interrupt)

    with pytest.raises(storage.PublishCommittedAfterInterrupt) as interrupted:
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert (
        interrupted.value.result.status
        is storage.PublishStatus.PUBLISHED_AFTER_INTERRUPT_RECONCILED
    )
    assert destination.read_bytes() == content
    assert not list((raw / ".staging").glob("*.stage"))


def test_interrupt_between_link_and_stage_unlink_is_reconciled_before_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = raw / "reports" / "report.pdf"

    def link_then_interrupt(
        stage_directory: DirectoryLease,
        stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        target_directory.child_path(target_name).hardlink_to(stage_directory.child_path(stage_name))
        raise KeyboardInterrupt

    monkeypatch.setattr(storage, "_publish_no_replace", link_then_interrupt)

    with pytest.raises(storage.PublishCommittedAfterInterrupt) as interrupted:
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert (
        interrupted.value.result.status
        is storage.PublishStatus.PUBLISHED_AFTER_INTERRUPT_RECONCILED
    )
    assert destination.read_bytes() == content
    assert destination.stat().st_nlink == 1
    assert not list((raw / ".staging").glob("*.stage"))


def test_error_after_atomic_publish_carries_verified_committed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    destination = raw / "reports" / "report.pdf"
    real_publish = storage._publish_no_replace  # pyright: ignore[reportPrivateUsage]

    def publish_then_error(
        stage_directory: DirectoryLease,
        stage_name: str,
        target_directory: DirectoryLease,
        target_name: str,
    ) -> None:
        real_publish(stage_directory, stage_name, target_directory, target_name)
        raise OSError("synthetic post-publication failure")

    monkeypatch.setattr(storage, "_publish_no_replace", publish_then_error)

    with pytest.raises(storage.PublishCommittedAfterError) as committed:
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert (
        committed.value.result.status is storage.PublishStatus.PUBLISHED_AFTER_INTERRUPT_RECONCILED
    )
    assert destination.read_bytes() == content
    assert not list((raw / ".staging").glob("*.stage"))


def test_stage_parent_swap_cannot_create_stage_outside_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    source = tmp_path / "system-temp" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    raw.mkdir()
    staging = raw / ".staging"
    destination = raw / "reports" / "report.pdf"
    outside = tmp_path / "outside-stage"
    outside.mkdir()
    saved_staging = raw / ".staging-saved"
    real_copy = storage._copy_between_leases  # pyright: ignore[reportPrivateUsage]
    swap_blocked = False

    def swap_then_copy(
        source_directory: DirectoryLease,
        source_name: str,
        stage_directory: DirectoryLease,
        stage_name: str,
    ) -> tuple[int, str]:
        nonlocal swap_blocked
        try:
            staging.rename(saved_staging)
        except OSError:
            swap_blocked = True
            return real_copy(source_directory, source_name, stage_directory, stage_name)
        try:
            _make_directory_alias(staging, outside)
            return real_copy(source_directory, source_name, stage_directory, stage_name)
        finally:
            if staging.is_symlink():
                staging.unlink()
            elif staging.exists():
                staging.rmdir()
            saved_staging.rename(staging)

    monkeypatch.setattr(storage, "_copy_between_leases", swap_then_copy)

    try:
        result = storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=tmp_path / "system-temp",
            raw_root=raw,
            staging_dir=staging,
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )
    except storage.PathBoundaryError:
        result = None

    assert swap_blocked or result is None
    assert not list(outside.iterdir())


@pytest.mark.parametrize("unsafe_part", ("source", "staging", "destination"))
def test_publication_rejects_paths_outside_explicit_roots_before_writing(
    tmp_path: Path, unsafe_part: str
) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    system_temp = tmp_path / "system-temp"
    raw = tmp_path / "raw"
    source = system_temp / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    staging = raw / ".staging" / "pilot"
    destination = raw / "reports" / "2026" / "report.pdf"
    outside = tmp_path / "outside"
    if unsafe_part == "source":
        source = outside / "source.pdf"
        source.parent.mkdir()
        source.write_bytes(content)
    elif unsafe_part == "staging":
        staging = outside / "staging"
    else:
        destination = outside / "report.pdf"

    with pytest.raises(storage.PathBoundaryError):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=system_temp,
            raw_root=raw,
            staging_dir=staging,
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    if unsafe_part != "source":
        assert not outside.exists()


def test_existing_destination_symlink_is_never_accepted_as_identical(tmp_path: Path) -> None:
    import peru_conflicts.acquisition.storage as storage

    content = _pdf()
    system_temp = tmp_path / "system-temp"
    source = system_temp / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(content)
    raw = tmp_path / "raw"
    destination = raw / "reports" / "report.pdf"
    destination.parent.mkdir(parents=True)
    external = tmp_path / "external.pdf"
    external.write_bytes(content)
    try:
        destination.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this Windows host")

    with pytest.raises(storage.PathBoundaryError, match="reparse"):
        storage.stage_copy_and_publish_no_replace(
            source_temp=source,
            system_temp_root=system_temp,
            raw_root=raw,
            staging_dir=raw / ".staging",
            destination=destination,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_bytes=len(content),
        )

    assert external.read_bytes() == content


def test_raw_publication_implementation_never_uses_os_replace() -> None:
    import peru_conflicts.acquisition.storage as storage

    assert "os.replace" not in inspect.getsource(storage)
