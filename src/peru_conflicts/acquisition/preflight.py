"""Read-only M1-03A validation and deterministic action planning."""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Literal

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.acquisition.models import DryRunAction, DryRunResult
from peru_conflicts.acquisition.plan import LoadedPilotPlan
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.paths import DataPaths, ReadOnlyZoneError


class PreflightError(RuntimeError):
    """Base error for a failed read-only acquisition preflight."""


class BaselineVerificationError(PreflightError):
    """The merged Git or source-integrity receipt baseline did not match."""


class ProtectedSourcePathError(PreflightError):
    """A planned protected-source path was unsafe or unavailable."""


class SourceFingerprintMismatch(PreflightError):
    """A protected source's stable size or SHA-256 differed from the plan."""


class DryRunOutputError(PreflightError):
    """Dry-run output was outside the ignored repository-cache boundary."""


def _git_bytes(repo_root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise BaselineVerificationError(
            f"Git baseline validation failed for: {' '.join(arguments)}"
        ) from error
    return result.stdout


def _verify_baseline(loaded_plan: LoadedPilotPlan, repo_root: Path) -> None:
    plan = loaded_plan.plan
    commit = plan.baseline_receipt_git_commit
    _git_bytes(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    _git_bytes(repo_root, "merge-base", "--is-ancestor", commit, "HEAD")

    relative = PurePosixPath(plan.baseline_receipt_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise BaselineVerificationError("baseline receipt path must be repository-relative")
    worktree_path = repo_root.joinpath(*relative.parts)
    worktree_resolved = worktree_path.resolve()
    repository_resolved = repo_root.resolve()
    if not worktree_resolved.is_relative_to(repository_resolved) or not worktree_resolved.is_file():
        raise BaselineVerificationError("worktree receipt is missing or outside the repository")
    expected = plan.baseline_receipt_sha256
    worktree_bytes = worktree_resolved.read_bytes()
    if hashlib.sha256(worktree_bytes).hexdigest() != expected:
        raise BaselineVerificationError("worktree receipt does not match the pinned SHA-256")
    committed_bytes = _git_bytes(repo_root, "show", f"{commit}:{relative.as_posix()}")
    if hashlib.sha256(committed_bytes).hexdigest() != expected:
        raise BaselineVerificationError("receipt at the pinned Git commit does not match")


def _validate_symbolic_storage_paths(paths: DataPaths, loaded_plan: LoadedPilotPlan) -> None:
    policy = loaded_plan.plan.promotion_policy
    temporary = PurePosixPath(policy.temporary_location)
    temp_parts = temporary.parts
    if (
        temporary.is_absolute()
        or ".." in temp_parts
        or not temp_parts
        or temp_parts[0] != "system_temp"
    ):
        raise PreflightError("temporary location must be rooted at the system-temp symbol")

    staging = PurePosixPath(policy.same_filesystem_staging_location)
    staging_parts = staging.parts
    if (
        staging.is_absolute()
        or staging_parts[:2] != ("conflict_data_root", "01_raw")
        or ".." in staging_parts
    ):
        raise PreflightError("future staging location must remain below conflict_data_root/01_raw")
    logical_staging = Path(os.path.abspath(paths.root.joinpath(*staging_parts[1:])))
    if not logical_staging.is_relative_to(paths.raw):
        raise PreflightError("future staging location escapes the logical raw zone")
    if not logical_staging.resolve().is_relative_to(paths.raw.resolve()):
        raise PreflightError("future staging location escapes the resolved raw zone")


def _resolve_protected_source(paths: DataPaths, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[:2] != ("01_raw", "reports")
    ):
        raise ProtectedSourcePathError("protected source must be below 01_raw/reports")
    reports = paths.raw / "reports"
    logical = Path(os.path.abspath(paths.root.joinpath(*relative.parts)))
    if not logical.is_relative_to(reports):
        raise ProtectedSourcePathError("logical protected source escapes 01_raw/reports")
    resolved_reports = reports.resolve()
    resolved = logical.resolve()
    if not resolved.is_relative_to(resolved_reports):
        raise ProtectedSourcePathError("resolved protected source escapes 01_raw/reports")
    if not resolved.is_file():
        raise ProtectedSourcePathError(
            f"protected source is not an existing regular file: {relative}"
        )
    return resolved


def _stable_file_fingerprint(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = hashlib.sha256()
    observed_bytes = 0
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            observed_bytes += len(chunk)
            digest.update(chunk)
    after = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_opened = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_opened or identity_opened != identity_after:
        raise SourceFingerprintMismatch(f"source changed while it was being hashed: {path.name}")
    if observed_bytes != opened.st_size:
        raise SourceFingerprintMismatch(f"source byte count changed while hashing: {path.name}")
    return observed_bytes, digest.hexdigest()


def _actions(loaded_plan: LoadedPilotPlan) -> tuple[DryRunAction, ...]:
    actions: list[DryRunAction] = []

    def add(
        *,
        phase: Literal["preflight", "future_network", "future_disposition"],
        action: str,
        report_number: int | None = None,
        url_role: Literal["landing", "direct_download"] | None = None,
        url: str | None = None,
        relative_path: str | None = None,
    ) -> None:
        actions.append(
            DryRunAction(
                sequence=len(actions) + 1,
                phase=phase,
                action=action,
                report_number=report_number,
                url_role=url_role,
                url=url,
                relative_path=relative_path,
            )
        )

    for action in (
        "validate_plan_contract",
        "validate_merged_baseline",
        "validate_source_integrity_receipt",
        "validate_data_root",
        "validate_raw_write_protection",
    ):
        add(phase="preflight", action=action)
    for target in loaded_plan.plan.targets:
        add(
            phase="preflight",
            action="validate_existing_source",
            report_number=target.report_number,
            relative_path=target.existing_local_relative_path,
        )
    for target in loaded_plan.plan.targets:
        add(
            phase="future_network",
            action="request_landing_html",
            report_number=target.report_number,
            url_role="landing",
            url=target.landing_page_url,
        )
        add(
            phase="future_network",
            action="stream_pdf_to_system_temp",
            report_number=target.report_number,
            url_role="direct_download",
            url=target.direct_download_url,
        )
        add(
            phase="future_disposition",
            action="compare_hash_then_deduplicate_or_stop_for_review",
            report_number=target.report_number,
            relative_path=target.existing_local_relative_path,
        )
    return tuple(actions)


def run_dry_run_preflight(
    *, loaded_plan: LoadedPilotPlan, repo_root: Path, data_root: Path
) -> DryRunResult:
    plan = loaded_plan.plan
    _verify_baseline(loaded_plan, repo_root.resolve())
    paths = DataPaths.resolve(repo_root=repo_root, data_root=data_root)
    _validate_symbolic_storage_paths(paths, loaded_plan)
    for protected_zone in (paths.external, paths.raw, paths.archive):
        try:
            paths.require_writable(protected_zone / "__m1_03a_write_probe__")
        except ReadOnlyZoneError:
            continue
        raise PreflightError(f"routine write protection is not active for {protected_zone.name}")

    verified_bytes = 0
    for target in plan.targets:
        source = _resolve_protected_source(paths, target.existing_local_relative_path)
        observed_bytes, observed_sha256 = _stable_file_fingerprint(source)
        if (
            observed_bytes != target.existing_local_byte_count
            or observed_sha256 != target.existing_local_sha256
        ):
            raise SourceFingerprintMismatch(
                f"protected source fingerprint mismatch for report {target.report_number}"
            )
        verified_bytes += observed_bytes

    return DryRunResult(
        schema_version="0.1.0",
        run_type="m1_03a_dry_run",
        plan_id=plan.plan_id,
        plan_file_sha256=loaded_plan.file_sha256,
        plan_semantic_sha256=loaded_plan.semantic_sha256,
        target_set_sha256=loaded_plan.target_set_sha256,
        baseline_git_commit=plan.baseline_receipt_git_commit,
        baseline_receipt_path=plan.baseline_receipt_path,
        baseline_receipt_sha256=plan.baseline_receipt_sha256,
        verified_source_count=10,
        verified_source_bytes=verified_bytes,
        logical_url_count=20,
        network_requests=0,
        dropbox_writes=0,
        actions=_actions(loaded_plan),
    )


def write_dry_run_result(
    path: Path, result: DryRunResult, *, repo_root: Path, data_root: Path
) -> None:
    repository = Path(os.path.abspath(repo_root.expanduser()))
    data = Path(os.path.abspath(data_root.expanduser())).resolve(strict=True)
    if not repository.is_dir():
        raise DryRunOutputError("repository root must be an existing directory")
    repository_resolved = repository.resolve(strict=True)
    if (
        repository.is_relative_to(data)
        or data.is_relative_to(repository)
        or repository_resolved.is_relative_to(data)
        or data.is_relative_to(repository_resolved)
    ):
        raise DryRunOutputError("repository and CONFLICT_DATA_ROOT cannot overlap")
    cache_logical = Path(os.path.abspath(repository / ".cache"))
    logical = Path(os.path.abspath(path.expanduser()))
    if not logical.is_relative_to(cache_logical):
        raise DryRunOutputError("dry-run output must remain below repository .cache")
    if logical.is_relative_to(data):
        raise DryRunOutputError("dry-run output cannot be inside CONFLICT_DATA_ROOT")
    content = canonical_json_bytes(result.model_dump(mode="json")) + b"\n"
    relative_parent = logical.parent.relative_to(repository)
    temporary_name = f".{logical.name}.{uuid.uuid4().hex}.tmp"
    try:
        with ExitStack() as stack:
            current = stack.enter_context(DirectoryLease.acquire(repository))
            for part in relative_parent.parts:
                current = stack.enter_context(current.acquire_child(part, create=True))
            current.require_bound()
            if not current.resolved.is_relative_to(
                repository_resolved / ".cache"
            ) or current.resolved.is_relative_to(data):
                raise DryRunOutputError("bound dry-run output must remain below repository .cache")
            try:
                with current.open_child_exclusive(temporary_name) as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                current.require_bound()
                current.unlink_child(logical.name, missing_ok=True)
                current.rename_child_no_replace(temporary_name, logical.name)
            finally:
                current.unlink_child(temporary_name, missing_ok=True)
    except DirectoryLeaseError as error:
        raise DryRunOutputError("dry-run output directory could not remain bound") from error
