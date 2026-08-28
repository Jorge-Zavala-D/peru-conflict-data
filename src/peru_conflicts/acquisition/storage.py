"""No-overwrite publication primitives, used only with temporary test roots in M1-03A."""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from peru_conflicts.acquisition.fs_safety import (
    DirectoryLease,
    DirectoryLeaseError,
    rename_between_directories_no_replace,
)


class StorageError(RuntimeError):
    """Base error for a rejected future storage transition."""


class DestinationConflict(StorageError):
    """A destination name already identifies different bytes."""


class StageIntegrityError(StorageError):
    """The source, copy stream, or staged rehash did not match the expected object."""


class CrossDeviceStageError(StorageError):
    """The stage and destination directories do not share a filesystem."""


class PathBoundaryError(StorageError):
    """A publication path escaped, aliased, or violated its explicit root."""


class PublishCommittedAfterInterrupt(KeyboardInterrupt):
    """Cancellation occurred after a verified destination had been committed."""

    def __init__(self, result: PublishResult) -> None:
        super().__init__("publication committed before interruption")
        self.result = result


class PublishCommittedAfterError(StorageError):
    """An error occurred after a verified destination had been committed."""

    def __init__(self, result: PublishResult, error: BaseException) -> None:
        super().__init__(f"publication committed before {type(error).__name__}")
        self.result = result


class PublishStatus(StrEnum):
    PUBLISHED = "published"
    ALREADY_PRESENT_IDENTICAL = "already_present_identical"
    PUBLISHED_AFTER_INTERRUPT_RECONCILED = "published_after_interrupt_reconciled"


@dataclass(frozen=True, slots=True)
class PublishResult:
    status: PublishStatus
    destination: Path
    byte_count: int
    sha256: str


def filesystem_device(path: Path) -> int:
    return path.stat().st_dev


def _publish_no_replace(
    stage_directory: DirectoryLease,
    stage_name: str,
    destination_directory: DirectoryLease,
    destination_name: str,
) -> None:
    """Publish between identity-bound directories without replacement."""

    rename_between_directories_no_replace(
        stage_directory,
        stage_name,
        destination_directory,
        destination_name,
    )


def _absolute_logical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = cast(int, getattr(path.lstat(), "st_file_attributes", 0))
    except (FileNotFoundError, OSError):
        return False
    marker = cast(int, getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return bool(marker and attributes & marker)


def _require_existing_root(path: Path, *, label: str) -> tuple[Path, Path]:
    logical = _absolute_logical(path)
    if _is_reparse_point(logical):
        raise PathBoundaryError(f"{label} root cannot be a symlink or reparse point")
    if not logical.is_dir():
        raise PathBoundaryError(f"{label} root must be an existing directory")
    return logical, logical.resolve(strict=True)


def _validate_child_path(
    path: Path,
    *,
    logical_boundary: Path,
    resolved_boundary: Path,
    label: str,
) -> Path:
    logical = _absolute_logical(path)
    if not logical.is_relative_to(logical_boundary):
        raise PathBoundaryError(f"{label} escapes its logical root")

    relative = logical.relative_to(logical_boundary)
    cursor = logical_boundary
    for part in relative.parts:
        cursor /= part
        if not os.path.lexists(cursor):
            break
        if _is_reparse_point(cursor):
            raise PathBoundaryError(f"{label} contains a symlink or reparse point")
        resolved = cursor.resolve(strict=True)
        if not resolved.is_relative_to(resolved_boundary):
            raise PathBoundaryError(f"{label} escapes its resolved root")

    nearest = logical
    while not os.path.lexists(nearest):
        if nearest.parent == nearest:
            raise PathBoundaryError(f"{label} has no resolvable existing ancestor")
        nearest = nearest.parent
    if not nearest.resolve(strict=True).is_relative_to(resolved_boundary):
        raise PathBoundaryError(f"{label} escapes its resolved root")
    return logical


def _lease_relative_directory(
    *,
    root: DirectoryLease,
    relative_parts: tuple[str, ...],
    stack: ExitStack,
    create: bool,
) -> DirectoryLease:
    current = root
    for part in relative_parts:
        current = stack.enter_context(current.acquire_child(part, create=create))
    return current


def _fingerprint_bound_file(directory: DirectoryLease, name: str) -> tuple[int, str]:
    try:
        before = directory.child_lstat(name)
        if not stat.S_ISREG(before.st_mode):
            raise PathBoundaryError("bound file must be a regular file")
        if before.st_nlink != 1:
            raise PathBoundaryError("bound file cannot be a hardlink alias")
        digest = hashlib.sha256()
        byte_count = 0
        with directory.open_child_read(name) as source:
            opened = os.fstat(source.fileno())
            if opened.st_nlink != 1:
                raise PathBoundaryError("bound file cannot be a hardlink alias")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                byte_count += len(chunk)
                digest.update(chunk)
        after = directory.child_lstat(name)
    except DirectoryLeaseError as error:
        raise PathBoundaryError("bound file could not be inspected safely") from error
    identities = {
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink),
        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink),
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink),
    }
    if len(identities) != 1 or byte_count != opened.st_size:
        raise PathBoundaryError("bound file changed during inspection")
    return byte_count, digest.hexdigest()


def _copy_between_leases(
    source_directory: DirectoryLease,
    source_name: str,
    stage_directory: DirectoryLease,
    stage_name: str,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with source_directory.open_child_read(source_name) as source:
            source_before = os.fstat(source.fileno())
            if source_before.st_nlink != 1:
                raise PathBoundaryError("temporary source cannot be a hardlink alias")
            with stage_directory.open_child_exclusive(stage_name) as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    byte_count += len(chunk)
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            source_after = os.fstat(source.fileno())
    except DirectoryLeaseError as error:
        raise PathBoundaryError("stage copy could not remain directory-bound") from error
    source_id_before = (
        source_before.st_dev,
        source_before.st_ino,
        source_before.st_size,
        source_before.st_mtime_ns,
        source_before.st_nlink,
    )
    source_id_after = (
        source_after.st_dev,
        source_after.st_ino,
        source_after.st_size,
        source_after.st_mtime_ns,
        source_after.st_nlink,
    )
    if source_id_before != source_id_after or byte_count != source_before.st_size:
        raise StageIntegrityError("temporary source changed during stage copy")
    return byte_count, digest.hexdigest()


def _existing_bound_result(
    directory: DirectoryLease,
    name: str,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> PublishResult:
    observed_bytes, observed_sha256 = _fingerprint_bound_file(directory, name)
    if observed_bytes != expected_bytes or observed_sha256 != expected_sha256:
        raise DestinationConflict("destination already exists with different bytes")
    return PublishResult(
        status=PublishStatus.ALREADY_PRESENT_IDENTICAL,
        destination=directory.child_path(name),
        byte_count=observed_bytes,
        sha256=observed_sha256,
    )


def stage_copy_and_publish_no_replace(
    *,
    source_temp: Path,
    system_temp_root: Path,
    raw_root: Path,
    staging_dir: Path,
    destination: Path,
    expected_sha256: str,
    expected_bytes: int,
) -> PublishResult:
    """Copy, independently rehash, and publish without overwriting a raw object."""

    system_logical, system_resolved = _require_existing_root(
        system_temp_root, label="system temporary"
    )
    raw_logical, raw_resolved = _require_existing_root(raw_root, label="raw")
    if (
        system_logical.is_relative_to(raw_logical)
        or raw_logical.is_relative_to(system_logical)
        or system_resolved.is_relative_to(raw_resolved)
        or raw_resolved.is_relative_to(system_resolved)
    ):
        raise PathBoundaryError("system temporary and raw roots must not overlap")

    source_logical = _validate_child_path(
        source_temp,
        logical_boundary=system_logical,
        resolved_boundary=system_resolved,
        label="temporary source",
    )
    if _is_reparse_point(source_logical):
        raise PathBoundaryError("temporary source cannot be a symlink or reparse point")
    if not source_logical.is_file():
        raise StageIntegrityError("temporary source is not an existing regular file")

    staging_boundary_logical = raw_logical / ".staging"
    staging_logical = _validate_child_path(
        staging_dir,
        logical_boundary=staging_boundary_logical,
        resolved_boundary=raw_resolved,
        label="staging directory",
    )
    reports_boundary_logical = raw_logical / "reports"
    destination_logical = _validate_child_path(
        destination,
        logical_boundary=reports_boundary_logical,
        resolved_boundary=raw_resolved,
        label="raw destination",
    )

    source_relative = source_logical.relative_to(system_logical)
    staging_relative = staging_logical.relative_to(raw_logical)
    destination_relative = destination_logical.relative_to(raw_logical)
    stage_name = f".{destination_logical.name}.{uuid.uuid4().hex}.stage"

    try:
        with ExitStack() as stack:
            system_lease = stack.enter_context(DirectoryLease.acquire(system_logical))
            raw_lease = stack.enter_context(DirectoryLease.acquire(raw_logical))
            source_parent = _lease_relative_directory(
                root=system_lease,
                relative_parts=source_relative.parent.parts,
                stack=stack,
                create=False,
            )
            stage_directory = _lease_relative_directory(
                root=raw_lease,
                relative_parts=staging_relative.parts,
                stack=stack,
                create=True,
            )
            destination_directory = _lease_relative_directory(
                root=raw_lease,
                relative_parts=destination_relative.parent.parts,
                stack=stack,
                create=True,
            )
            if filesystem_device(stage_directory.path) != filesystem_device(
                destination_directory.path
            ):
                raise CrossDeviceStageError(
                    "staging and destination directories are on different devices"
                )

            source_bytes, source_sha256 = _fingerprint_bound_file(
                source_parent, source_relative.name
            )
            if source_bytes != expected_bytes or source_sha256 != expected_sha256:
                raise StageIntegrityError(
                    "temporary source does not match expected size and SHA-256"
                )
            if destination_directory.child_exists(destination_relative.name):
                return _existing_bound_result(
                    destination_directory,
                    destination_relative.name,
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                )

            try:
                copied_bytes, copied_sha256 = _copy_between_leases(
                    source_parent,
                    source_relative.name,
                    stage_directory,
                    stage_name,
                )
                if copied_bytes != expected_bytes or copied_sha256 != expected_sha256:
                    raise StageIntegrityError("stage copy stream does not match expected bytes")
                staged_bytes, staged_sha256 = _fingerprint_bound_file(stage_directory, stage_name)
                if staged_bytes != expected_bytes or staged_sha256 != expected_sha256:
                    raise StageIntegrityError("stage rehash does not match expected bytes")
                try:
                    _publish_no_replace(
                        stage_directory,
                        stage_name,
                        destination_directory,
                        destination_relative.name,
                    )
                except FileExistsError:
                    try:
                        return _existing_bound_result(
                            destination_directory,
                            destination_relative.name,
                            expected_bytes=expected_bytes,
                            expected_sha256=expected_sha256,
                        )
                    except DestinationConflict as conflict:
                        raise DestinationConflict(
                            "destination appeared during publication with different bytes"
                        ) from conflict
                except BaseException as error:
                    stage_directory.unlink_child(stage_name, missing_ok=True)
                    if not destination_directory.child_exists(destination_relative.name):
                        raise
                    reconciled = _existing_bound_result(
                        destination_directory,
                        destination_relative.name,
                        expected_bytes=expected_bytes,
                        expected_sha256=expected_sha256,
                    )
                    result = PublishResult(
                        status=PublishStatus.PUBLISHED_AFTER_INTERRUPT_RECONCILED,
                        destination=reconciled.destination,
                        byte_count=reconciled.byte_count,
                        sha256=reconciled.sha256,
                    )
                    if isinstance(error, KeyboardInterrupt):
                        raise PublishCommittedAfterInterrupt(result) from error
                    raise PublishCommittedAfterError(result, error) from error

                published_bytes, published_sha256 = _fingerprint_bound_file(
                    destination_directory, destination_relative.name
                )
                if published_bytes != expected_bytes or published_sha256 != expected_sha256:
                    raise StageIntegrityError("published destination failed its integrity recheck")
                return PublishResult(
                    status=PublishStatus.PUBLISHED,
                    destination=destination_directory.child_path(destination_relative.name),
                    byte_count=published_bytes,
                    sha256=published_sha256,
                )
            finally:
                stage_directory.unlink_child(stage_name, missing_ok=True)
    except DirectoryLeaseError as error:
        raise PathBoundaryError("publication directory binding failed") from error
