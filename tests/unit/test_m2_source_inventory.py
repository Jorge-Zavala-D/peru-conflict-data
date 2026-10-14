"""Protect exact inventory names and every-call byte validation with cheaper keys."""

import cProfile
import hashlib
import os
from pathlib import Path
from types import CodeType

import pytest

from peru_conflicts.execution.setup_deployment import source_inventory


def synthetic_tree(root: Path) -> dict[str, str]:
    files = {
        "src/deep/a.py": b"old",
        "src/\u00e1rea/\u00f1.PY": "synthetic \u00c5<&>".encode(),
        "scripts/entry.py": b"entry",
        "uv.lock": b"lock",
        "pyproject.toml": b"project",
    }
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in files.items()
        if os.name == "nt" or not name.endswith(".PY")
    }


@pytest.mark.parametrize("relative", [False, True])
def test_source_inventory_preserves_exact_nested_unicode_and_case_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: bool
) -> None:
    root = tmp_path / "space \u00e1" / "nested"
    expected = synthetic_tree(root)
    if relative:
        monkeypatch.chdir(tmp_path)
        root = Path("space \u00e1/nested")
    actual = source_inventory(root)
    assert actual == expected
    assert all(type(k) is str and type(v) is str for k, v in actual.items())


def test_source_inventory_same_size_replacement_and_mtime_are_reread(tmp_path: Path) -> None:
    expected = synthetic_tree(tmp_path)
    assert source_inventory(tmp_path) == expected
    source = tmp_path / "src/deep/a.py"
    before = source.stat()
    replacement = source.with_suffix(".replacement")
    replacement.write_bytes(b"new")
    os.replace(replacement, source)
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    expected["src/deep/a.py"] = hashlib.sha256(b"new").hexdigest()
    assert source_inventory(tmp_path) == expected
    inode = source.stat().st_ino
    source.write_bytes(b"now")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert source.stat().st_ino == inode
    expected["src/deep/a.py"] = hashlib.sha256(b"now").hexdigest()
    assert source_inventory(tmp_path) == expected


def test_source_inventory_addition_and_deletion_are_fresh(tmp_path: Path) -> None:
    expected = synthetic_tree(tmp_path)
    assert source_inventory(tmp_path) == expected
    extra = tmp_path / "scripts/add.py"
    extra.write_bytes(b"extra")
    expected["scripts/add.py"] = hashlib.sha256(b"extra").hexdigest()
    assert source_inventory(tmp_path) == expected
    extra.unlink()
    del expected["scripts/add.py"]
    assert source_inventory(tmp_path) == expected
    original = tmp_path / "scripts/entry.py"
    original.rename(tmp_path / "scripts/renamed.py")
    expected["scripts/renamed.py"] = expected.pop("scripts/entry.py")
    assert source_inventory(tmp_path) == expected


def test_source_inventory_independent_roots_do_not_share_byte_results(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    expected_first, expected_second = synthetic_tree(first), synthetic_tree(second)
    (second / "src/deep/a.py").write_bytes(b"NEW")
    expected_second["src/deep/a.py"] = hashlib.sha256(b"NEW").hexdigest()
    assert source_inventory(first) == expected_first
    assert source_inventory(second) == expected_second
    assert source_inventory(first) == expected_first


def test_source_inventory_missing_pin_and_matching_directory_still_fail(tmp_path: Path) -> None:
    synthetic_tree(tmp_path)
    pin = tmp_path / "uv.lock"
    pin.unlink()
    with pytest.raises(OSError):
        source_inventory(tmp_path)
    pin.write_bytes(b"lock")
    (tmp_path / "src/not_a_file.py").mkdir()
    with pytest.raises(OSError):
        source_inventory(tmp_path)


def test_source_inventory_avoids_redundant_relative_path_reconstruction(tmp_path: Path) -> None:
    """The known costly lexical reconstruction must not return to each file check."""
    expected = synthetic_tree(tmp_path)
    profile = cProfile.Profile()
    profile.enable()
    actual = source_inventory(tmp_path)
    profile.disable()
    assert actual == expected
    calls = sum(
        entry.callcount
        for entry in profile.getstats()
        if isinstance(entry.code, CodeType) and entry.code.co_name == "relative_to"
    )
    assert calls == 0, f"{calls} redundant relative-path reconstructions in one fresh inventory"
