"""Closed M2 entry: no independently protected installation is distributed."""

import sys

_BOOTSTRAP_SHA256 = "64a6a65f6f60304a9eddd9b134ec7e3606b79115d5ea730a75d3861b7ac75563"


def launch(anchor: dict[str, object] | None, private_reader: object, clock: object) -> object:
    """Internal protected-launch-artifact seam, never CLI-selected trust."""
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError("STARTUP")
    if [(getattr(x, "__module__", None), getattr(x, "__name__", None)) for x in sys.meta_path] != [
        ("_frozen_importlib", "BuiltinImporter"),
        ("_frozen_importlib", "FrozenImporter"),
        ("_frozen_importlib_external", "PathFinder"),
    ]:
        raise ValueError("STARTUP")
    # os/path are frozen in the supported CPython startup. Check search paths
    # before importing even bootstrap stdlib helpers from the filesystem.
    import os

    base = os.path.normcase(os.path.abspath(sys.base_prefix))
    for path in sys.path:
        normalized = os.path.normcase(os.path.abspath(path))
        if (
            not path
            or not (normalized == base or normalized.startswith(base + os.sep))
            or "site-packages" in normalized.split(os.sep)
            or "dist-packages" in normalized.split(os.sep)
        ):
            raise ValueError("STARTUP")
    if isinstance(anchor, dict) and list(sys.path) != anchor.get("initial_paths"):
        raise ValueError("STARTUP")
    import hashlib
    from contextlib import suppress
    from pathlib import Path
    from types import ModuleType

    module = None
    with suppress(Exception):
        path = (
            Path(__file__).resolve().parents[1] / "src/peru_conflicts/execution/setup_bootstrap.py"
        )
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != _BOOTSTRAP_SHA256:
            raise ValueError("bootstrap differs")
        candidate = ModuleType("_verified_m2_bootstrap")
        candidate.__file__ = str(path)
        exec(compile(raw, str(path), "exec"), candidate.__dict__)
        module = candidate
    if module is None or not hasattr(module, "start"):
        raise ValueError("BOOTSTRAP")
    return module.start(anchor, private_reader, clock=clock)


def operate(operation: str, context: object) -> dict[str, object]:
    """Only a verified launch may supply the installed context; never CLI trust."""
    from peru_conflicts.execution.setup_operator import operate as dispatch

    return dispatch(operation, context)


def main() -> int:
    # No project/third-party import, private lookup or network is reachable here.
    # A populated launch artifact must be independently reviewed and protected;
    # it authenticates setup_bootstrap bytes before invoking its private seam.
    stage = "STARTUP"
    if sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode:
        operation = sys.argv[1] if len(sys.argv) == 2 else "status"
        if len(sys.argv) > 2 or operation not in {
            "admit",
            "next",
            "capture",
            "import",
            "status",
            "recover",
        }:
            stage = "ARGUMENTS"
        else:
            from datetime import UTC, datetime

            try:
                context = launch(None, None, lambda: datetime.now(UTC))
                import json

                result = operate(operation, context)
                print(json.dumps(result, sort_keys=True))
                return int(str(result["exit_code"]))
            except ValueError as error:
                stage = (
                    str(error) if str(error) in {"CLOSED", "STARTUP", "BOOTSTRAP"} else "REJECTED"
                )
    print(f"M2 startup rejected: {stage}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
