"""Identity-bound recovery of deterministic run-owned system-temp objects."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from peru_conflicts.acquisition.engine import (
    DownloadedObject,
    TemporaryPathBoundaryError,
    lease_system_temp_run_directory,
)
from peru_conflicts.acquisition.fs_safety import (
    DirectoryLease,
    DirectoryLeaseError,
    deletion_quarantine_name,
)
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableByteObjectV2,
    DurableCleanupV2,
    DurableTemporaryRecoveryV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore


class TemporaryRecoveryError(RuntimeError):
    """Run-owned temporary state is ambiguous, aliased, or contradictory."""


@dataclass(frozen=True, slots=True)
class RecoveredDownload:
    """One complete, rehashed temporary object linked to its durable attempt."""

    attempt_id: str
    downloaded: DownloadedObject


def deterministic_temp_token(
    authorization_id: str,
    *,
    report_number: int,
    attempt_ordinal: int,
) -> str:
    """Return the sole bounded token for one authorization/report/attempt tuple."""

    payload = f"{authorization_id}:{report_number}:{attempt_ordinal}".encode()
    return hashlib.sha256(payload).hexdigest()[:32]


def temporary_object_names(
    authorization_id: str,
    *,
    report_number: int,
    attempt_ordinal: int,
) -> tuple[str, str]:
    """Return deterministic partial and complete object names."""

    token = deterministic_temp_token(
        authorization_id,
        report_number=report_number,
        attempt_ordinal=attempt_ordinal,
    )
    partial = f"report-{report_number}-{token}.pdf.partial"
    return partial, partial.removesuffix(".partial")


def _stable_open_child_fingerprint(
    directory: DirectoryLease,
    name: str,
    source: BinaryIO,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    prefix = bytearray()
    try:
        before = os.fstat(source.fileno())
        while chunk := source.read(64 * 1024):
            byte_count += len(chunk)
            if byte_count > 50_000_000:
                raise TemporaryRecoveryError("recovered object exceeds the PDF ceiling")
            if len(prefix) < 5:
                prefix.extend(chunk[: 5 - len(prefix)])
            digest.update(chunk)
        after = os.fstat(source.fileno())
        current = directory.child_lstat(name)
    except (OSError, DirectoryLeaseError) as error:
        raise TemporaryRecoveryError("temporary object could not be safely rehashed") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or (after.st_dev, after.st_ino, after.st_size)
        != (current.st_dev, current.st_ino, current.st_size)
        or bytes(prefix) != b"%PDF-"
        or byte_count < 1_024
    ):
        raise TemporaryRecoveryError("temporary complete object is not a stable PDF")
    return byte_count, digest.hexdigest()


def _stable_child_fingerprint(
    directory: DirectoryLease,
    name: str,
) -> tuple[int, str]:
    try:
        with directory.open_child_read(name) as source:
            return _stable_open_child_fingerprint(directory, name, source)
    except (OSError, DirectoryLeaseError) as error:
        raise TemporaryRecoveryError("temporary object could not be safely rehashed") from error


@dataclass(slots=True)
class TemporaryRecoveryManager:
    """Reconcile only names derivable from durable PDF attempts in one run directory."""

    system_temp_root: Path
    run_id: str
    authorization_id: str
    ledger: ManifestLedgerStore
    utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def _append_recovery(
        self,
        *,
        start: DurableAttemptStartedV2,
        object_state: str,
        recovery_action: str,
        observed_bytes: int | None = None,
        observed_sha256: str | None = None,
    ) -> None:
        record_id = f"temporary-recovery-{start.attempt_id}-{object_state}-{recovery_action}"
        candidate = DurableTemporaryRecoveryV2.model_validate(
            {
                "schema_version": "0.2.0",
                "record_type": "temporary_recovery",
                "record_id": record_id,
                "authorization_id": self.ledger.authorization_id,
                "run_id": self.ledger.run_id,
                "plan_id": self.ledger.plan_id,
                "sequence": self.ledger.next_sequence,
                "previous_record_sha256": self.ledger.ledger_head_sha256,
                "recorded_at": self.utc_clock(),
                "report_number": start.report_number,
                "attempt_id": start.attempt_id,
                "object_state": object_state,
                "recovery_action": recovery_action,
                "observed_bytes": observed_bytes,
                "observed_sha256": observed_sha256,
            },
            strict=True,
        )
        existing = next(
            (
                record
                for record in self.ledger.records
                if getattr(record, "record_id", None) == record_id
            ),
            None,
        )
        if existing is not None:
            if (
                not isinstance(existing, DurableTemporaryRecoveryV2)
                or existing.report_number != candidate.report_number
                or existing.attempt_id != candidate.attempt_id
                or existing.object_state != candidate.object_state
                or existing.recovery_action != candidate.recovery_action
                or existing.observed_bytes != candidate.observed_bytes
                or existing.observed_sha256 != candidate.observed_sha256
            ):
                raise TemporaryRecoveryError("durable temporary fingerprint differs")
            return
        self.ledger.append(candidate)

    def reconcile(self) -> dict[int, RecoveredDownload]:
        """Remove owned partials and return exact successful complete objects."""

        root = Path(os.path.abspath(self.system_temp_root))
        run_path = root / self.run_id
        if not os.path.lexists(root) or not os.path.lexists(run_path):
            return {}
        starts = {
            record.attempt_id: record
            for record in self.ledger.records
            if isinstance(record, DurableAttemptStartedV2) and record.request_kind == "pdf"
        }
        finishes = {
            record.attempt_id: record
            for record in self.ledger.records
            if isinstance(record, DurableAttemptFinishedV2)
        }
        byte_attempts = {
            record.source_attempt_id
            for record in self.ledger.records
            if isinstance(record, DurableByteObjectV2)
        }
        cleaned_attempts = {
            record.attempt_id
            for record in self.ledger.records
            if isinstance(record, DurableCleanupV2)
        }
        expected: dict[str, tuple[DurableAttemptStartedV2, str]] = {}
        for start in starts.values():
            partial, complete = temporary_object_names(
                self.authorization_id,
                report_number=start.report_number,
                attempt_ordinal=start.attempt_ordinal,
            )
            expected[partial] = (start, "partial")
            expected[complete] = (start, "complete")
            expected[deletion_quarantine_name(complete)] = (start, "quarantine")

        recovered: dict[int, RecoveredDownload] = {}
        try:
            with lease_system_temp_run_directory(
                root,
                self.run_id,
                create=False,
            ) as run_lease:
                names = run_lease.list_child_names()
                unexpected = tuple(name for name in names if name not in expected)
                if unexpected:
                    raise TemporaryRecoveryError(
                        "run directory contains an unexpected temporary object"
                    )
                for start in starts.values():
                    partial, complete = temporary_object_names(
                        self.authorization_id,
                        report_number=start.report_number,
                        attempt_ordinal=start.attempt_ordinal,
                    )
                    present = {
                        candidate
                        for candidate in (
                            partial,
                            complete,
                            deletion_quarantine_name(complete),
                        )
                        if candidate in names
                    }
                    if len(present) > 1:
                        raise TemporaryRecoveryError(
                            "one attempt has conflicting temporary object states"
                        )
                for name in names:
                    start, object_state = expected[name]
                    if start.attempt_id in cleaned_attempts:
                        raise TemporaryRecoveryError(
                            "cleaned attempt unexpectedly retains a temporary object"
                        )
                    if object_state == "partial":
                        run_lease.unlink_child(name)
                        self._append_recovery(
                            start=start,
                            object_state="partial",
                            recovery_action="removed_partial",
                        )
                        continue
                    finish = finishes.get(start.attempt_id)
                    if finish is None or finish.outcome != "success":
                        try:
                            with run_lease.open_child_read_for_delete(name) as source:
                                observed_bytes, observed_sha256 = _stable_open_child_fingerprint(
                                    run_lease,
                                    name,
                                    source,
                                )
                                self._append_recovery(
                                    start=start,
                                    object_state="complete",
                                    recovery_action="observed_unaccepted_complete",
                                    observed_bytes=observed_bytes,
                                    observed_sha256=observed_sha256,
                                )
                                delete_name = name
                                if object_state != "quarantine":
                                    delete_name = deletion_quarantine_name(name)
                                    run_lease.quarantine_open_child(
                                        name,
                                        source,
                                        delete_name,
                                    )
                                run_lease.unlink_open_child(delete_name, source)
                            if run_lease.child_exists(name) or run_lease.child_exists(
                                deletion_quarantine_name(name.removesuffix(".delete"))
                            ):
                                raise TemporaryRecoveryError(
                                    "temporary child identity changed during deletion"
                                )
                        except (OSError, DirectoryLeaseError) as error:
                            raise TemporaryRecoveryError(
                                "temporary object identity-bound deletion failed"
                            ) from error
                        self._append_recovery(
                            start=start,
                            object_state="complete",
                            recovery_action="removed_unaccepted_complete",
                        )
                        continue
                    observed_bytes, observed_sha256 = _stable_child_fingerprint(
                        run_lease,
                        name,
                    )
                    if (
                        finish.accepted_bytes != observed_bytes
                        or finish.body_sha256 != observed_sha256
                    ):
                        raise TemporaryRecoveryError(
                            "complete temporary object fingerprint differs"
                        )
                    if start.report_number in recovered:
                        raise TemporaryRecoveryError(
                            "one report has multiple complete temporary objects"
                        )
                    if start.attempt_id not in byte_attempts:
                        self._append_recovery(
                            start=start,
                            object_state="complete",
                            recovery_action="accepted_complete_for_resume",
                            observed_bytes=observed_bytes,
                            observed_sha256=observed_sha256,
                        )
                    recovered[start.report_number] = RecoveredDownload(
                        attempt_id=start.attempt_id,
                        downloaded=DownloadedObject(
                            path=run_lease.child_path(name),
                            byte_count=observed_bytes,
                            sha256=observed_sha256,
                            final_url=start.normalized_url,
                        ),
                    )
        except (DirectoryLeaseError, TemporaryPathBoundaryError) as error:
            raise TemporaryRecoveryError(
                "run temporary directory could not be identity-bound"
            ) from error
        return recovered
