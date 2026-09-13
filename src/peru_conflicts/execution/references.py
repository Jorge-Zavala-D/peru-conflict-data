"""Native reference custody for non-launched readiness previews."""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import subprocess
import tempfile
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import Field, model_validator

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExecutableIdentity(StrictModel):
    path: str = Field(min_length=1)
    sha256: Sha256
    version: str = Field(min_length=1)


class ReferenceExtractionPolicy(StrictModel):
    policy_id: Literal["m2-02-reference-policy-v1"] = "m2-02-reference-policy-v1"
    owner_approved: Literal[False] = False
    pdftotext: ExecutableIdentity
    pdfinfo: ExecutableIdentity
    mode: Literal["raw", "layout"]
    encoding: Literal["UTF-8"] = "UTF-8"
    eol: Literal["unix"] = "unix"
    unicode_normalization: Literal["none"] = "none"
    ocr: Literal[False] = False

    @property
    def fingerprint(self) -> str:
        return sha256(canonical_json_bytes(self.model_dump(mode="json")))


def _run(args: list[str]) -> bytes:
    result = subprocess.run(args, capture_output=True, check=True, timeout=120)
    return result.stdout


def verify_executable(pin: ExecutableIdentity) -> None:
    binary = Path(pin.path)
    if not binary.is_absolute() or sha256(binary.read_bytes()) != pin.sha256:
        raise ValueError("extractor binary identity mismatch")
    version = subprocess.run([str(binary), "-v"], capture_output=True, check=True, timeout=20)
    if pin.version not in (version.stdout + version.stderr).decode("utf-8", errors="strict"):
        raise ValueError("extractor version mismatch")


def extract_pages(
    snapshot: Path, expected_pages: int, policy: ReferenceExtractionPolicy
) -> dict[int, bytes]:
    """Native-only, single-page extraction from an owned snapshot; no semantic inference."""
    verify_executable(policy.pdftotext)
    verify_executable(policy.pdfinfo)
    info = _run([policy.pdfinfo.path, str(snapshot)]).decode("utf-8", errors="strict")
    match = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
    if match is None or int(match[1]) != expected_pages:
        raise ValueError("protected PDF page count mismatch")
    pages: dict[int, bytes] = {}
    for page in range(1, expected_pages + 1):
        data = _run(
            [
                policy.pdftotext.path,
                "-f",
                str(page),
                "-l",
                str(page),
                f"-{policy.mode}",
                "-enc",
                "UTF-8",
                "-eol",
                "unix",
                "-nopgbrk",
                str(snapshot),
                "-",
            ]
        )
        reference_text(data)
        pages[page] = data
    verify_executable(policy.pdftotext)
    return pages


def reference_text(data: bytes) -> str:
    text = data.decode("utf-8", errors="strict")
    if "\r" in text or "\f" in text or text.startswith("\ufeff"):
        raise ValueError("reference must be UTF-8 LF without BOM or form feed")
    return text


def select_position(data: bytes, *, line: int, column: int) -> int:
    """Convert a human's one-based line/column to a code-point boundary, not a guess."""
    text = reference_text(data)
    lines = text.split("\n") if text else []
    if line < 1 or line > len(lines) or column < 1:
        raise ValueError("select an existing one-based line and column")
    selected = lines[line - 1]
    if column > len(selected) + 1:
        raise ValueError("column is outside selected line")
    return sum(len(value) + 1 for value in lines[: line - 1]) + column - 1


class ReferencePage(StrictModel):
    page: int = Field(ge=1)
    reference_sha256: Sha256
    byte_count: int = Field(ge=0)
    codepoint_count: int = Field(ge=0)


class ReferenceSnapshotManifest(StrictModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    reference_policy_id: Literal["m2-02-reference-policy-v1"] = "m2-02-reference-policy-v1"
    report_number: int = Field(ge=1)
    source_sha256: Sha256
    page_count: int = Field(ge=1)
    coordinate_policy: Literal["page-native-utf8-lf-codepoint-v1"] = (
        "page-native-utf8-lf-codepoint-v1"
    )
    extraction_policy_sha256: Sha256
    pages: tuple[ReferencePage, ...]

    @model_validator(mode="after")
    def closed_pages(self) -> Self:
        if tuple(p.page for p in self.pages) != tuple(range(1, self.page_count + 1)):
            raise ValueError("reference pages must be complete, sorted and unique")
        return self

    @property
    def snapshot_sha256(self) -> str:
        return sha256(canonical_json_bytes(self.model_dump(mode="json")) + b"\n")


def build_manifest(
    report: int, source_sha: str, pages: Mapping[int, bytes], policy_sha: str
) -> ReferenceSnapshotManifest:
    return ReferenceSnapshotManifest(
        report_number=report,
        source_sha256=source_sha,
        page_count=len(pages),
        extraction_policy_sha256=policy_sha,
        pages=tuple(
            ReferencePage(
                page=number,
                reference_sha256=sha256(data),
                byte_count=len(data),
                codepoint_count=len(reference_text(data)),
            )
            for number, data in sorted(pages.items())
        ),
    )


def verify_pages(manifest: ReferenceSnapshotManifest, pages: Mapping[int, bytes]) -> None:
    rebuilt = build_manifest(
        manifest.report_number,
        manifest.source_sha256,
        pages,
        manifest.extraction_policy_sha256,
    )
    if rebuilt != manifest:
        raise ValueError("reference snapshot bytes or page inventory changed")


@contextmanager
def _windows_read_guard(path: Path) -> Generator[None]:
    """Deny write/delete sharing while the native child process reads its snapshot."""
    if os.name != "nt":
        yield
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(path), 0x80000000, 0x1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "snapshot read-only custody failed")
    try:
        yield
    finally:
        if not close(handle):
            raise OSError(ctypes.get_last_error(), "snapshot custody close failed")


@contextmanager
def verified_source_snapshot(root: Path, relative_path: str, expected_sha: str) -> Generator[Path]:
    """Copy from retained read custody to an owned ephemeral extraction input; never write root."""
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(p in {".", ".."} for p in relative.parts):
        raise ValueError("source path must be relative and confined")
    if "\\" in relative_path or ":" in relative_path or not relative.parts:
        raise ValueError("source path must use relative POSIX components")
    with ExitStack() as stack:
        parent = stack.enter_context(DirectoryLease.acquire(root))
        for part in relative.parts[:-1]:
            parent = stack.enter_context(parent.acquire_child(part))
        stream = stack.enter_context(parent.open_child_read(relative.name))
        data = stream.read()
        if sha256(data) != expected_sha:
            raise ValueError("protected source hash mismatch")
        with tempfile.TemporaryDirectory(prefix="m2-readiness-source-") as temporary:
            snapshot = Path(temporary) / "source.pdf"
            with snapshot.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            with (
                DirectoryLease.acquire(Path(temporary)) as owned,
                _windows_read_guard(snapshot),
                owned.open_child_read("source.pdf") as retained,
            ):
                before = os.fstat(retained.fileno())
                directory_before = Path(temporary).stat()
                if sha256(retained.read()) != expected_sha:
                    raise ValueError("owned source snapshot hash mismatch")
                try:
                    yield snapshot
                finally:
                    retained.seek(0)
                    after = os.fstat(retained.fileno())
                    bound = owned.child_lstat("source.pdf")
                    if (
                        sha256(retained.read()) != expected_sha
                        or (before.st_dev, before.st_ino) != (bound.st_dev, bound.st_ino)
                        or (before.st_mtime_ns, before.st_ctime_ns)
                        != (after.st_mtime_ns, after.st_ctime_ns)
                        or directory_before.st_mtime_ns != Path(temporary).stat().st_mtime_ns
                    ):
                        raise ValueError("owned snapshot changed during extraction")
                    owned.require_bound()
                    stream.seek(0)
                    if sha256(stream.read()) != expected_sha:
                        raise ValueError("protected source changed during extraction")
                    parent.require_bound()
