"""Native temporary-boundary regressions; no external provider or authority."""

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _command(temp: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "peru_conflicts.execution.setup_synthetic"],
        env=dict(os.environ, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp)),
        capture_output=True,
        text=True,
        check=False,
    )


def test_standalone_accepts_real_short_name_temp_boundary(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("requires native Windows short-name capability")
    from ctypes import wintypes

    boundary = tmp_path / "m2-readiness-long-temporary-boundary"
    boundary.mkdir()
    get_short = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
    get_short.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    get_short.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_short(str(boundary), buffer, len(buffer))
    if not length:
        raise ctypes.WinError(ctypes.get_last_error())
    short = Path(buffer.value)
    if short == boundary:
        pytest.skip("8.3 names unavailable for this synthetic directory")
    assert short.samefile(boundary)
    assert short.resolve(strict=True) == boundary.resolve(strict=True)
    assert not short.is_junction() and not short.is_symlink()
    result = _command(short)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["success"]["complete"] is True
    assert output["success"]["checks"] == {"PASS": 108}
    assert output["success"]["remaining_probes"] == 0
    assert "no registered real grant" in output["production_rejection"]
    assert list(boundary.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows junctions")
def test_standalone_rejects_junction_in_original_temp_ancestry(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "temp").mkdir()
    redirect = tmp_path / "redirect"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(redirect), str(outside)],
        check=True,
        capture_output=True,
    )
    try:
        assert redirect.is_junction()
        result = _command(redirect / "temp")
        assert result.returncode != 0
        assert "DirectoryLeaseError" in result.stderr
        assert list((outside / "temp").iterdir()) == []
    finally:
        redirect.rmdir()  # Only the test-created junction, never its target tree.
