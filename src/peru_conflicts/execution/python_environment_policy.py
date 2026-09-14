"""Stdlib-only rehearsal inventory and consistency policy, not a trust bootstrap.

An independent verifier must authenticate/protect the installation before Python
starts and throughout execution. Hashing here cannot authenticate modules already
loaded, the OS loader, or later reads. Never scans third-party or user packages.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import struct
import sys
import sysconfig
from pathlib import Path, PurePosixPath
from typing import Any, cast

POLICY = "m2-python-environment-rehearsal-v1"
BOUNDARY = "external-os-loader-kernel-system-libraries-and-hardware-require-independent-trust"
EXCLUSIONS = ("__pycache__", "site-packages", "dist-packages", ".pyc", ".pyo")


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value in {".", ".."}
        or path.is_absolute()
        or str(path) != value
        or any(p in {".", ".."} for p in path.parts)
        or "\\" in value
        or ":" in value
    ):
        raise ValueError("unsafe Python environment relative path")


def excluded(path: str, system: str) -> bool:
    if system == "Windows":
        path = path.casefold()
    return bool(set(PurePosixPath(path).parts) & set(EXCLUSIONS[:3])) or path.endswith(
        EXCLUSIONS[3:]
    )


def validate_document(value: dict[str, Any]) -> None:
    """Single normative validator shared with the separately pinned launcher."""
    if set(value) != {
        "policy",
        "production_approved",
        "external_trust_boundary",
        "exclusions",
        "identity",
        "stdlib_path",
        "interpreter_path",
        "interpreter_sha256",
        "dependency_sha256",
        "file_hashes",
        "symlinks",
        "python_environment_sha256",
    }:
        raise ValueError("Python environment manifest fields differ")
    if (
        value["policy"] != POLICY
        or value["production_approved"] is not False
        or value["external_trust_boundary"] != BOUNDARY
        or value["exclusions"] != list(EXCLUSIONS)
    ):
        raise ValueError("Python environment is rehearsal-only with an explicit trust boundary")
    identity = value["identity"]
    if not isinstance(identity, dict):
        raise ValueError("Python environment implementation identity is missing")
    identity = cast(dict[str, Any], identity)
    if set(identity) != {
        "implementation",
        "version",
        "build",
        "compiler",
        "system",
        "machine",
        "pointer_bits",
        "abi",
    } or any(not isinstance(v, str) or not v for v in identity.values()):
        raise ValueError("Python environment implementation identity is incomplete")
    if identity["implementation"] != "CPython" or identity["system"] not in {"Windows", "Linux"}:
        raise ValueError("unsupported Python environment implementation/platform")
    hashes, links = value["file_hashes"], value["symlinks"]
    if not isinstance(hashes, dict) or not hashes or not isinstance(links, dict):
        raise ValueError("Python environment inventory missing")
    hashes = cast(dict[str, Any], hashes)
    links = cast(dict[str, Any], links)
    for name, pin in hashes.items():
        safe_relative(name)
        if (
            excluded(name, identity["system"])
            or not isinstance(pin, str)
            or not re.fullmatch("[a-f0-9]{64}", pin)
        ):
            raise ValueError("Python environment inventory contains excluded bytes or invalid pin")
    for name, target in links.items():
        safe_relative(name)
        safe_relative(target)
        if (
            name == target
            or name not in hashes
            or target not in hashes
            or hashes[name] != hashes[target]
        ):
            raise ValueError("Python environment symlink identity differs")
    for name in ("stdlib_path", "interpreter_path"):
        safe_relative(value[name])
    if identity["system"] == "Windows":
        startup_directories = {
            PurePosixPath("."),
            PurePosixPath(value["interpreter_path"].casefold()).parent,
        }
        configuration_directories = startup_directories | {p.parent for p in startup_directories}
        for name in hashes:
            path = PurePosixPath(name.casefold())
            if (
                path.parent in configuration_directories and path.name.casefold() == "pyvenv.cfg"
            ) or (path.parent in startup_directories and path.name.casefold().endswith("._pth")):
                raise ValueError("unsupported Windows startup configuration")
    if not any(name.startswith(value["stdlib_path"] + "/") for name in hashes):
        raise ValueError("Python environment standard library is missing")
    if hashes.get(value["interpreter_path"]) != value["interpreter_sha256"]:
        raise ValueError("Python environment interpreter identity differs")
    for key in ("interpreter_sha256", "dependency_sha256", "python_environment_sha256"):
        if not isinstance(value[key], str) or not re.fullmatch("[a-f0-9]{64}", value[key]):
            raise ValueError("Python environment prerequisite pin is invalid")
    expected = digest(
        json_bytes({k: v for k, v in value.items() if k != "python_environment_sha256"})
    )
    if expected != value["python_environment_sha256"]:
        raise ValueError("Python environment aggregate differs")


def capture_document(
    dependency_sha256: str,
    *,
    root: Path | None = None,
    stdlib: Path | None = None,
    executable: Path | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """Measure a rehearsal installation. Explicit paths are for invented fixtures.

    Windows: complete Lib, DLLs, Tcl runtime, root DLLs/executables/Python zips.
    Startup ._pth overrides and adjacent/parent pyvenv.cfg are unsupported.
    Linux dedicated prefixes only: complete configured stdlib (lib-dynload),
    Python zips, bin/python*, shared objects throughout lib/lib64 and bundled Tcl/
    Tk runtime data. Shared system prefixes are unsupported, never swept. Retain
    internal file symlink identity; external OS libraries require separate trust.
    """
    root = (root or Path(sys.base_prefix)).resolve(strict=True)
    stdlib = stdlib or Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    if executable is None:
        configured = Path(getattr(sys, "_base_executable", sys.executable))
        executable = configured.parent.resolve(strict=True) / configured.name
    system = system or platform.system()
    if system not in {"Windows", "Linux"}:
        raise ValueError("unsupported Python environment platform")
    if system == "Windows":
        # Supported dedicated layouts have no startup path overrides. Inspect
        # only distribution/DLL and interpreter directories and their immediate
        # parents (pyvenv.cfg); do not sweep an OS tree or follow config content.
        # This post-start check cannot replace independent pre-start verification.
        startup_directories = {root, executable.parent}
        for directory in startup_directories | {p.parent for p in startup_directories}:
            for entry in directory.iterdir():
                name = entry.name.casefold()
                if name == "pyvenv.cfg" or (
                    directory in startup_directories and name.endswith("._pth")
                ):
                    raise ValueError("unsupported Windows startup configuration")
    if system == "Linux" and root.as_posix() in {
        "/",
        "/usr",
        "/usr/local",
        "/usr/lib",
        "/usr/lib64",
        "/lib",
        "/lib64",
        "/opt",
    }:
        raise ValueError("unsupported shared Linux prefix; a dedicated distribution is required")
    hashes: dict[str, str] = {}
    links: dict[str, str] = {}

    def capture(path: Path) -> None:
        relative = path.relative_to(root).as_posix()
        if excluded(relative, system):
            return
        if path.is_symlink():
            target = path.resolve(strict=True)
            target_name = target.relative_to(root).as_posix()
            if not target.is_file() or excluded(target_name, system):
                raise ValueError("Python environment symlink leaves regular runtime files")
            links[relative] = target_name
            capture(target)
            hashes[relative] = hashes[target_name]
        elif path.is_dir():
            if getattr(path.stat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Python environment directory alias prohibited")
            for child in sorted(path.iterdir()):
                capture(child)
        elif path.is_file():
            hashes[relative] = digest(path.read_bytes())
        else:
            raise ValueError("Python environment nonregular or missing runtime file")

    capture(stdlib)
    capture(executable)
    if system == "Windows":
        for name in ("DLLs", "tcl"):
            if (root / name).exists():
                capture(root / name)
        for path in sorted(root.iterdir()):
            if path.suffix.lower() in {".dll", ".exe"} or path.match("python*.zip"):
                capture(path)
    else:

        def native_runtime(path: Path) -> None:
            relative = path.relative_to(root).as_posix()
            if excluded(relative, system) or path == stdlib:
                return
            if path.is_symlink() and path.is_dir():
                raise ValueError("ambiguous Linux native runtime directory alias")
            if path.is_dir():
                if path.name.startswith(("tcl", "tk")):
                    capture(path)
                else:
                    for child in sorted(path.iterdir()):
                        native_runtime(child)
            elif ".so" in path.suffixes or path.match("python*.zip"):
                capture(path)

        for folder in ("lib", "lib64"):
            if (root / folder).exists():
                native_runtime(root / folder)
        for path in sorted((root / "bin").glob("python*")):
            if path.is_file() or path.is_symlink():
                capture(path)
    identity = {
        "implementation": platform.python_implementation(),
        "version": sys.version,
        "build": " | ".join(platform.python_build()),
        "compiler": platform.python_compiler(),
        "system": system,
        "machine": platform.machine(),
        "pointer_bits": str(struct.calcsize("P") * 8),
        "abi": str(sysconfig.get_config_var("SOABI") or sys.implementation.cache_tag),
    }
    value: dict[str, Any] = {
        "policy": POLICY,
        "production_approved": False,
        "external_trust_boundary": BOUNDARY,
        "exclusions": list(EXCLUSIONS),
        "identity": identity,
        "stdlib_path": stdlib.relative_to(root).as_posix(),
        "interpreter_path": executable.relative_to(root).as_posix(),
        "interpreter_sha256": hashes[executable.relative_to(root).as_posix()],
        "dependency_sha256": dependency_sha256,
        "file_hashes": dict(sorted(hashes.items())),
        "symlinks": dict(sorted(links.items())),
    }
    value["python_environment_sha256"] = digest(json_bytes(value))
    validate_document(value)
    return value
