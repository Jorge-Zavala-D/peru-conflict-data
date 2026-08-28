"""Directory-handle-bound filesystem operations for acquisition staging.

Every child mutation is resolved relative to a retained directory descriptor or
handle.  POSIX uses the ``dir_fd`` APIs.  Windows uses ``NtCreateFile`` and
``NtSetInformationFile`` with ``OBJECT_ATTRIBUTES.RootDirectory``; pathname-based
child opens and renames are deliberately forbidden because they admit a junction
swap between validation and the filesystem syscall.
"""

from __future__ import annotations

import ctypes
import errno
import os
import stat
from contextlib import AbstractContextManager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self


class DirectoryLeaseError(RuntimeError):
    """A directory could not be bound or changed safely."""


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(marker and attributes & marker)


def _safe_child_name(name: str) -> str:
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise DirectoryLeaseError("directory child name must be one safe path segment")
    return name


if os.name == "nt":
    import msvcrt

    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _DELETE = 0x00010000
    _SYNCHRONIZE = 0x00100000
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_READ_DATA = 0x0001
    _FILE_WRITE_DATA = 0x0002
    _FILE_TRAVERSE = 0x0020
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_NON_DIRECTORY_FILE = 0x00000040
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _FILE_OPEN = 1
    _FILE_CREATE = 2
    _FILE_OPEN_IF = 3
    _OBJ_CASE_INSENSITIVE = 0x00000040
    _FILE_RENAME_INFORMATION = 10
    _FILE_DISPOSITION_INFORMATION = 13

    class _UnicodeString(ctypes.Structure):
        _fields_ = (
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        )

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = (
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(_UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", wintypes.LPVOID),
            ("SecurityQualityOfService", wintypes.LPVOID),
        )

    class _IoStatusValue(ctypes.Union):
        _fields_ = (("Status", wintypes.LONG), ("Pointer", wintypes.LPVOID))

    class _IoStatusBlock(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = (("value", _IoStatusValue), ("Information", ctypes.c_size_t))

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("FileAttributes", wintypes.DWORD),
            ("CreationTime", wintypes.FILETIME),
            ("LastAccessTime", wintypes.FILETIME),
            ("LastWriteTime", wintypes.FILETIME),
            ("VolumeSerialNumber", wintypes.DWORD),
            ("FileSizeHigh", wintypes.DWORD),
            ("FileSizeLow", wintypes.DWORD),
            ("NumberOfLinks", wintypes.DWORD),
            ("FileIndexHigh", wintypes.DWORD),
            ("FileIndexLow", wintypes.DWORD),
        )

    class _FileRenameInformation(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.ULONG),
        )

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_file = _kernel32.CreateFileW
    _create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _create_file.restype = wintypes.HANDLE
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = (wintypes.HANDLE,)
    _close_handle.restype = wintypes.BOOL
    _get_file_information = _kernel32.GetFileInformationByHandle
    _get_file_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    _get_file_information.restype = wintypes.BOOL

    _ntdll = ctypes.WinDLL("ntdll")
    _nt_create_file = _ntdll.NtCreateFile
    _nt_create_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
    )
    _nt_create_file.restype = wintypes.LONG
    _nt_set_information_file = _ntdll.NtSetInformationFile
    _nt_set_information_file.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        wintypes.ULONG,
    )
    _nt_set_information_file.restype = wintypes.LONG
    _rtl_nt_status_to_dos_error = _ntdll.RtlNtStatusToDosError
    _rtl_nt_status_to_dos_error.argtypes = (wintypes.LONG,)
    _rtl_nt_status_to_dos_error.restype = wintypes.ULONG


def _windows_error_from_status(status: int, name: str) -> OSError:
    code = int(_rtl_nt_status_to_dos_error(status))  # type: ignore[possibly-undefined]
    message = ctypes.FormatError(code)
    if code in {2, 3}:
        return FileNotFoundError(code, message, name)
    if code in {80, 183}:
        return FileExistsError(code, message, name)
    return OSError(code, message, name)


def _windows_handle_information(handle: int) -> tuple[int, int, int]:
    details = _ByHandleFileInformation()  # type: ignore[possibly-undefined]
    if not _get_file_information(  # type: ignore[possibly-undefined]
        wintypes.HANDLE(handle), ctypes.byref(details)
    ):
        code = ctypes.get_last_error()
        raise OSError(code, ctypes.FormatError(code))
    file_index = (int(details.FileIndexHigh) << 32) | int(details.FileIndexLow)
    return int(details.VolumeSerialNumber), file_index, int(details.FileAttributes)


def _windows_open_relative_handle(
    root_handle: int,
    name: str,
    *,
    desired_access: int,
    disposition: int,
    options: int,
    attributes: int = 0,
) -> int:
    """Open one safe child relative to an already-bound Windows directory handle."""

    child_name = _safe_child_name(name)
    encoded_length = len(child_name.encode("utf-16-le"))
    name_buffer = ctypes.create_unicode_buffer(child_name)
    unicode_name = _UnicodeString(  # type: ignore[possibly-undefined]
        encoded_length,
        encoded_length + ctypes.sizeof(wintypes.WCHAR),
        ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    object_attributes = _ObjectAttributes(  # type: ignore[possibly-undefined]
        ctypes.sizeof(_ObjectAttributes),  # type: ignore[possibly-undefined]
        wintypes.HANDLE(root_handle),
        ctypes.pointer(unicode_name),
        _OBJ_CASE_INSENSITIVE,  # type: ignore[possibly-undefined]
        None,
        None,
    )
    io_status = _IoStatusBlock()  # type: ignore[possibly-undefined]
    result_handle = wintypes.HANDLE()
    status = int(
        _nt_create_file(  # type: ignore[possibly-undefined]
            ctypes.byref(result_handle),
            desired_access,
            ctypes.byref(object_attributes),
            ctypes.byref(io_status),
            None,
            attributes,
            _FILE_SHARE_READ  # type: ignore[possibly-undefined]
            | _FILE_SHARE_WRITE  # type: ignore[possibly-undefined]
            | _FILE_SHARE_DELETE,  # type: ignore[possibly-undefined]
            disposition,
            options,
            None,
            0,
        )
    )
    if status < 0:
        raise _windows_error_from_status(status, child_name)
    numeric = int(result_handle.value or 0)
    if not numeric:
        raise DirectoryLeaseError("Windows returned an invalid relative child handle")
    return numeric


def _windows_handle_to_descriptor(handle: int, flags: int) -> int:
    try:
        return int(msvcrt.open_osfhandle(handle, flags))  # type: ignore[possibly-undefined]
    except BaseException:
        _close_handle(handle)  # type: ignore[possibly-undefined]
        raise


def _windows_open_relative_file_descriptor(
    root_handle: int,
    name: str,
    *,
    write_exclusive: bool,
) -> int:
    if write_exclusive:
        desired_access = (
            _FILE_WRITE_DATA | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE  # type: ignore[possibly-undefined]
        )
        disposition = _FILE_CREATE  # type: ignore[possibly-undefined]
        descriptor_flags = os.O_WRONLY | os.O_BINARY
    else:
        desired_access = (
            _FILE_READ_DATA | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE  # type: ignore[possibly-undefined]
        )
        disposition = _FILE_OPEN  # type: ignore[possibly-undefined]
        descriptor_flags = os.O_RDONLY | os.O_BINARY
    handle = _windows_open_relative_handle(
        root_handle,
        name,
        desired_access=desired_access,
        disposition=disposition,
        options=(
            _FILE_NON_DIRECTORY_FILE  # type: ignore[possibly-undefined]
            | _FILE_SYNCHRONOUS_IO_NONALERT  # type: ignore[possibly-undefined]
            | _FILE_OPEN_REPARSE_POINT  # type: ignore[possibly-undefined]
        ),
        attributes=_FILE_ATTRIBUTE_NORMAL,  # type: ignore[possibly-undefined]
    )
    try:
        return _windows_handle_to_descriptor(handle, descriptor_flags)
    except BaseException:
        if write_exclusive:
            _windows_unlink_relative(root_handle, name)
        raise


def _windows_unlink_relative(root_handle: int, name: str) -> None:
    handle = _windows_open_relative_handle(
        root_handle,
        name,
        desired_access=(
            _DELETE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE  # type: ignore[possibly-undefined]
        ),
        disposition=_FILE_OPEN,  # type: ignore[possibly-undefined]
        options=(
            _FILE_NON_DIRECTORY_FILE  # type: ignore[possibly-undefined]
            | _FILE_SYNCHRONOUS_IO_NONALERT  # type: ignore[possibly-undefined]
            | _FILE_OPEN_REPARSE_POINT  # type: ignore[possibly-undefined]
        ),
    )
    try:
        disposition = wintypes.BOOLEAN(1)
        io_status = _IoStatusBlock()  # type: ignore[possibly-undefined]
        status = int(
            _nt_set_information_file(  # type: ignore[possibly-undefined]
                wintypes.HANDLE(handle),
                ctypes.byref(io_status),
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
                _FILE_DISPOSITION_INFORMATION,  # type: ignore[possibly-undefined]
            )
        )
        if status < 0:
            raise _windows_error_from_status(status, name)
    finally:
        _close_handle(handle)  # type: ignore[possibly-undefined]


def _windows_rename_relative_no_replace(
    source_root_handle: int,
    source_name: str,
    destination_root_handle: int,
    destination_name: str,
) -> None:
    source = _safe_child_name(source_name)
    destination = _safe_child_name(destination_name)
    source_handle = _windows_open_relative_handle(
        source_root_handle,
        source,
        desired_access=(
            _DELETE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE  # type: ignore[possibly-undefined]
        ),
        disposition=_FILE_OPEN,  # type: ignore[possibly-undefined]
        options=(
            _FILE_NON_DIRECTORY_FILE  # type: ignore[possibly-undefined]
            | _FILE_SYNCHRONOUS_IO_NONALERT  # type: ignore[possibly-undefined]
            | _FILE_OPEN_REPARSE_POINT  # type: ignore[possibly-undefined]
        ),
    )
    try:
        encoded_name = destination.encode("utf-16-le")
        name_offset = (
            _FileRenameInformation.FileNameLength.offset  # type: ignore[possibly-undefined]
            + ctypes.sizeof(wintypes.ULONG)
        )
        buffer_size = max(
            ctypes.sizeof(_FileRenameInformation),  # type: ignore[possibly-undefined]
            name_offset + len(encoded_name),
        )
        rename_buffer = ctypes.create_string_buffer(buffer_size)
        rename_information = _FileRenameInformation.from_buffer(  # type: ignore[possibly-undefined]
            rename_buffer
        )
        rename_information.ReplaceIfExists = 0
        rename_information.RootDirectory = wintypes.HANDLE(destination_root_handle)
        rename_information.FileNameLength = len(encoded_name)
        ctypes.memmove(
            ctypes.addressof(rename_buffer) + name_offset,
            encoded_name,
            len(encoded_name),
        )
        io_status = _IoStatusBlock()  # type: ignore[possibly-undefined]
        status = int(
            _nt_set_information_file(  # type: ignore[possibly-undefined]
                wintypes.HANDLE(source_handle),
                ctypes.byref(io_status),
                rename_buffer,
                buffer_size,
                _FILE_RENAME_INFORMATION,  # type: ignore[possibly-undefined]
            )
        )
        if status < 0:
            raise _windows_error_from_status(status, destination)
    finally:
        _close_handle(source_handle)  # type: ignore[possibly-undefined]


def _open_windows_directory_handle(path: Path) -> int:
    if os.name != "nt":  # pragma: no cover - guarded by callers
        raise DirectoryLeaseError("Windows directory handles are unavailable")
    handle = _create_file(  # type: ignore[possibly-undefined]
        str(path),
        _FILE_LIST_DIRECTORY  # type: ignore[possibly-undefined]
        | _FILE_TRAVERSE  # type: ignore[possibly-undefined]
        | _FILE_READ_ATTRIBUTES  # type: ignore[possibly-undefined]
        | _SYNCHRONIZE,  # type: ignore[possibly-undefined]
        _FILE_SHARE_READ  # type: ignore[possibly-undefined]
        | _FILE_SHARE_WRITE  # type: ignore[possibly-undefined]
        | _FILE_SHARE_DELETE,  # type: ignore[possibly-undefined]
        None,
        _OPEN_EXISTING,  # type: ignore[possibly-undefined]
        _FILE_FLAG_BACKUP_SEMANTICS  # type: ignore[possibly-undefined]
        | _FILE_FLAG_OPEN_REPARSE_POINT,  # type: ignore[possibly-undefined]
        None,
    )
    numeric = int(handle)
    if numeric == _INVALID_HANDLE_VALUE:  # type: ignore[possibly-undefined]
        error = ctypes.get_last_error()
        raise DirectoryLeaseError(f"directory handle could not be opened safely ({error})")
    return numeric


def _open_windows_child_directory_handle(parent_handle: int, name: str, *, create: bool) -> int:
    return _windows_open_relative_handle(
        parent_handle,
        name,
        desired_access=(
            _FILE_LIST_DIRECTORY  # type: ignore[possibly-undefined]
            | _FILE_TRAVERSE  # type: ignore[possibly-undefined]
            | _FILE_READ_ATTRIBUTES  # type: ignore[possibly-undefined]
            | _SYNCHRONIZE  # type: ignore[possibly-undefined]
        ),
        disposition=(
            _FILE_OPEN_IF if create else _FILE_OPEN  # type: ignore[possibly-undefined]
        ),
        options=(
            _FILE_DIRECTORY_FILE  # type: ignore[possibly-undefined]
            | _FILE_SYNCHRONOUS_IO_NONALERT  # type: ignore[possibly-undefined]
            | _FILE_OPEN_REPARSE_POINT  # type: ignore[possibly-undefined]
        ),
        attributes=_FILE_ATTRIBUTE_DIRECTORY,  # type: ignore[possibly-undefined]
    )


@dataclass(slots=True)
class DirectoryLease(AbstractContextManager["DirectoryLease"]):
    """An identity-checked directory held stable for child operations."""

    path: Path
    resolved: Path
    identity: tuple[int, int]
    _posix_fd: int | None = None
    _windows_handle: int | None = None
    _windows_identity: tuple[int, int] | None = None
    _closed: bool = False

    @classmethod
    def acquire(cls, path: Path) -> Self:
        logical = _absolute(path)
        if _is_reparse_point(logical):
            raise DirectoryLeaseError("directory lease cannot bind a symlink or reparse point")
        try:
            before = logical.lstat()
        except OSError as error:
            raise DirectoryLeaseError("directory lease target cannot be inspected") from error
        if not stat.S_ISDIR(before.st_mode):
            raise DirectoryLeaseError("directory lease target must be an existing directory")

        posix_fd: int | None = None
        windows_handle: int | None = None
        try:
            if os.name == "nt":
                windows_handle = _open_windows_directory_handle(logical)
                volume, file_index, attributes = _windows_handle_information(windows_handle)
                opened = logical.lstat()
                if (
                    file_index != opened.st_ino
                    or not attributes & _FILE_ATTRIBUTE_DIRECTORY  # type: ignore[possibly-undefined]
                    or attributes & _FILE_ATTRIBUTE_REPARSE_POINT  # type: ignore[possibly-undefined]
                ):
                    raise DirectoryLeaseError("directory handle identity is inconsistent")
            else:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                posix_fd = os.open(logical, flags)
                opened = os.fstat(posix_fd)
            if _is_reparse_point(logical):
                raise DirectoryLeaseError("directory became a symlink or reparse point")
            after = logical.lstat()
            identities = {
                (before.st_dev, before.st_ino),
                (opened.st_dev, opened.st_ino),
                (after.st_dev, after.st_ino),
            }
            if len(identities) != 1 or not stat.S_ISDIR(opened.st_mode):
                raise DirectoryLeaseError("directory identity changed while acquiring its lease")
            resolved = logical.resolve(strict=True)
            return cls(
                path=logical,
                resolved=resolved,
                identity=(opened.st_dev, opened.st_ino),
                _posix_fd=posix_fd,
                _windows_handle=windows_handle,
                _windows_identity=(volume, file_index) if os.name == "nt" else None,
            )
        except BaseException:
            if posix_fd is not None:
                os.close(posix_fd)
            if windows_handle is not None:
                _close_handle(windows_handle)  # type: ignore[possibly-undefined]
            raise

    def __enter__(self) -> Self:
        self.require_bound()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    @property
    def posix_fd(self) -> int:
        if self._closed or self._posix_fd is None:
            raise DirectoryLeaseError("POSIX directory descriptor is unavailable")
        return self._posix_fd

    @property
    def windows_handle(self) -> int:
        if self._closed or self._windows_handle is None:
            raise DirectoryLeaseError("Windows directory handle is unavailable")
        return self._windows_handle

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._posix_fd is not None:
            os.close(self._posix_fd)
            self._posix_fd = None
        if self._windows_handle is not None:
            if not _close_handle(self._windows_handle):  # type: ignore[possibly-undefined]
                raise DirectoryLeaseError("Windows directory handle could not be closed")
            self._windows_handle = None
            self._windows_identity = None

    def require_bound(self) -> None:
        if self._closed:
            raise DirectoryLeaseError("directory lease is already closed")
        if _is_reparse_point(self.path):
            raise DirectoryLeaseError("leased directory became a symlink or reparse point")
        try:
            current = self.path.lstat()
        except OSError as error:
            raise DirectoryLeaseError("leased directory is no longer addressable") from error
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != self.identity
            or self.path.resolve(strict=True) != self.resolved
        ):
            raise DirectoryLeaseError("leased directory identity changed")
        if self._posix_fd is not None:
            opened = os.fstat(self._posix_fd)
            if (opened.st_dev, opened.st_ino) != self.identity:
                raise DirectoryLeaseError("leased directory descriptor identity changed")
        if self._windows_handle is not None:
            volume, file_index, attributes = _windows_handle_information(self._windows_handle)
            if (
                self._windows_identity != (volume, file_index)
                or file_index != self.identity[1]
                or not attributes & _FILE_ATTRIBUTE_DIRECTORY  # type: ignore[possibly-undefined]
                or attributes & _FILE_ATTRIBUTE_REPARSE_POINT  # type: ignore[possibly-undefined]
            ):
                raise DirectoryLeaseError("leased Windows directory handle identity changed")

    def child_path(self, name: str) -> Path:
        return self.path / _safe_child_name(name)

    def acquire_child(self, name: str, *, create: bool = False) -> DirectoryLease:
        child_name = _safe_child_name(name)
        self.require_bound()
        if os.name == "nt":
            try:
                handle = _open_windows_child_directory_handle(
                    self.windows_handle, child_name, create=create
                )
                volume, file_index, attributes = _windows_handle_information(handle)
                if (
                    not attributes & _FILE_ATTRIBUTE_DIRECTORY  # type: ignore[possibly-undefined]
                    or attributes & _FILE_ATTRIBUTE_REPARSE_POINT  # type: ignore[possibly-undefined]
                ):
                    raise DirectoryLeaseError("child directory handle is unsafe")
                child_path = self.child_path(child_name)
                current = child_path.lstat()
                if (
                    not stat.S_ISDIR(current.st_mode)
                    or current.st_ino != file_index
                    or _is_reparse_point(child_path)
                ):
                    raise DirectoryLeaseError("child directory identity is inconsistent")
                child = DirectoryLease(
                    path=child_path,
                    resolved=child_path.resolve(strict=True),
                    identity=(current.st_dev, current.st_ino),
                    _windows_handle=handle,
                    _windows_identity=(volume, file_index),
                )
            except BaseException:
                if "handle" in locals():
                    _close_handle(handle)  # type: ignore[possibly-undefined]
                raise
        else:
            if create:
                try:
                    os.mkdir(child_name, dir_fd=self.posix_fd)
                except FileExistsError:
                    pass
                except OSError as error:
                    raise DirectoryLeaseError(
                        "child directory could not be created safely"
                    ) from error
            child_path = self.child_path(child_name)
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(child_name, flags, dir_fd=self.posix_fd)
                opened = os.fstat(descriptor)
                current = child_path.lstat()
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
                    or _is_reparse_point(child_path)
                ):
                    raise DirectoryLeaseError("child directory identity is inconsistent")
                child = DirectoryLease(
                    path=child_path,
                    resolved=child_path.resolve(strict=True),
                    identity=(opened.st_dev, opened.st_ino),
                    _posix_fd=descriptor,
                )
            except BaseException:
                if "descriptor" in locals():
                    os.close(descriptor)
                raise
        try:
            self.require_bound()
            if not child.resolved.is_relative_to(self.resolved):
                raise DirectoryLeaseError("child directory escapes its leased parent")
            return child
        except BaseException:
            child.close()
            raise

    def open_child_exclusive(self, name: str) -> BinaryIO:
        child_name = _safe_child_name(name)
        self.require_bound()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            if os.name == "nt":
                descriptor = _windows_open_relative_file_descriptor(
                    self.windows_handle, child_name, write_exclusive=True
                )
            else:
                descriptor = os.open(child_name, flags, 0o600, dir_fd=self.posix_fd)
        except OSError as error:
            raise DirectoryLeaseError("exclusive child file could not be created safely") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise DirectoryLeaseError("new child is not an unaliased regular file")
            self.require_bound()
            return os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            try:
                if os.name == "nt":
                    _windows_unlink_relative(self.windows_handle, child_name)
                else:
                    os.unlink(child_name, dir_fd=self.posix_fd)
            except BaseException as rollback_error:
                raise DirectoryLeaseError(
                    "new child could not be rolled back after validation failure"
                ) from rollback_error
            raise

    def open_child_read(self, name: str) -> BinaryIO:
        child_name = _safe_child_name(name)
        self.require_bound()
        try:
            before = self.child_lstat(child_name)
        except DirectoryLeaseError:
            raise
        before_attributes = getattr(before, "st_file_attributes", 0)
        reparse_marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if not stat.S_ISREG(before.st_mode) or (
            reparse_marker and before_attributes & reparse_marker
        ):
            raise DirectoryLeaseError("child is not an unaliased regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            if os.name == "nt":
                descriptor = _windows_open_relative_file_descriptor(
                    self.windows_handle, child_name, write_exclusive=False
                )
            else:
                descriptor = os.open(child_name, flags, dir_fd=self.posix_fd)
        except OSError as error:
            raise DirectoryLeaseError("child file could not be opened safely") from error
        try:
            details = os.fstat(descriptor)
            after = self.child_lstat(child_name)
            if (
                not stat.S_ISREG(details.st_mode)
                or (before.st_dev, before.st_ino) != (details.st_dev, details.st_ino)
                or (details.st_dev, details.st_ino) != (after.st_dev, after.st_ino)
                or (reparse_marker and getattr(details, "st_file_attributes", 0) & reparse_marker)
            ):
                raise DirectoryLeaseError("child is not a regular file")
            self.require_bound()
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise

    def child_lstat(self, name: str) -> os.stat_result:
        child_name = _safe_child_name(name)
        self.require_bound()
        try:
            if os.name == "nt":
                descriptor = _windows_open_relative_file_descriptor(
                    self.windows_handle, child_name, write_exclusive=False
                )
                try:
                    return os.fstat(descriptor)
                finally:
                    os.close(descriptor)
            return os.stat(child_name, dir_fd=self.posix_fd, follow_symlinks=False)
        except OSError as error:
            raise DirectoryLeaseError("child file could not be inspected safely") from error

    def child_exists(self, name: str) -> bool:
        try:
            self.child_lstat(name)
        except DirectoryLeaseError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return False
            raise
        return True

    def unlink_child(self, name: str, *, missing_ok: bool = False) -> None:
        child_name = _safe_child_name(name)
        self.require_bound()
        try:
            if os.name == "nt":
                _windows_unlink_relative(self.windows_handle, child_name)
            else:
                os.unlink(child_name, dir_fd=self.posix_fd)
        except FileNotFoundError:
            if not missing_ok:
                raise
        except OSError as error:
            raise DirectoryLeaseError("child file could not be removed safely") from error

    def rename_child_no_replace(self, source_name: str, destination_name: str) -> None:
        source = _safe_child_name(source_name)
        destination = _safe_child_name(destination_name)
        self.require_bound()
        if self.child_exists(destination):
            raise FileExistsError(self.child_path(destination))
        if os.name == "nt":
            _windows_rename_relative_no_replace(
                self.windows_handle,
                source,
                self.windows_handle,
                destination,
            )
        else:
            _posix_rename_no_replace(self.posix_fd, source, self.posix_fd, destination)
        try:
            self.require_bound()
        except BaseException:
            try:
                if os.name == "nt":
                    _windows_unlink_relative(self.windows_handle, destination)
                else:
                    os.unlink(destination, dir_fd=self.posix_fd)
            except BaseException as rollback_error:
                raise DirectoryLeaseError(
                    "renamed child could not be rolled back after parent identity loss"
                ) from rollback_error
            raise


def rename_between_directories_no_replace(
    source_directory: DirectoryLease,
    source_name: str,
    destination_directory: DirectoryLease,
    destination_name: str,
) -> None:
    """Atomically move one child between leased directories without replacement."""

    source = _safe_child_name(source_name)
    destination = _safe_child_name(destination_name)
    source_directory.require_bound()
    destination_directory.require_bound()
    if destination_directory.child_exists(destination):
        raise FileExistsError(destination_directory.child_path(destination))
    if os.name == "nt":
        _windows_rename_relative_no_replace(
            source_directory.windows_handle,
            source,
            destination_directory.windows_handle,
            destination,
        )
    else:
        _posix_rename_no_replace(
            source_directory.posix_fd,
            source,
            destination_directory.posix_fd,
            destination,
        )
    try:
        source_directory.require_bound()
        destination_directory.require_bound()
    except BaseException:
        try:
            if os.name == "nt":
                _windows_unlink_relative(destination_directory.windows_handle, destination)
            else:
                os.unlink(destination, dir_fd=destination_directory.posix_fd)
        except BaseException as rollback_error:
            raise DirectoryLeaseError(
                "published child could not be rolled back after parent identity loss"
            ) from rollback_error
        raise


def _posix_rename_no_replace(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
) -> None:
    """Use renameat2 where available; otherwise use a recoverable link/unlink pair."""

    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is not None:
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(
            source_fd,
            os.fsencode(source_name),
            destination_fd,
            os.fsencode(destination_name),
            1,  # RENAME_NOREPLACE
        )
        if result == 0:
            return
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(destination_name)
        if code not in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
            raise OSError(code, os.strerror(code), destination_name)

    os.link(
        source_name,
        destination_name,
        src_dir_fd=source_fd,
        dst_dir_fd=destination_fd,
        follow_symlinks=False,
    )
    os.unlink(source_name, dir_fd=source_fd)
