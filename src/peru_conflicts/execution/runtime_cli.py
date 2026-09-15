"""Separately trusted, standard-library-only launcher for an unissued runtime.

Invoke an independently protected copy with a trusted interpreter: python -I -S
-B trusted_launcher.py ... . The launcher and interpreter/stdlib are trust roots,
not authenticated by their own claims. Native dependency storage must also be
independently protected throughout the process; pin checks do not replace that
operational prerequisite. This program never establishes human launch authority.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
import stat
import sys
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, cast


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def document(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("identity must be a JSON object")
    return cast(dict[str, Any], value)


def relative_name(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or str(path) != value
        or any(p in {".", ".."} for p in path.parts)
        or "\\" in value
        or ":" in value
    ):
        raise ValueError("unsafe relative file name")


def _not_alias(path: Path) -> None:
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("aliased path is prohibited")
    if path.absolute() != path.resolve(strict=True):
        raise ValueError("path resolves through an alias")


@contextmanager
def _windows_guard(path: Path, directory: bool) -> Generator[None]:
    """Retain read-only Windows sharing through all reads and imports."""
    if os.name != "nt":
        yield
        return
    from ctypes import wintypes

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
    handle = create(
        str(path), 0x80000000, 1, None, 3, 0x00200000 | (0x02000000 if directory else 0), None
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ValueError("read custody unavailable")
    try:
        _not_alias(path)
        yield
    finally:
        if not close(handle):
            raise ValueError("read custody close failed")


def _open_directory(path: Path, parent_fd: int | None) -> int | None:
    if os.name == "nt":
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path if parent_fd is None else path.name, flags, dir_fd=parent_fd)


def _capture_regular_file(path: Path, stack: ExitStack, parent_fd: int | None) -> bytes:
    """Bind all reads to one regular, singly linked file and retained parent."""

    def child_stat() -> os.stat_result:
        return (
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if parent_fd is not None
            else path.lstat()
        )

    def require_regular(info: os.stat_result) -> None:
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("non-regular or aliased input")
        if info.st_nlink != 1:
            raise ValueError("hard-linked input is prohibited")

    def signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return (info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns)

    before = child_stat()
    require_regular(before)
    stack.enter_context(_windows_guard(path, False))
    fd = os.open(
        path.name if parent_fd is not None else path,
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
        dir_fd=parent_fd,
    )
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        # O_NONBLOCK prevents a replacement FIFO from blocking before this check.
        require_regular(opened)
        if signature(before) != signature(opened):
            raise ValueError("input replaced before capture")
        data = stream.read()
        after = os.fstat(stream.fileno())
    bound = child_stat()
    require_regular(after)
    require_regular(bound)
    # Windows Python 3.12 pathname stat reports creation time in st_ctime;
    # descriptor stat reports change time. Compare each clock to itself.
    if (
        not signature(before) == signature(opened) == signature(after) == signature(bound)
        or before.st_ctime_ns != bound.st_ctime_ns
        or opened.st_ctime_ns != after.st_ctime_ns
    ):
        raise ValueError("input changed during capture")
    return data


def read_file(path: Path, stack: ExitStack) -> bytes:
    """Capture one input without reading unrelated siblings in its directory."""
    _not_alias(path)
    parent = path.parent
    stack.enter_context(_windows_guard(parent, True))
    descriptor = _open_directory(parent, None)
    if descriptor is not None:
        stack.callback(os.close, descriptor)
    before = os.fstat(descriptor) if descriptor is not None else parent.stat()
    data = _capture_regular_file(path, stack, descriptor)
    after = os.fstat(descriptor) if descriptor is not None else parent.stat()
    _not_alias(path)
    bound = parent.stat()
    if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or (before.st_dev, before.st_ino) != (bound.st_dev, bound.st_ino):
        raise ValueError("input parent changed during capture")
    return data


def read_tree(root: Path, stack: ExitStack) -> dict[str, bytes]:
    """Read retained descriptors, rejecting aliases and changes during capture."""
    _not_alias(root)
    result: dict[str, bytes] = {}

    def visit(path: Path, prefix: str, parent_fd: int | None = None) -> None:
        stack.enter_context(_windows_guard(path, True))
        descriptor = _open_directory(path, parent_fd)
        if descriptor is not None:
            stack.callback(os.close, descriptor)
        before = os.fstat(descriptor) if descriptor is not None else path.stat()
        entries = sorted(os.listdir(descriptor if descriptor is not None else path))
        for name in entries:
            relative_name(name)
            child = path / name
            info = (
                os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if descriptor is not None
                else child.lstat()
            )
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("aliased package entry")
            if stat.S_ISDIR(info.st_mode):
                visit(child, prefix + name + "/", descriptor)
            elif stat.S_ISREG(info.st_mode):
                result[prefix + name] = _capture_regular_file(child, stack, descriptor)
            else:
                raise ValueError("non-regular input")
        after_dir = os.fstat(descriptor) if descriptor is not None else path.stat()
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
            after_dir.st_dev,
            after_dir.st_ino,
            after_dir.st_mtime_ns,
            after_dir.st_ctime_ns,
        ):
            raise ValueError("directory changed during capture")
        _not_alias(path)
        bound_dir = path.stat()
        if (before.st_dev, before.st_ino) != (bound_dir.st_dev, bound_dir.st_ino):
            raise ValueError("directory replaced during capture")

    visit(root, "")
    return result


def _inventory(
    files: Mapping[str, bytes], hashes: dict[str, Any], *, mutable: frozenset[str] = frozenset()
) -> None:
    if set(files) != set(hashes):
        raise ValueError("file inventory differs")
    for name, expected in hashes.items():
        relative_name(name)
        if name not in mutable and digest(files[name]) != expected:
            raise ValueError("pinned file bytes differ")


class MemoryModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """No repository fallback; execute only the already verified source bytes."""

    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.modules: dict[str, tuple[bytes, bool]] = {}
        for name, data in files.items():
            if name.startswith("peru_conflicts/") and name.endswith(".py"):
                package = name.endswith("/__init__.py")
                module = (name[:-12] if package else name[:-3]).replace("/", ".")
                self.modules[module] = data, package

    def find_spec(
        self, fullname: str, path: object = None, target: ModuleType | None = None
    ) -> Any:
        if fullname != "peru_conflicts" and not fullname.startswith("peru_conflicts."):
            return None
        if fullname not in self.modules:
            raise ModuleNotFoundError("module is outside neutral source allowlist")
        return importlib.util.spec_from_loader(fullname, self, is_package=self.modules[fullname][1])

    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        source, _ = self.modules[module.__name__]
        exec(compile(source, "<verified-neutral-source>", "exec"), module.__dict__)


def _csv(header: str, rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=header.split(","), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def execute(args: argparse.Namespace, stack: ExitStack) -> str:
    if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:
        raise ValueError("trusted interpreter requires -I -S -B")
    if digest(Path(__file__).read_bytes()) != args.launcher_sha256:
        raise ValueError("trusted launcher pin differs")
    if digest(Path(sys.executable).resolve().read_bytes()) != args.interpreter_sha256:
        raise ValueError("trusted interpreter pin differs")
    files = read_tree(args.runtime, stack)
    manifest = document(files.pop("RUNTIME_MANIFEST.json"))
    if manifest["policy"] != "m2-neutral-runtime-source-selection-v1":
        raise ValueError("runtime policy differs")
    expected_runtime = digest(
        json_bytes({"policy": manifest["policy"], "file_hashes": manifest["file_hashes"]})
    )
    if expected_runtime != args.runtime_sha256 or manifest["runtime_sha256"] != args.runtime_sha256:
        raise ValueError("trusted runtime pin differs")
    _inventory(files, manifest["file_hashes"])
    for field in (
        "dependency",
        "contract",
        "launcher",
        "interpreter",
        "python_environment",
        "python_environment_manifest",
    ):
        if manifest[field + "_sha256"] != getattr(args, field + "_sha256"):
            raise ValueError("runtime prerequisite pin differs")
    if (
        digest(files["CONTRACT.json"]) != args.contract_sha256
        or digest(files["DEPENDENCIES.json"]) != args.dependency_sha256
        or digest(files["FIELD_REGISTRY.json"]) != manifest["registry_sha256"]
    ):
        raise ValueError("runtime material pin differs")
    if digest(files["PYTHON_ENVIRONMENT.json"]) != args.python_environment_manifest_sha256:
        raise ValueError("Python environment manifest pin differs")
    # This policy is executed only from the already verified runtime snapshot.
    # No repository fallback, site import, or third-party validator is involved.
    # These are consistency checks; already-loaded stdlib and later OS/native
    # reads require independently provisioned, continuously protected custody.
    environment_policy: dict[str, Any] = {"__name__": "verified_python_environment_policy"}
    exec(
        compile(files["PYTHON_ENVIRONMENT_POLICY.py"], "<verified-environment-policy>", "exec"),
        environment_policy,
    )
    environment = document(files["PYTHON_ENVIRONMENT.json"])
    environment_policy["validate_document"](environment)
    if (
        manifest["python_environment"] != environment
        or environment["python_environment_sha256"] != args.python_environment_sha256
        or environment["interpreter_sha256"] != args.interpreter_sha256
        or environment["dependency_sha256"] != args.dependency_sha256
        or environment_policy["capture_document"](args.dependency_sha256) != environment
    ):
        raise ValueError("Python environment differs independently supplied rehearsal pins")
    dependencies = document(files["DEPENDENCIES.json"])
    if (
        dependencies["python_version"] != sys.version
        or manifest["python_version"] != sys.version
        or dependencies["versions"] != manifest["dependency_versions"]
    ):
        raise ValueError("interpreter or dependency version differs")
    dependency_files = read_tree(args.dependencies, stack)
    _inventory(dependency_files, dependencies["file_hashes"])
    package_files = read_tree(args.package, stack)
    view = document(package_files.pop("NEUTRAL_VIEW.json"))
    if view.pop("view_sha256") != args.view_sha256 or digest(json_bytes(view)) != args.view_sha256:
        raise ValueError("trusted neutral view pin differs")
    if (
        view["policy"] != "m2-neutral-human-view-v1"
        or view["original_package_sha256"] != args.package_sha256
        or view["contract_sha256"] != args.contract_sha256
    ):
        raise ValueError("neutral view lineage differs")
    if digest(package_files["PACKAGE_MANIFEST.json"]) != args.package_sha256:
        raise ValueError("trusted original package pin differs")
    receipt_bytes = read_file(args.issuance, stack)
    if digest(receipt_bytes) != args.issuance_sha256:
        raise ValueError("trusted receipt pin differs")
    receipt = document(receipt_bytes)
    expected_receipt = {
        "kind": "UNISSUED_RUNTIME_REHEARSAL",
        "runtime_sha256": args.runtime_sha256,
        "dependency_sha256": args.dependency_sha256,
        "launcher_sha256": args.launcher_sha256,
        "interpreter_sha256": args.interpreter_sha256,
        "python_environment_sha256": args.python_environment_sha256,
        "python_environment_manifest_sha256": args.python_environment_manifest_sha256,
        "view_sha256": args.view_sha256,
        "original_package_sha256": args.package_sha256,
        "contract_sha256": args.contract_sha256,
        "role": args.role,
        "run_id": document(package_files["PACKAGE_MANIFEST.json"])["run_id"],
    }
    if receipt != expected_receipt:
        raise ValueError("receipt binding differs")
    # All package, runtime and dependency identities are verified before importing
    # any non-stdlib code. Native-library storage remains an external trust root.
    if any(name == "peru_conflicts" or name.startswith("peru_conflicts.") for name in sys.modules):
        raise ValueError("repository modules already loaded")
    sys.path.append(str(args.dependencies))
    sys.meta_path.insert(0, MemoryModules(files))
    from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES
    from peru_conflicts.execution.discovery import position_from_reference
    from peru_conflicts.execution.neutral_forms import empty_slots, rows, validate_neutral_forms
    from peru_conflicts.execution.packages import FORM_HEADERS, PackageManifest
    from peru_conflicts.execution.references import reference_text, select_position, verify_pages

    registry = {
        family: tuple(fields) for family, fields in document(files["FIELD_REGISTRY.json"]).items()
    }
    manifest_model = PackageManifest.model_validate_json(package_files["PACKAGE_MANIFEST.json"])
    if (
        manifest_model.role != args.role
        or manifest_model.package_id != view["original_package_id"]
        or json_bytes(manifest_model.contract_identity.model_dump(mode="json"))
        != files["CONTRACT.json"]
    ):
        raise ValueError("package role or contract differs")

    def package_verifier(candidate: Mapping[str, bytes]) -> Any:
        _inventory(candidate, view["file_hashes"], mutable=frozenset(FORM_HEADERS))
        for name in FORM_HEADERS:
            rows(candidate, name)
        for reference in manifest_model.references:
            verify_pages(
                reference,
                {
                    p.page: candidate[f"references/{reference.report_number}/{p.page:04d}.txt"]
                    for p in reference.pages
                },
            )
        return manifest_model

    package_verifier(package_files)
    if args.command in {"page", "position"}:
        data = package_files[f"references/{args.report}/{args.page:04d}.txt"]
        if args.command == "page":
            return "".join(
                f"{number}: {line}\n"
                for number, line in enumerate(reference_text(data).split("\n"), 1)
            )
        position = position_from_reference(
            page=args.page,
            offset=select_position(data, line=args.line, column=args.column),
            reference=data,
        )
        return json_bytes(position.model_dump(mode="json")).decode()
    if args.command == "slots":
        return _csv(
            FORM_HEADERS["annotations.csv"],
            empty_slots(
                package_files, required_field_registry=registry, package_verifier=package_verifier
            ),
        )
    if args.command == "inspection-template":
        return _csv(
            FORM_HEADERS["inspection.csv"],
            [
                {
                    "report_number": str(reference.report_number),
                    "object_family": family,
                    "inspection_complete": "",
                    "zero_discoveries_confirmed": "",
                    "comment": "",
                }
                for reference in manifest_model.references
                for family in sorted(BENCHMARK_OBJECT_TYPES)
            ],
        )
    draft = validate_neutral_forms(
        package_files,
        expected_package=manifest_model,
        require_complete=args.require_complete,
        required_field_registry=registry,
        package_verifier=package_verifier,
    )
    return json_bytes(draft.model_dump(mode="json", exclude={"input_files"})).decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Unissued neutral source-form runtime")
    for name in ("runtime", "dependencies", "package", "issuance"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in (
        "runtime",
        "dependency",
        "launcher",
        "interpreter",
        "python-environment",
        "python-environment-manifest",
        "view",
        "package",
        "contract",
        "issuance",
    ):
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--role", choices=("annotator-a", "annotator-b"), required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("page", "position", "slots", "inspection-template", "validate"):
        command = commands.add_parser(name)
        if name in {"page", "position"}:
            command.add_argument("--report", type=int, required=True)
            command.add_argument("--page", type=int, required=True)
        if name == "position":
            command.add_argument("--line", type=int, required=True)
            command.add_argument("--column", type=int, required=True)
        if name == "validate":
            command.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        with ExitStack() as stack:
            output = execute(args, stack)
        sys.stdout.buffer.write(output.encode("utf-8"))
        return 0
    except Exception:
        # User values, physical paths and internal implementation are not emitted.
        sys.stderr.write("Neutral runtime rejected the inputs or prerequisites.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
