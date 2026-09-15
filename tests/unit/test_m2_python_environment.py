"""Environment bytes are rehearsal evidence, never production trust authority."""

import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest

from peru_conflicts.execution.launch import LaunchIdentity
from peru_conflicts.execution.runtime_build import RuntimeManifest


def environment_module() -> Any:
    name = "peru_conflicts.execution.python_environment"
    assert importlib.util.find_spec(name) is not None, "Python environment binding is absent"
    return importlib.import_module(name)


def test_launch_and_runtime_require_separate_environment_pins() -> None:
    for model in (LaunchIdentity, RuntimeManifest):
        assert "python_environment_sha256" in model.model_fields
        assert "python_environment_manifest_sha256" in model.model_fields


def test_windows_exclusions_ignore_case_preserving_inventory_spelling(tmp_path: Path) -> None:
    module = environment_module()
    stdlib, executable = installation(tmp_path, "Windows")
    for original, replacement in (
        ("site-packages", "Site-Packages"),
        ("__pycache__", "__PYCACHE__"),
    ):
        (stdlib / original).rename(stdlib / "rename-temporary")
        (stdlib / "rename-temporary").rename(stdlib / replacement)
    for relative in ("Site-Packages/third_party.py", "__PYCACHE__/module.PYC"):
        path = stdlib / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"excluded bytes")
    (stdlib / "Kept.py").write_bytes(b"preserved spelling")
    manifest = module.capture_rehearsal_environment(
        "a" * 64, root=tmp_path, stdlib=stdlib, executable=executable, system="Windows"
    )
    assert "Lib/Kept.py" in manifest.file_hashes
    assert not any(
        "site-packages" in name.casefold() or "__pycache__" in name.casefold()
        for name in manifest.file_hashes
    )


def installation(root: Path, system: str) -> tuple[Path, Path]:
    stdlib = root / ("Lib" if system == "Windows" else "lib/python3.12")
    executable = root / ("python.exe" if system == "Windows" else "bin/python3.12")
    for relative, data in {
        stdlib.relative_to(root) / "os.py": b"original stdlib",
        stdlib.relative_to(root) / "encodings/__init__.py": b"encoding runtime",
        stdlib.relative_to(root) / "site-packages/user.py": b"excluded dependency",
        stdlib.relative_to(root) / "__pycache__/os.pyc": b"excluded cache",
        executable.relative_to(root): b"same interpreter",
        Path("python312.zip" if system == "Windows" else "lib/python312.zip"): b"zip",
        Path(
            "DLLs/_ssl.pyd" if system == "Windows" else "lib/python3.12/lib-dynload/_ssl.so"
        ): b"native",
        Path("python312.dll" if system == "Windows" else "lib/libpython3.12.so.1.0"): b"shared",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return stdlib, executable


@pytest.mark.parametrize(
    "location,name",
    [
        ("root", "python._pth"),
        ("root", "python313._pth"),
        ("root", "PYTHON313._PTH"),
        ("executable", "python._pth"),
        ("executable", "python313._pth"),
        ("root", "pyvenv.cfg"),
        ("parent", "pyvenv.cfg"),
        ("executable", "pyvenv.cfg"),
        ("executable_parent", "PyVenv.CFG"),
    ],
)
def test_windows_startup_configuration_addition_and_alteration_fail_closed(
    tmp_path: Path, location: str, name: str
) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, original_executable = installation(root, "Windows")
    executable = root / "dedicated/Scripts/python.exe"
    executable.parent.mkdir(parents=True)
    original_executable.rename(executable)
    arguments = dict(root=root, stdlib=stdlib, executable=executable, system="Windows")
    module.capture_rehearsal_environment("a" * 64, **arguments)
    directory = {
        "root": root,
        "parent": root.parent,
        "executable": executable.parent,
        "executable_parent": executable.parent.parent,
    }[location]
    configuration = directory / name
    for content in (b"external-import-path\n", b"changed-import-path\nimport site\n"):
        configuration.write_bytes(content)
        with pytest.raises(ValueError, match="unsupported Windows startup configuration"):
            module.capture_rehearsal_environment("a" * 64, **arguments)


def test_windows_startup_configuration_directory_also_fails_closed(tmp_path: Path) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Windows")
    (root / "python313._pth").mkdir()
    with pytest.raises(ValueError, match="unsupported Windows startup configuration"):
        module.capture_rehearsal_environment(
            "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Windows"
        )


@pytest.mark.parametrize(
    "path",
    [
        "python._pth",
        "PYTHON313._PTH",
        "dedicated/Scripts/python._pth",
        "DEDICATED/SCRIPTS/PYTHON313._PTH",
        "pyvenv.cfg",
        "dedicated/Scripts/pyvenv.cfg",
        "dedicated/PyVenv.CFG",
        "DEDICATED/PYVENV.CFG",
    ],
)
def test_windows_manifest_cannot_claim_unsupported_startup_configuration(
    tmp_path: Path, path: str
) -> None:
    from peru_conflicts.execution.python_environment_policy import digest, json_bytes

    module = environment_module()
    root = tmp_path / "installation"
    stdlib, original_executable = installation(root, "Windows")
    executable = root / "dedicated/Scripts/python.exe"
    executable.parent.mkdir(parents=True)
    original_executable.rename(executable)
    manifest = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Windows"
    )
    payload = manifest.model_dump(mode="json")
    payload["file_hashes"][path] = "b" * 64
    payload.pop("python_environment_sha256")
    payload["python_environment_sha256"] = digest(json_bytes(payload))
    with pytest.raises(ValueError, match="unsupported Windows startup configuration"):
        module.PythonEnvironmentTrustManifest.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_stdlib_change_changes_environment_without_interpreter_or_dependency_change(
    tmp_path: Path, system: str
) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, system)
    left = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system=system
    )
    (stdlib / "os.py").write_bytes(b"substituted stdlib")
    right = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system=system
    )
    assert left.interpreter_sha256 == right.interpreter_sha256
    assert left.dependency_sha256 == right.dependency_sha256
    assert left.python_environment_sha256 != right.python_environment_sha256
    assert not any("site-packages" in p or "__pycache__" in p for p in left.file_hashes)
    assert not any(str(tmp_path) in p for p in left.file_hashes)
    assert any(p.endswith(".zip") for p in left.file_hashes)
    assert any(p.endswith((".pyd", ".so")) for p in left.file_hashes)


@pytest.mark.parametrize("change", ["aggregate", "inventory", "identity", "production"])
def test_environment_manifest_rejects_changed_claims(tmp_path: Path, change: str) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Windows")
    manifest = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Windows"
    )
    payload = manifest.model_dump(mode="json")
    if change == "aggregate":
        payload["python_environment_sha256"] = "0" * 64
    elif change == "inventory":
        payload["file_hashes"]["Lib/os.py"] = "0" * 64
    elif change == "identity":
        payload["identity"]["version"] = "different build"
    else:
        payload["production_approved"] = True
    with pytest.raises(ValueError):
        module.PythonEnvironmentTrustManifest.model_validate_json(json.dumps(payload))


def test_runtime_manifest_rejects_environment_aggregate_substitution(tmp_path: Path) -> None:
    from peru_conflicts.execution.runtime_build import build_runtime

    runtime = build_runtime(tmp_path / "runtime")
    payload = runtime.model_dump(mode="json")
    payload["python_environment_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        RuntimeManifest.model_validate_json(json.dumps(payload))


def test_linux_multiarch_runtime_is_in_inventory(tmp_path: Path) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Linux")
    shared = root / "lib/x86_64-linux-gnu/libpython3.12.so.1.0"
    shared.parent.mkdir()
    shared.write_bytes(b"multiarch Python runtime")
    manifest = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
    )
    assert "lib/x86_64-linux-gnu/libpython3.12.so.1.0" in manifest.file_hashes


def test_linux_distribution_native_companions_and_tcl_runtime_are_bound(tmp_path: Path) -> None:
    module = environment_module()
    root = tmp_path / "dedicated-cpython"
    stdlib, executable = installation(root, "Linux")
    for name in ("lib/libcompanion.so.1", "lib/tcl8.6/init.tcl", "lib/tk8.6/tk.tcl"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"bundled runtime bytes")
    before = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
    )
    assert "lib/libcompanion.so.1" in before.file_hashes
    assert "lib/tcl8.6/init.tcl" in before.file_hashes
    assert "lib/tk8.6/tk.tcl" in before.file_hashes
    (root / "lib/libcompanion.so.1").write_bytes(b"different bundled library")
    after = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
    )
    assert before.python_environment_sha256 != after.python_environment_sha256


def test_shared_linux_prefix_fails_before_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Linux")
    actual_resolve = Path.resolve

    def resolve(path: Path, strict: bool = False) -> Path:
        # Simulate the system prefix lookup on Windows without reading /usr.
        return Path("/usr") if path == root else actual_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="shared Linux prefix"):
        module.capture_rehearsal_environment(
            "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
        )


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_environment_relocation_and_excluded_package_changes_preserve_identity(
    tmp_path: Path, system: str
) -> None:
    module = environment_module()
    captures: list[Any] = []
    for index in range(2):
        root = tmp_path / str(index)
        stdlib, executable = installation(root, system)
        (stdlib / "site-packages/user.py").write_bytes(str(index).encode())
        (stdlib / "__pycache__/os.pyc").write_bytes(str(index).encode())
        captures.append(
            module.capture_rehearsal_environment(
                "a" * 64, root=root, stdlib=stdlib, executable=executable, system=system
            )
        )
    assert captures[0] == captures[1]


def test_shared_library_link_resolution_binds_target_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Linux")
    link = root / "lib/libpython3.12.so"
    if os.name == "nt":
        # This account lacks file-symlink privileges. Supply only leaf link
        # resolution; the production traversal and target byte reads stay real.
        # Linux exercises an actual POSIX link below. No native Windows symlink
        # coverage is claimed by this portable resolver fixture.
        link.write_bytes(b"resolver fixture")
        actual_is_symlink = Path.is_symlink
        actual_resolve = Path.resolve

        def is_symlink(path: Path) -> bool:
            return path == link or actual_is_symlink(path)

        def resolve(path: Path, strict: bool = False) -> Path:
            if path == link:
                return actual_resolve(link.parent / "libpython3.12.so.1.0", strict=strict)
            return actual_resolve(path, strict=strict)

        monkeypatch.setattr(Path, "is_symlink", is_symlink)
        monkeypatch.setattr(Path, "resolve", resolve)
    else:
        link.symlink_to("libpython3.12.so.1.0")
    before = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
    )
    assert before.symlinks == {"lib/libpython3.12.so": "lib/libpython3.12.so.1.0"}
    (root / "lib/libpython3.12.so.1.0").write_bytes(b"substituted shared library")
    after = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Linux"
    )
    assert before.python_environment_sha256 != after.python_environment_sha256


@pytest.mark.parametrize("path", [".", "../outside.py", "/root.py", "Lib//os.py", "Lib/../os.py"])
def test_environment_manifest_rejects_unsafe_inventory_paths(tmp_path: Path, path: str) -> None:
    module = environment_module()
    root = tmp_path / "installation"
    stdlib, executable = installation(root, "Windows")
    manifest = module.capture_rehearsal_environment(
        "a" * 64, root=root, stdlib=stdlib, executable=executable, system="Windows"
    )
    payload = manifest.model_dump(mode="json")
    payload["file_hashes"][path] = "b" * 64
    from peru_conflicts.execution.python_environment_policy import digest, json_bytes

    payload.pop("python_environment_sha256")
    payload["python_environment_sha256"] = digest(json_bytes(payload))
    with pytest.raises(ValueError):
        module.PythonEnvironmentTrustManifest.model_validate_json(json.dumps(payload))
