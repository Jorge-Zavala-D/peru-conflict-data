"""Human-form validation and synthetic-only immutable lifecycle."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.benchmark.models import (
    AnnotatorSubmission,
    PartitionRole,
    SubmissionStatus,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .discovery import (
    DiscoveredObject,
    DiscoveryComparison,
    DiscoveryWindow,
    compare_discoveries,
)
from .neutral_forms import (
    DiscoveryFormHeader as DiscoveryFormHeader,
)
from .neutral_forms import (
    declarations as declarations,
)
from .neutral_forms import (
    empty_slots as empty_slots,
)
from .neutral_forms import (
    required_fields as required_fields,
)
from .neutral_forms import (
    rows as rows,
)
from .neutral_forms import (
    validate_neutral_forms,
)
from .packages import (
    PackageManifest,
    publish_new,
    require_readiness_root,
)
from .references import sha256


class ValidatedDraft(StrictModel):
    package: PackageManifest
    input_files: dict[str, bytes]
    coordinator_partitions: dict[int, PartitionRole]
    input_hashes: dict[str, Sha256]
    discoveries: tuple[DiscoveredObject, ...]
    unresolved: tuple[dict[str, str], ...]
    inspections: tuple[dict[str, str], ...]
    submissions: tuple[AnnotatorSubmission, ...]
    complete: bool


def validate_forms(
    files: Mapping[str, bytes],
    partitions: Mapping[int, PartitionRole],
    *,
    expected_package: PackageManifest,
    require_complete: bool = False,
) -> ValidatedDraft:
    manifest, _, _ = declarations(files)
    if manifest != expected_package:
        raise ValueError("package/source/reference differs from trusted coordinator assignment")
    if set(partitions) != {m.report_number for m in manifest.references}:
        raise ValueError("coordinator routing differs from assignment")
    neutral = validate_neutral_forms(
        files, expected_package=expected_package, require_complete=require_complete
    )
    submissions = tuple(
        AnnotatorSubmission(
            submission_id="draft-"
            + sha256(canonical_json_bytes([manifest.package_id, record.discovery_id])),
            annotator_id=manifest.role,
            unit_id=discovery.to_annotation_unit().unit_id,
            partition_role=partitions[discovery.window.report_number],
            status=SubmissionStatus.DRAFT,
            object_inventory=record.object_inventory,
            annotations=record.annotations,
        )
        for discovery, record in zip(neutral.discoveries, neutral.records, strict=True)
    )
    return ValidatedDraft(
        package=neutral.package,
        input_files=neutral.input_files,
        coordinator_partitions=dict(partitions),
        input_hashes=neutral.input_hashes,
        discoveries=neutral.discoveries,
        unresolved=neutral.unresolved,
        inspections=neutral.inspections,
        submissions=submissions,
        complete=neutral.complete,
    )


class SyntheticLock(StrictModel):
    kind: Literal["SYNTHETIC_EXECUTION_PROOF_NOT_HUMAN_SUBMISSION"] = (
        "SYNTHETIC_EXECUTION_PROOF_NOT_HUMAN_SUBMISSION"
    )
    lock_id: str
    locked_at: AwareDatetime
    supersedes: Sha256 | None = None
    draft: ValidatedDraft
    locked_submissions: tuple[AnnotatorSubmission, ...]


def read_locked(root: Path, digest: str) -> SyntheticLock:
    require_readiness_root(root)
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("lock identity must be exact SHA-256")
    with DirectoryLease.acquire(root) as parent, parent.acquire_child(digest) as directory:
        with directory.open_child_read("payload.json") as stream:
            data = stream.read()
        with directory.open_child_read("receipt.sha256") as stream:
            seal = stream.read()
    if sha256(data) != digest or seal != (digest + "\n").encode():
        raise ValueError("locked payload changed or publication incomplete")
    return SyntheticLock.model_validate_json(data)


def _history(root: Path) -> dict[str, SyntheticLock]:
    require_readiness_root(root)
    return {
        path.name: read_locked(root, path.name)
        for path in sorted(root.iterdir())
        if path.name != ".publication.lock"
    }


@contextmanager
def _publication_guard(root: Path) -> Generator[None]:
    require_readiness_root(root)
    with DirectoryLease.acquire(root) as parent:
        stream = parent.open_child_exclusive(".publication.lock")
        try:
            stream.write(b"synthetic publication in progress\n")
            stream.flush()
            os.fsync(stream.fileno())
            yield
        finally:
            stream.close()
            parent.unlink_child(".publication.lock")


def lock_synthetic(
    root: Path,
    draft: ValidatedDraft,
    lock_id: str,
    locked_at: datetime,
    *,
    expected_package: PackageManifest,
    confirmed: bool,
    supersedes: str | None = None,
) -> str:
    if draft.package != expected_package:
        raise ValueError("lock differs from trusted coordinator assignment")
    with _publication_guard(root):
        return _lock_synthetic(
            root, draft, lock_id, locked_at, confirmed=confirmed, supersedes=supersedes
        )


def _lock_synthetic(
    root: Path,
    draft: ValidatedDraft,
    lock_id: str,
    locked_at: datetime,
    *,
    confirmed: bool,
    supersedes: str | None,
) -> str:
    if not confirmed or not draft.complete:
        raise ValueError("explicit completion confirmation and complete validation required")
    if draft.package.run_id != "synthetic-run":
        raise ValueError("real annotation launch is not approved; synthetic rehearsal only")
    verified = validate_forms(
        draft.input_files,
        draft.coordinator_partitions,
        expected_package=draft.package,
        require_complete=True,
    )
    if verified != draft:
        raise ValueError("validated draft differs from freshly verified input bytes")
    history = _history(root)
    if any(record.lock_id == lock_id for record in history.values()):
        raise ValueError("lock ID already published; overwrite prohibited")
    if supersedes is None and any(r.draft.package == draft.package for r in history.values()):
        raise ValueError("existing package lock requires explicit supersession")
    if supersedes is not None:
        if supersedes not in history or any(r.supersedes == supersedes for r in history.values()):
            raise ValueError("supersession needs preserved current parent")
        parent = history[supersedes]
        if parent.draft.package != draft.package:
            raise ValueError("supersession cannot change package/run/role")
    locked = tuple(
        AnnotatorSubmission.model_validate_json(
            json.dumps(
                s.model_dump(mode="json")
                | {
                    "status": "locked",
                    "locked_at": locked_at.isoformat(),
                    "submission_id": lock_id + "-" + str(index),
                    "supersedes_submission_id": None
                    if supersedes is None
                    else next(
                        (
                            p.submission_id
                            for p in history[supersedes].locked_submissions
                            if p.unit_id == s.unit_id
                        ),
                        None,
                    ),
                }
            )
        )
        for index, s in enumerate(draft.submissions)
    )
    record = SyntheticLock(
        lock_id=lock_id,
        locked_at=locked_at,
        supersedes=supersedes,
        draft=draft,
        locked_submissions=locked,
    )
    data = canonical_json_bytes(record.model_dump(mode="json")) + b"\n"
    digest = sha256(data)
    publish_new(root, f"{digest}/payload.json", data)
    publish_new(root, f"{digest}/receipt.sha256", (digest + "\n").encode())
    read_locked(root, digest)
    return digest


def compare_locked(
    root: Path, a: str, b: str, *, right_root: Path | None = None
) -> dict[int, DiscoveryComparison]:
    roots = sorted({root.resolve(), (right_root or root).resolve()})
    with ExitStack() as stack:
        for directory in roots:
            stack.enter_context(_publication_guard(directory))
        return _compare_locked(root, a, b, right_root=right_root)


def _compare_locked(
    root: Path, a: str, b: str, *, right_root: Path | None = None
) -> dict[int, DiscoveryComparison]:
    history = _history(root)
    right_history = history if right_root is None else _history(right_root)
    if a not in history or b not in right_history:
        raise ValueError("comparison requires two published locks")
    if any(record.supersedes in {a, b} for record in (*history.values(), *right_history.values())):
        raise ValueError("comparison input is superseded")
    left, right = history[a].draft, right_history[b].draft
    if (
        left.package.role != "annotator-a"
        or right.package.role != "annotator-b"
        or left.package.references != right.package.references
        or left.coordinator_partitions != right.coordinator_partitions
    ):
        raise ValueError("comparison requires distinct A/B roles with identical source references")
    return {
        m.report_number: compare_discoveries(
            DiscoveryWindow(
                report_number=m.report_number,
                source_sha256=m.source_sha256,
                page_count=m.page_count,
            ),
            left.package.role,
            right.package.role,
            tuple(d for d in left.discoveries if d.window.report_number == m.report_number),
            tuple(d for d in right.discoveries if d.window.report_number == m.report_number),
        )
        for m in left.package.references
    }
