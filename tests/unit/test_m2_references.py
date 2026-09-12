"""Breaks caught: reference corruption, coordinate drift, and unreviewed source bytes."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from peru_conflicts.execution import references


def test_unicode_position_is_human_selected_not_byte_offset() -> None:
    assert references.select_position("áx\n🙂z\n".encode(), line=2, column=2) == 4


def test_only_lf_separates_displayed_and_selected_lines() -> None:
    data = "first\u2028second\u0085third\nlast\n".encode()
    assert references.select_position(data, line=2, column=1) == len(
        "first\u2028second\u0085third\n"
    )
    assert references.select_position(data, line=3, column=1) == len(data.decode())


@pytest.mark.parametrize("line,column", [(0, 1), (1, 0), (3, 1), (1, 9)])
def test_position_rejects_nonexistent_location(line: int, column: int) -> None:
    with pytest.raises(ValueError):
        references.select_position(b"one\ntwo", line=line, column=column)


def test_snapshot_detects_corruption_missing_and_duplicate_pages(tmp_path: Path) -> None:
    pages = {1: b"one\n", 2: b"two\n"}
    manifest = references.build_manifest(260, "a" * 64, pages, "b" * 64)
    references.verify_pages(manifest, pages)
    for invalid in ({1: b"one\n"}, {1: b"changed", 2: b"two\n"}):
        with pytest.raises(ValueError):
            references.verify_pages(manifest, invalid)
    payload = manifest.model_dump(mode="json")
    payload["pages"][1] = payload["pages"][0]
    with pytest.raises(ValueError):
        references.ReferenceSnapshotManifest.model_validate_json(__import__("json").dumps(payload))
    assert manifest.pages[0].reference_sha256 == hashlib.sha256(b"one\n").hexdigest()


@pytest.mark.parametrize("value", [b"x\r\n", b"x\f", b"\xef\xbb\xbfx", b"\xff"])
def test_reference_never_silently_normalizes(value: bytes) -> None:
    with pytest.raises(ValueError):
        references.build_manifest(260, "a" * 64, {1: value}, "b" * 64)


def test_custody_rejects_wrong_source_before_extractor(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"synthetic pdf")
    with (
        pytest.raises(ValueError, match="source hash"),
        references.verified_source_snapshot(tmp_path, "source.pdf", "0" * 64),
    ):
        pytest.fail("mismatched source reached extraction")


def test_owned_source_snapshot_is_removed(tmp_path: Path) -> None:
    data = b"synthetic pdf"
    (tmp_path / "source.pdf").write_bytes(data)
    with references.verified_source_snapshot(
        tmp_path, "source.pdf", hashlib.sha256(data).hexdigest()
    ) as snapshot:
        assert snapshot.read_bytes() == data
        assert snapshot.parent != tmp_path
    assert not snapshot.exists()


def test_temporary_snapshot_mutation_is_denied_or_rejected(tmp_path: Path) -> None:
    data = b"synthetic pdf"
    (tmp_path / "source.pdf").write_bytes(data)
    if os.name == "nt":
        with (
            references.verified_source_snapshot(
                tmp_path, "source.pdf", hashlib.sha256(data).hexdigest()
            ) as snapshot,
            pytest.raises(OSError),
        ):
            snapshot.write_bytes(b"changed input")
    else:
        with (
            pytest.raises(ValueError, match="snapshot"),
            references.verified_source_snapshot(
                tmp_path, "source.pdf", hashlib.sha256(data).hexdigest()
            ) as snapshot,
        ):
            snapshot.write_bytes(b"changed input")


def test_pinned_extractor_checks_pages_and_uses_single_page_native_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "engine.exe"
    binary.write_bytes(b"fake engine")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if "-v" in args:
            return subprocess.CompletedProcess(args, 0, b"", b"engine 1\n")
        if len(args) == 2:
            return subprocess.CompletedProcess(args, 0, b"Pages: 2\n", b"")
        page = args[args.index("-f") + 1]
        return subprocess.CompletedProcess(args, 0, f"page {page}\n".encode(), b"")

    monkeypatch.setattr(references.subprocess, "run", fake_run)
    pin = references.ExecutableIdentity(
        path=str(binary), sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), version="engine 1"
    )
    policy = references.ReferenceExtractionPolicy(pdftotext=pin, pdfinfo=pin, mode="raw")
    pages = references.extract_pages(tmp_path / "snapshot.pdf", 2, policy)
    assert pages == {1: b"page 1\n", 2: b"page 2\n"}
    assert [call for call in calls if "-f" in call][-1][1:-2] == [
        "-f",
        "2",
        "-l",
        "2",
        "-raw",
        "-enc",
        "UTF-8",
        "-eol",
        "unix",
        "-nopgbrk",
    ]
    with pytest.raises(ValueError, match="page count"):
        references.extract_pages(tmp_path / "snapshot.pdf", 3, policy)
    binary.write_bytes(b"replaced")
    with pytest.raises(ValueError, match="binary"):
        references.extract_pages(tmp_path / "snapshot.pdf", 2, policy)
