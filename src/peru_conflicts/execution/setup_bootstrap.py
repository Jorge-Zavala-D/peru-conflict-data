"""Stdlib-only pre-import gate for an independently protected launch artifact.

The OS, interpreter, initial stdlib and launch artifact are trusted BEFORE this
code executes. The anchor is supplied only by that artifact, never an application
argument or environment option. No anchor/authority is distributed. Protected
installation bytes must remain protected throughout execution (not a hash sandbox).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast


class StartupRejected(ValueError):
    """Only a fixed stage identifier is exposed; never the input exception."""


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return cast(dict[str, Any], value)


def _direct(path: Path) -> bytes:
    for item in (path, *path.parents):
        details = item.lstat()
        if item.is_symlink() or getattr(details, "st_file_attributes", 0) & 0x400:
            raise ValueError("aliased input")
    if not path.is_file():
        raise ValueError("file required")
    return path.read_bytes()


def _pinned(path: str, expected: str) -> bytes:
    value = _direct(Path(path))
    if _hash(value) != expected:
        raise ValueError("pin mismatch")
    return value


def _startup() -> None:
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError("isolated startup required")
    if any(name in sys.modules for name in ("site", "sitecustomize", "usercustomize")):
        raise ValueError("site already processed")
    prohibited = ("python", "openssl_", "ld_", "dyld_", "m2_")
    if any(name.lower().startswith(prohibited) for name in os.environ):
        raise ValueError("startup override")
    if any(
        name == "peru_conflicts"
        or name.startswith("peru_conflicts.")
        or name in {"pydantic", "pydantic_core", "yaml"}
        for name in sys.modules
    ):
        raise ValueError("premature application import")
    base = Path(sys.base_prefix).resolve()
    if any(not p or not Path(p).resolve().is_relative_to(base) for p in sys.path):
        raise ValueError("unapproved initial path")
    for name, module in tuple(sys.modules.items()):
        if name == "__main__":
            continue  # independently protected launch artifact, not application code
        if (
            name in {"typing.io", "typing.re"}
            and module is vars(sys.modules["typing"])[name.split(".")[1]]
        ):
            continue  # Python 3.12 stdlib aliases, not separately loaded modules
        spec = getattr(module, "__spec__", None)
        if spec is not None and spec.origin in {"built-in", "frozen"}:
            continue
        origin = getattr(module, "__file__", None)
        if origin is None or not Path(origin).resolve().is_relative_to(base):
            raise ValueError("unapproved loaded module")


def start(
    anchor: dict[str, Any] | None,
    private_reader: Callable[[], bytes],
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Any:
    """Private protected-launcher seam; not a caller-selectable trust API/CLI.

    An external protected launcher pins this file BEFORE executing it. Its anchor
    pins the installation, registry and environment document independently; these
    documents do not carry their own authority. Application inventory includes this
    file and the distributed entry, avoiding self-hash exclusions/circular pins.
    """
    stage = "STARTUP"
    result: Any = None
    succeeded = False
    with suppress(Exception):
        _startup()
        stage = "CLOSED"
        if anchor is None:
            raise ValueError("no installed independent authority")
        stage = "ANCHOR"
        if set(anchor) != {
            "bootstrap_sha256",
            "installation_path",
            "installation_sha256",
            "registry_path",
            "registry_sha256",
            "grant_path",
            "environment_path",
            "environment_sha256",
            "executable",
            "initial_paths",
        }:
            raise ValueError("anchor fields")
        _pinned(__file__, anchor["bootstrap_sha256"])
        if str(Path(sys.executable).resolve()) != anchor["executable"]:
            raise ValueError("wrong interpreter")
        if list(sys.path) != anchor["initial_paths"]:
            raise ValueError("initial paths differ")
        stage = "REGISTRY"
        registry_raw = _pinned(anchor["registry_path"], anchor["registry_sha256"])
        registry = _json(registry_raw)
        if set(registry) != {"version", "grants"} or registry["version"] != "m2-real-registry-v2":
            raise ValueError("registry shape")
        if len(registry["grants"]) != 1:
            raise ValueError("one exact registered installation required")
        entry = registry["grants"][0]
        if set(entry) != {"grant_sha256", "installation_sha256", "revoked"}:
            raise ValueError("registry entry")
        if (
            entry["revoked"] is not False
            or entry["installation_sha256"] != anchor["installation_sha256"]
        ):
            raise ValueError("revoked/substituted installation")
        stage = "INSTALLATION"
        raw = _pinned(anchor["installation_path"], anchor["installation_sha256"])
        pin = _json(raw)
        now = clock()
        if pin["revoked"] is not False or not now < datetime.fromisoformat(pin["validity_end"]):
            raise ValueError("revoked/expired installation")
        grant = _pinned(anchor["grant_path"], entry["grant_sha256"])
        if pin["grant_sha256"] != entry["grant_sha256"]:
            raise ValueError("grant binding")
        stage = "SOURCE"
        root = Path(pin["source_root"])
        # The source pin is a Python-source inventory. Do not let a native or
        # legacy sourceless module outrank those measured .py files at import.
        if any(
            p.suffix.lower() in {".pyd", ".so", ".pyc"} and "__pycache__" not in p.parts
            for p in root.joinpath("src").rglob("*")
        ):
            raise ValueError("unmeasured source executable")
        paths = [
            *root.joinpath("src").rglob("*.py"),
            *root.joinpath("scripts").rglob("*.py"),
            root / "uv.lock",
            root / "pyproject.toml",
        ]
        if {p.relative_to(root).as_posix(): _hash(_direct(p)) for p in paths} != pin[
            "source_files"
        ]:
            raise ValueError("source inventory")
        stage = "RUNTIME"
        executable = Path(sys.executable).resolve()
        venv = executable.parent.parent
        site = (
            venv / "Lib/site-packages"
            if os.name == "nt"
            else venv / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        )
        if any("__pycache__" not in p.parts for p in site.rglob("*.pyc")):
            raise ValueError("unmeasured dependency executable")
        files = [
            p
            for p in site.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        ]
        runtime = {
            str(executable): _hash(_direct(executable)),
            **{str(p): _hash(_direct(p)) for p in files},
        }
        if runtime != pin["runtime_files"]:
            raise ValueError("runtime inventory")
        stage = "ENVIRONMENT"
        sys.prefix = sys.exec_prefix = str(venv)
        environment = _json(_pinned(anchor["environment_path"], anchor["environment_sha256"]))
        # This stdlib-only policy module is authenticated by SOURCE before exec.
        policy_path = root / "src/peru_conflicts/execution/python_environment_policy.py"
        policy = ModuleType("_verified_m2_environment")
        policy.__file__ = str(policy_path)
        exec(compile(_direct(policy_path), str(policy_path), "exec"), policy.__dict__)
        dependency = _hash(
            json.dumps(
                runtime, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        measured = policy.capture_document(dependency)
        if (
            measured != environment
            or measured["python_environment_sha256"] != pin["python_environment_sha256"]
        ):
            raise ValueError("environment identity")
        stage = "ORIGIN"
        # -B prevents writes, not reads of unmeasured cache files. Use a fixed,
        # absent cache tree so only the inventoried sources can supply bytecode.
        # The trusted installation must remain immutable throughout execution.
        no_cache = venv / ".m2-disabled-bytecode"
        if no_cache.exists():
            raise ValueError("bytecode cache is not absent")
        sys.pycache_prefix = str(no_cache)
        sys.path.extend((str(root / "src"), str(site)))
        for name, expected in (
            ("peru_conflicts", root / "src"),
            ("pydantic", site),
            ("pydantic_core", site),
            ("yaml", site),
            ("annotated_types", site),
            ("typing_extensions", site),
            ("typing_inspection", site),
        ):
            spec = importlib.util.find_spec(name)
            if (
                spec is None
                or spec.origin is None
                or not Path(spec.origin).resolve().is_relative_to(expected)
            ):
                raise ValueError("module origin")
        # -S on Python 3.12 skips venv prefix setup; establish the verified prefix
        # explicitly, never process .pth/sitecustomize or use an editable loader.
        sys.prefix = sys.exec_prefix = str(venv)
        import sysconfig

        sysconfig.get_paths()  # populated before verification below, not authority
        if Path(sysconfig.get_path("purelib")).resolve() != site.resolve():
            raise ValueError("runtime import prefix")
        os.environ["PYDANTIC_DISABLE_PLUGINS"] = "__all__"
        stage = "ADMISSION"
        deployment = importlib.import_module("peru_conflicts.execution.setup_deployment")
        loader = vars(deployment)["_load_verified"]

        def revalidate() -> bytes:
            _pinned(anchor["registry_path"], anchor["registry_sha256"])
            return _pinned(anchor["installation_path"], anchor["installation_sha256"])

        result = loader(
            grant, raw, anchor["installation_sha256"], private_reader, revalidate, clock=clock
        )
        succeeded = True
    if not succeeded:
        raise StartupRejected(stage)
    return result
