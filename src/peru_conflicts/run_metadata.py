"""Capture reproducibility identity for every pipeline run."""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from peru_conflicts.hashing import hash_mapping, sha256_file
from peru_conflicts.models import SCHEMA_VERSION, ModelInvocation
from peru_conflicts.models.common import Sha256, StrictModel, VersionedModel


class GitState(StrictModel):
    commit: str
    dirty: bool


class EnvironmentFingerprint(StrictModel):
    python_version: str
    python_implementation: str
    platform: str
    machine: str
    package_versions: dict[str, str]
    system_binaries: dict[str, str] = Field(default_factory=dict)


class RunMetadata(VersionedModel):
    run_id: str
    started_at: datetime
    git: GitState
    config_hash: Sha256
    schema_hash: Sha256
    lockfile_hash: Sha256 | None = None
    parser_versions: dict[str, str]
    input_hashes: dict[str, Sha256]
    environment: EnvironmentFingerprint
    model_invocations: tuple[ModelInvocation, ...] = ()


def capture_run_metadata(
    *,
    project_root: Path,
    config_paths: Iterable[Path],
    input_paths: Mapping[str, Path],
    parser_versions: Mapping[str, str],
    git_state: GitState | None = None,
    model_invocations: Sequence[ModelInvocation] = (),
    system_binaries: Mapping[str, str] | None = None,
    started_at: datetime | None = None,
    run_id: str | None = None,
) -> RunMetadata:
    """Build a complete run fingerprint without writing it to storage."""

    root = project_root.resolve()
    ordered_configs = sorted(
        (path.resolve() for path in config_paths), key=lambda path: path.as_posix()
    )
    config_hashes = {
        f"{index:04d}:{_portable_key(path, root)}": sha256_file(path)
        for index, path in enumerate(ordered_configs)
    }
    schema_hashes = {
        _portable_key(path, root): sha256_file(path)
        for path in sorted((root / "schemas").rglob("*.schema.json"))
    }
    lockfile = root / "uv.lock"

    return RunMetadata(
        run_id=run_id or f"run_{uuid4()}",
        started_at=started_at or datetime.now(UTC),
        git=git_state or _capture_git_state(root),
        config_hash=hash_mapping(config_hashes),
        schema_hash=hash_mapping(schema_hashes),
        lockfile_hash=sha256_file(lockfile) if lockfile.is_file() else None,
        parser_versions=dict(sorted(parser_versions.items())),
        input_hashes={name: sha256_file(path) for name, path in sorted(input_paths.items())},
        environment=_capture_environment(system_binaries or {}),
        model_invocations=tuple(model_invocations),
        schema_version=SCHEMA_VERSION,
    )


def _portable_key(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.name


def _capture_git_state(project_root: Path) -> GitState:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return GitState(commit=commit, dirty=bool(status.strip()))


def _capture_environment(system_binaries: Mapping[str, str]) -> EnvironmentFingerprint:
    package_names = ("pydantic", "PyYAML")
    versions = {name: importlib.metadata.version(name) for name in package_names}
    return EnvironmentFingerprint(
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        platform=platform.platform(),
        machine=platform.machine(),
        package_versions=versions,
        system_binaries=dict(sorted(system_binaries.items())),
    )
