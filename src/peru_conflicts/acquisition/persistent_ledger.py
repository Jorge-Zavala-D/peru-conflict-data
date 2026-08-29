"""Identity-bound, hash-chained production ledger for future comparison runs."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, suppress
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self

from pydantic import TypeAdapter, ValidationError

from peru_conflicts.acquisition.authorization import compute_leased_data_root_identity_sha256
from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableByteObjectV2,
    DurableCleanupV2,
    DurableComparisonV2,
    DurableIssueV2,
    DurableLandingAssociationV2,
    DurableLedgerRecordV2,
    DurableRunOpenedV2,
    DurableRunTerminalV2,
    DurableSourceRehashV2,
    DurableTemporaryRecoveryV2,
    StorageNamespaceMarkerV2,
    UseIndexClaimV2,
    UseIndexLedgerAnchorV2,
    UseIndexLedgerCreatedV2,
    UseIndexRecordV2,
    UseIndexTerminalV2,
    marker_bytes,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import StrictModel

INDEX_NAME = "authorization-use-index-v2.jsonl"
MARKER_NAME = "m1-03b-namespace-v2.json"
LOCK_NAME = ".m1-03b-v2.lock"
_LEDGER_ADAPTER: TypeAdapter[DurableLedgerRecordV2] = TypeAdapter(DurableLedgerRecordV2)
_INDEX_ADAPTER: TypeAdapter[UseIndexRecordV2] = TypeAdapter(UseIndexRecordV2)
FaultInjector = Callable[[str], None]


class PersistentLedgerError(RuntimeError):
    """Base class for fail-closed operational persistence."""


class LedgerLockUnavailable(PersistentLedgerError):
    """Another process owns the manifest writer lock."""


class LedgerRollbackDetected(PersistentLedgerError):
    """Hash chains or high-water anchors indicate rollback/corruption."""


class MarkerMismatch(PersistentLedgerError):
    """Manifest namespace marker differs from authorization-pinned bytes."""


class AuthorizationSpent(PersistentLedgerError):
    """A terminal one-shot authorization cannot be used again."""


class LedgerRecordConflict(PersistentLedgerError):
    """A record conflicts with deterministic identity or state."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ledger_name(authorization_id: str) -> str:
    digest = _sha256(authorization_id.encode("utf-8"))[:32]
    return f"authorization-{digest}.v2.jsonl"


class _KernelLock:
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream
        self._locked = False

    def acquire(self) -> None:
        descriptor = self._stream.fileno()
        try:
            self._stream.seek(0, os.SEEK_END)
            if self._stream.tell() == 0:
                self._stream.write(b"\0")
                self._stream.flush()
                os.fsync(descriptor)
            self._stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise LedgerLockUnavailable("manifest writer lock is already held") from error
        self._locked = True

    def release(self) -> None:
        if not self._locked:
            return
        self._stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False


class _BoundAppendFile:
    def __init__(self, directory: DirectoryLease, name: str) -> None:
        self.directory = directory
        self.name = name
        existed = directory.child_exists(name)
        self.stream = directory.open_child_append(name)
        try:
            details = os.fstat(self.stream.fileno())
            self.identity = (details.st_dev, details.st_ino)
            self._require_bound()
            if not existed:
                directory.sync_directory()
                self._require_bound()
        except BaseException:
            self.stream.close()
            raise

    @property
    def path(self) -> Path:
        return self.directory.child_path(self.name)

    def _require_bound(self) -> None:
        self.directory.require_bound()
        opened = os.fstat(self.stream.fileno())
        current = self.directory.child_lstat(self.name)
        if (
            not opened.st_nlink == 1
            or (opened.st_dev, opened.st_ino) != self.identity
            or (current.st_dev, current.st_ino) != self.identity
        ):
            raise LedgerRollbackDetected("ledger file identity or link count changed")

    def read_bytes(self) -> bytes:
        self._require_bound()
        self.stream.seek(0)
        content = self.stream.read()
        self.stream.seek(0, os.SEEK_END)
        self._require_bound()
        return content

    def append_fsync(self, line: bytes) -> None:
        self._require_bound()
        self.stream.seek(0, os.SEEK_END)
        written = self.stream.write(line)
        if written != len(line):
            raise PersistentLedgerError("ledger append was incomplete")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self._require_bound()

    def close(self) -> None:
        self.stream.close()


def _canonical_record_line(record: StrictModel) -> bytes:
    payload = record.model_dump(mode="json")
    return canonical_json_bytes(payload) + b"\n"


def _parse_chain[RecordT: StrictModel](
    raw: bytes,
    *,
    adapter: TypeAdapter[RecordT],
    sequence_field: str,
    previous_field: str,
) -> tuple[tuple[RecordT, ...], tuple[str, ...]]:
    if not raw:
        return (), ()
    if not raw.endswith(b"\n"):
        raise LedgerRollbackDetected("JSONL has an incomplete final record")
    records: list[RecordT] = []
    hashes: list[str] = []
    previous: str | None = None
    for expected_sequence, line_with_lf in enumerate(raw.splitlines(keepends=True), start=1):
        line = line_with_lf[:-1]
        if not line:
            raise LedgerRollbackDetected("JSONL contains an empty record")
        try:
            record = adapter.validate_json(line)
        except ValidationError as error:
            raise LedgerRollbackDetected("JSONL record is structurally invalid") from error
        if _canonical_record_line(record) != line_with_lf:
            raise LedgerRollbackDetected("JSONL record is not canonical")
        if getattr(record, sequence_field) != expected_sequence:
            raise LedgerRollbackDetected("JSONL sequence is not contiguous")
        if getattr(record, previous_field) != previous:
            raise LedgerRollbackDetected("JSONL previous-record hash is inconsistent")
        previous = _sha256(line)
        records.append(record)
        hashes.append(previous)
    return tuple(records), tuple(hashes)


def validate_durable_ledger_graph(records: Sequence[DurableLedgerRecordV2]) -> None:
    """Validate deterministic identities, references, and terminal truth."""

    if not records:
        return
    record_ids = tuple(getattr(record, "record_id", None) for record in records)
    if None in record_ids or len(set(record_ids)) != len(record_ids):
        raise LedgerRecordConflict("ledger record IDs must be globally unique")
    opened = tuple(record for record in records if isinstance(record, DurableRunOpenedV2))
    if len(opened) != 1 or records[0] is not opened[0] or opened[0].record_id != "run-opened":
        raise LedgerRecordConflict("ledger requires one deterministic run-opened origin")

    starts: dict[str, DurableAttemptStartedV2] = {}
    finishes: dict[str, DurableAttemptFinishedV2] = {}
    continued_attempts: set[str] = set()
    for record in records:
        if isinstance(record, DurableAttemptStartedV2):
            expected_attempt = f"attempt-{record.attempt_ordinal:04d}"
            if (
                record.attempt_id != expected_attempt
                or record.record_id != f"{expected_attempt}-start"
                or record.attempt_id in starts
            ):
                raise LedgerRecordConflict("attempt start has a noncanonical logical identity")
            if record.continued_from_attempt_id is not None:
                prior_start = starts.get(record.continued_from_attempt_id)
                prior_finish = finishes.get(record.continued_from_attempt_id)
                expected_outcome = (
                    "redirect" if record.continuation_reason == "redirect" else "retryable_failure"
                )
                if (
                    prior_start is None
                    or prior_finish is None
                    or prior_finish.outcome != expected_outcome
                    or prior_start.report_number != record.report_number
                    or prior_start.request_kind != record.request_kind
                    or record.continued_from_attempt_id in continued_attempts
                ):
                    raise LedgerRecordConflict(
                        "attempt continuation lacks one matching prior outcome"
                    )
                continued_attempts.add(record.continued_from_attempt_id)
            starts[record.attempt_id] = record
        elif isinstance(record, DurableAttemptFinishedV2):
            start = starts.get(record.attempt_id)
            if start is None:
                raise LedgerRecordConflict("attempt finish has no prior attempt start")
            if (
                record.record_id != f"{record.attempt_id}-finish"
                or record.attempt_ordinal != start.attempt_ordinal
                or record.attempt_id in finishes
            ):
                raise LedgerRecordConflict("attempt finish has a conflicting logical identity")
            finishes[record.attempt_id] = record

    byte_by_report: dict[int, DurableByteObjectV2] = {}
    comparison_by_report: dict[int, DurableComparisonV2] = {}
    recovery_actions: dict[tuple[str, str], set[str]] = {}
    for record in records:
        if isinstance(record, DurableLandingAssociationV2):
            start = starts.get(record.landing_attempt_id)
            finish = finishes.get(record.landing_attempt_id)
            if (
                record.record_id != f"landing-association-{record.report_number}"
                or start is None
                or finish is None
                or start.report_number != record.report_number
                or start.request_kind != "landing_html"
                or finish.outcome != "success"
                or finish.body_sha256 != record.landing_body_sha256
                or finish.accepted_bytes != record.landing_body_bytes
            ):
                raise LedgerRecordConflict(
                    "landing association lacks one successful source attempt"
                )
        elif isinstance(record, DurableByteObjectV2):
            start = starts.get(record.source_attempt_id)
            finish = finishes.get(record.source_attempt_id)
            if (
                record.record_id != f"byte-object-{record.report_number}-{record.observed_sha256}"
                or record.report_number in byte_by_report
                or start is None
                or finish is None
                or start.report_number != record.report_number
                or start.request_kind != "pdf"
                or finish.outcome != "success"
                or finish.body_sha256 != record.observed_sha256
                or finish.accepted_bytes != record.observed_bytes
            ):
                raise LedgerRecordConflict("byte object lacks one accepted PDF attempt")
            byte_by_report[record.report_number] = record
        elif isinstance(record, DurableComparisonV2):
            byte_object = byte_by_report.get(record.report_number)
            if (
                record.record_id != f"comparison-{record.report_number}"
                or record.report_number in comparison_by_report
                or byte_object is None
                or record.source_attempt_id != byte_object.source_attempt_id
                or record.observed_sha256 != byte_object.observed_sha256
                or record.observed_bytes != byte_object.observed_bytes
            ):
                raise LedgerRecordConflict("comparison does not bind one prior byte object")
            comparison_by_report[record.report_number] = record
        elif isinstance(record, DurableCleanupV2):
            byte_object = byte_by_report.get(record.report_number)
            if (
                record.record_id != f"cleanup-{record.report_number}"
                or byte_object is None
                or record.attempt_id != byte_object.source_attempt_id
            ):
                raise LedgerRecordConflict("cleanup does not bind one prior byte object")
        elif isinstance(record, DurableSourceRehashV2):
            if record.record_id != f"source-rehash-{record.phase}-{record.report_number}":
                raise LedgerRecordConflict("source rehash has a noncanonical logical identity")
        elif isinstance(record, DurableTemporaryRecoveryV2):
            start = starts.get(record.attempt_id)
            if (
                record.record_id
                != (
                    f"temporary-recovery-{record.attempt_id}-{record.object_state}-"
                    f"{record.recovery_action}"
                )
                or start is None
                or start.request_kind != "pdf"
                or start.report_number != record.report_number
            ):
                raise LedgerRecordConflict("temporary recovery does not bind one prior PDF attempt")
            key = (record.attempt_id, record.object_state)
            prior_actions = recovery_actions.setdefault(key, set())
            if record.recovery_action in prior_actions:
                raise LedgerRecordConflict("temporary recovery action is duplicated")
            if (
                record.recovery_action == "removed_unaccepted_complete"
                and "observed_unaccepted_complete" not in prior_actions
            ):
                raise LedgerRecordConflict(
                    "unaccepted complete cleanup lacks a prior durable fingerprint"
                )
            if record.recovery_action == "accepted_complete_for_resume" and prior_actions:
                raise LedgerRecordConflict("accepted complete recovery conflicts with cleanup")
            if (
                record.recovery_action
                in {
                    "observed_unaccepted_complete",
                    "removed_unaccepted_complete",
                }
                and "accepted_complete_for_resume" in prior_actions
            ):
                raise LedgerRecordConflict("complete cleanup conflicts with accepted recovery")
            prior_actions.add(record.recovery_action)

    terminals = tuple(record for record in records if isinstance(record, DurableRunTerminalV2))
    if len(terminals) > 1 or (terminals and records[-1] is not terminals[0]):
        raise LedgerRecordConflict("ledger terminal must be unique and final")
    unfinished_attempts = tuple(sorted(set(starts).difference(finishes)))
    if terminals and unfinished_attempts:
        raise LedgerRecordConflict("ledger terminal cannot coexist with an unfinished attempt")
    if not terminals:
        return
    terminal = terminals[0]
    if terminal.record_id != "run-terminal":
        raise LedgerRecordConflict("run terminal has a noncanonical logical identity")
    issues = tuple(record for record in records if isinstance(record, DurableIssueV2))
    issues_by_id = {record.record_id: record for record in issues}
    for attempt_id, finish in finishes.items():
        if finish.outcome != "crash_outcome_unknown":
            continue
        issue = issues_by_id.get(f"issue-crash-outcome-unknown-{attempt_id}")
        start = starts[attempt_id]
        if (
            issue is None
            or issue.classification != "MISSING_EVIDENCE"
            or issue.reason_code != "attempt_outcome_unknown_after_process_crash"
            or issue.report_number != start.report_number
        ):
            raise LedgerRecordConflict(
                "unknown crash terminal lacks matching MISSING_EVIDENCE issue"
            )
    collisions = tuple(
        record
        for record in records
        if isinstance(record, DurableComparisonV2) and record.disposition == "stop_for_review"
    )
    scientific_issue = any(
        record.classification
        in {"PARSER_ERROR", "MISSING_EVIDENCE", "AMBIGUITY", "SOURCE_INCONSISTENCY"}
        for record in issues
    )
    if collisions or scientific_issue:
        if terminal.terminal_status != "stop_for_review":
            raise LedgerRecordConflict("collision or scientific issue must stop for review")
    elif terminal.terminal_status == "stop_for_review":
        raise LedgerRecordConflict("stop-for-review terminal lacks classified evidence")
    if terminal.terminal_status == "abandoned":
        if not any(
            record.classification in {"POLICY_VIOLATION", "INFRASTRUCTURE_FAILURE"}
            for record in issues
        ):
            raise LedgerRecordConflict("abandoned terminal lacks operational issue evidence")
        return
    if terminal.terminal_status != "completed":
        return

    expected = tuple(range(260, 270))
    landings = tuple(
        record.report_number
        for record in records
        if isinstance(record, DurableLandingAssociationV2)
    )
    byte_objects = tuple(
        record.report_number for record in records if isinstance(record, DurableByteObjectV2)
    )
    comparisons = tuple(record for record in records if isinstance(record, DurableComparisonV2))
    cleanups = tuple(
        record.report_number for record in records if isinstance(record, DurableCleanupV2)
    )
    unresolved_issues = tuple(
        record
        for record in issues
        if not (
            record.classification == "INFRASTRUCTURE_FAILURE"
            and record.reason_code == "temporary_cleanup_pending"
            and record.report_number in cleanups
        )
    )
    source_rehashes = tuple(
        record for record in records if isinstance(record, DurableSourceRehashV2)
    )
    rehash_reports_by_phase = {
        phase: tuple(record.report_number for record in source_rehashes if record.phase == phase)
        for phase in ("pre_network", "comparison_before", "comparison_after", "terminal")
    }
    if (
        landings != expected
        or byte_objects != expected
        or tuple(record.report_number for record in comparisons) != expected
        or any(
            record.relationship != "identical_bytes"
            or record.disposition != "identical_no_duplicate"
            for record in comparisons
        )
        or cleanups != expected
        or any(reports != expected for reports in rehash_reports_by_phase.values())
        or any(record.observed_sha256 != record.expected_sha256 for record in source_rehashes)
        or unresolved_issues
    ):
        raise LedgerRecordConflict("completed terminal lacks the exact clean ten-report graph")


class ManifestLedgerStore(AbstractContextManager["ManifestLedgerStore"]):
    """Narrow writer for marker, use index, and one deterministic authorization ledger."""

    def __init__(self) -> None:
        self._root_lease: DirectoryLease | None = None
        self._raw_lease: DirectoryLease | None = None
        self._manifest_lease: DirectoryLease | None = None
        self._lock_file: _BoundAppendFile | None = None
        self._lock: _KernelLock | None = None
        self._index_file: _BoundAppendFile | None = None
        self._ledger_file: _BoundAppendFile | None = None
        self._index_records: tuple[UseIndexRecordV2, ...] = ()
        self._index_hashes: tuple[str, ...] = ()
        self._records: tuple[DurableLedgerRecordV2, ...] = ()
        self._record_hashes: tuple[str, ...] = ()
        self._authorization_id = ""
        self._run_id = ""
        self._plan_id = ""
        self._ledger_name = ""
        self._fault_injector: FaultInjector | None = None
        self.data_root_identity_sha256 = ""
        self._closed = False

    @classmethod
    def open(
        cls,
        *,
        data_root: Path,
        marker: StorageNamespaceMarkerV2,
        expected_data_root_identity_sha256: str,
        execution_host_identity_sha256: str,
        expected_execution_tree_sha256: str,
        expected_authorization_artifact_sha256: str,
        authorization_id: str,
        run_id: str,
        plan_id: str,
        recorded_at: datetime,
        fault_injector: FaultInjector | None = None,
    ) -> Self:
        store = cls()
        try:
            store._initialize(
                data_root=data_root,
                marker=marker,
                expected_data_root_identity_sha256=expected_data_root_identity_sha256,
                execution_host_identity_sha256=execution_host_identity_sha256,
                expected_execution_tree_sha256=expected_execution_tree_sha256,
                expected_authorization_artifact_sha256=expected_authorization_artifact_sha256,
                authorization_id=authorization_id,
                run_id=run_id,
                plan_id=plan_id,
                recorded_at=recorded_at,
                fault_injector=fault_injector,
            )
            return store
        except BaseException:
            store.close()
            raise

    def _initialize(
        self,
        *,
        data_root: Path,
        marker: StorageNamespaceMarkerV2,
        expected_data_root_identity_sha256: str,
        execution_host_identity_sha256: str,
        expected_execution_tree_sha256: str,
        expected_authorization_artifact_sha256: str,
        authorization_id: str,
        run_id: str,
        plan_id: str,
        recorded_at: datetime,
        fault_injector: FaultInjector | None,
    ) -> None:
        self._root_lease = DirectoryLease.acquire(data_root)
        observed_identity = compute_leased_data_root_identity_sha256(
            self._root_lease,
            marker_nonce_sha256=marker.owner_nonce_sha256,
            execution_host_identity_sha256=execution_host_identity_sha256,
        )
        if observed_identity != expected_data_root_identity_sha256:
            raise MarkerMismatch("data-root identity differs from owner authorization")
        self.data_root_identity_sha256 = observed_identity
        self._authorization_id = authorization_id
        self._run_id = run_id
        self._plan_id = plan_id
        self.authorization_artifact_sha256 = expected_authorization_artifact_sha256
        self._ledger_name = _ledger_name(authorization_id)
        self._fault_injector = fault_injector

        self._raw_lease = self._root_lease.acquire_child("01_raw")
        self._manifest_lease = self._raw_lease.acquire_child("manifests")
        self._lock_file = _BoundAppendFile(self._manifest_lease, LOCK_NAME)
        self._lock = _KernelLock(self._lock_file.stream)
        self._lock.acquire()
        self._ensure_marker(marker)

        self._index_file = _BoundAppendFile(self._manifest_lease, INDEX_NAME)
        index_records, index_hashes = _parse_chain(
            self._index_file.read_bytes(),
            adapter=_INDEX_ADAPTER,
            sequence_field="index_sequence",
            previous_field="previous_index_sha256",
        )
        self._index_records = index_records
        self._index_hashes = index_hashes
        self._ensure_claim_and_ledger(
            marker=marker,
            execution_host_identity_sha256=execution_host_identity_sha256,
            authorization_artifact_sha256=expected_authorization_artifact_sha256,
            recorded_at=recorded_at,
        )
        if self._records:
            opened = self._records[0]
            if not isinstance(opened, DurableRunOpenedV2) or (
                opened.execution_tree_sha256 != expected_execution_tree_sha256
                or opened.authorization_artifact_sha256 != expected_authorization_artifact_sha256
                or opened.data_root_identity_sha256 != self.data_root_identity_sha256
                or opened.execution_host_identity_sha256 != execution_host_identity_sha256
            ):
                raise LedgerRollbackDetected("run-opened execution identity differs")

    def _ensure_marker(self, marker: StorageNamespaceMarkerV2) -> None:
        assert self._manifest_lease is not None
        expected = marker_bytes(marker)
        if self._manifest_lease.child_exists(MARKER_NAME):
            with self._manifest_lease.open_child_read(MARKER_NAME) as source:
                observed = source.read()
            if observed != expected:
                raise MarkerMismatch("manifest namespace marker bytes differ")
            return
        try:
            with self._manifest_lease.open_child_exclusive(MARKER_NAME) as destination:
                destination.write(expected)
                destination.flush()
                os.fsync(destination.fileno())
            self._manifest_lease.sync_directory()
        except FileExistsError:
            with self._manifest_lease.open_child_read(MARKER_NAME) as source:
                observed = source.read()
            if observed != expected:
                raise MarkerMismatch("racing namespace marker differs") from None
        self._inject("after_marker_fsync_before_claim")

    def _next_index_coordinates(self) -> tuple[int, str | None]:
        sequence = len(self._index_records) + 1
        previous = self._index_hashes[-1] if self._index_hashes else None
        return sequence, previous

    def _append_index(self, record: UseIndexRecordV2) -> None:
        assert self._index_file is not None
        line = _canonical_record_line(record)
        self._index_file.append_fsync(line)
        self._index_records = (*self._index_records, record)
        self._index_hashes = (*self._index_hashes, _sha256(line[:-1]))

    def _ensure_claim_and_ledger(
        self,
        *,
        marker: StorageNamespaceMarkerV2,
        execution_host_identity_sha256: str,
        authorization_artifact_sha256: str,
        recorded_at: datetime,
    ) -> None:
        assert self._manifest_lease is not None
        marker_sha = _sha256(marker_bytes(marker))
        claims = tuple(
            record
            for record in self._index_records
            if isinstance(record, UseIndexClaimV2)
            and record.authorization_id == self._authorization_id
        )
        if len(claims) > 1:
            raise LedgerRollbackDetected("authorization has multiple global claims")
        if not claims:
            sequence, previous = self._next_index_coordinates()
            claim = UseIndexClaimV2(
                schema_version="0.2.0",
                record_type="authorization_claim",
                index_sequence=sequence,
                previous_index_sha256=previous,
                authorization_id=self._authorization_id,
                run_id=self._run_id,
                plan_id=self._plan_id,
                authorization_artifact_sha256=authorization_artifact_sha256,
                storage_namespace_marker_sha256=marker_sha,
                data_root_identity_sha256=self.data_root_identity_sha256,
                execution_host_identity_sha256=execution_host_identity_sha256,
                recorded_at=recorded_at,
            )
            self._append_index(claim)
            claims = (claim,)
        claim = claims[0]
        if (
            claim.run_id != self._run_id
            or claim.plan_id != self._plan_id
            or claim.authorization_artifact_sha256 != authorization_artifact_sha256
            or claim.storage_namespace_marker_sha256 != marker_sha
            or claim.data_root_identity_sha256 != self.data_root_identity_sha256
            or claim.execution_host_identity_sha256 != execution_host_identity_sha256
        ):
            raise LedgerRollbackDetected("authorization claim identity is contradictory")

        relevant = tuple(
            record
            for record in self._index_records
            if getattr(record, "authorization_id", None) == self._authorization_id
            and getattr(record, "run_id", None) == self._run_id
        )
        created = tuple(
            record for record in relevant if isinstance(record, UseIndexLedgerCreatedV2)
        )
        if len(created) > 1:
            raise LedgerRollbackDetected("authorization has multiple ledger-created records")
        ledger_exists = self._manifest_lease.child_exists(self._ledger_name)
        if created and (created[0].ledger_name != self._ledger_name or not ledger_exists):
            raise LedgerRollbackDetected("use index and deterministic ledger disagree")
        if not created and ledger_exists:
            with self._manifest_lease.open_child_read(self._ledger_name) as source:
                if source.read():
                    raise LedgerRollbackDetected("unclaimed deterministic ledger contains bytes")
        self._ledger_file = _BoundAppendFile(self._manifest_lease, self._ledger_name)
        if not created:
            sequence, previous = self._next_index_coordinates()
            ledger_created = UseIndexLedgerCreatedV2(
                schema_version="0.2.0",
                record_type="ledger_created",
                index_sequence=sequence,
                previous_index_sha256=previous,
                authorization_id=self._authorization_id,
                run_id=self._run_id,
                ledger_name=self._ledger_name,
                recorded_at=recorded_at,
            )
            self._inject("after_claim_before_ledger_created")
            self._append_index(ledger_created)
        records, hashes = _parse_chain(
            self._ledger_file.read_bytes(),
            adapter=_LEDGER_ADAPTER,
            sequence_field="sequence",
            previous_field="previous_record_sha256",
        )
        self._records = records
        self._record_hashes = hashes
        self._validate_ledger_identity_and_anchors()
        self._validate_terminal_index()

    def _validate_ledger_identity_and_anchors(self) -> None:
        validate_durable_ledger_graph(self._records)
        for record in self._records:
            if (
                record.authorization_id != self._authorization_id
                or record.run_id != self._run_id
                or record.plan_id != self._plan_id
            ):
                raise LedgerRollbackDetected("ledger record belongs to another run")
        anchors = tuple(
            record
            for record in self._index_records
            if isinstance(record, UseIndexLedgerAnchorV2)
            and record.authorization_id == self._authorization_id
            and record.run_id == self._run_id
        )
        if len(anchors) != len(self._records):
            raise LedgerRollbackDetected("ledger and use-index high-water counts differ")
        for sequence, (anchor, record_hash) in enumerate(
            zip(anchors, self._record_hashes, strict=True), start=1
        ):
            if anchor.ledger_sequence != sequence or anchor.ledger_head_sha256 != record_hash:
                raise LedgerRollbackDetected("ledger and use-index high-water hashes differ")

    def _validate_terminal_index(self) -> None:
        ledger_terminals = tuple(
            record for record in self._records if isinstance(record, DurableRunTerminalV2)
        )
        index_terminals = tuple(
            record
            for record in self._index_records
            if isinstance(record, UseIndexTerminalV2)
            and record.authorization_id == self._authorization_id
            and record.run_id == self._run_id
        )
        if len(ledger_terminals) != len(index_terminals) or len(ledger_terminals) > 1:
            raise LedgerRollbackDetected("ledger and use index terminal states differ")
        if not ledger_terminals:
            return
        ledger_terminal = ledger_terminals[0]
        index_terminal = index_terminals[0]
        if (
            index_terminal.terminal_status != ledger_terminal.terminal_status
            or index_terminal.ledger_sequence != ledger_terminal.sequence
            or index_terminal.ledger_head_sha256 != self._record_hashes[-1]
        ):
            raise LedgerRollbackDetected("terminal index does not bind the ledger terminal")
        raise AuthorizationSpent("authorization already has a terminal state")

    def _inject(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)

    @property
    def records(self) -> tuple[DurableLedgerRecordV2, ...]:
        return self._records

    @property
    def authorization_id(self) -> str:
        return self._authorization_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def plan_id(self) -> str:
        return self._plan_id

    @property
    def next_sequence(self) -> int:
        return len(self._records) + 1

    @property
    def ledger_head_sha256(self) -> str | None:
        return self._record_hashes[-1] if self._record_hashes else None

    @property
    def marker_path(self) -> Path:
        assert self._manifest_lease is not None
        return self._manifest_lease.child_path(MARKER_NAME)

    @property
    def index_path(self) -> Path:
        assert self._manifest_lease is not None
        return self._manifest_lease.child_path(INDEX_NAME)

    @property
    def ledger_path(self) -> Path:
        assert self._manifest_lease is not None
        return self._manifest_lease.child_path(self._ledger_name)

    @property
    def consumed_attempts(self) -> int:
        return sum(isinstance(record, DurableAttemptStartedV2) for record in self._records)

    @property
    def reserved_bytes(self) -> int:
        starts = {
            record.attempt_id: record.reserved_bytes
            for record in self._records
            if isinstance(record, DurableAttemptStartedV2)
        }
        for record in self._records:
            if isinstance(record, DurableAttemptFinishedV2) and record.attempt_id in starts:
                if record.outcome == "crash_outcome_unknown":
                    continue
                assert record.accepted_bytes is not None
                starts[record.attempt_id] = record.accepted_bytes
        return sum(starts.values())

    def append(self, record: DurableLedgerRecordV2) -> bool:
        """Append/fsync one record and its index anchor before exposing new state."""

        if self._closed:
            raise PersistentLedgerError("ledger store is closed")
        assert self._ledger_file is not None
        validated = _LEDGER_ADAPTER.validate_python(record)
        if (
            validated.authorization_id != self._authorization_id
            or validated.run_id != self._run_id
            or validated.plan_id != self._plan_id
        ):
            raise LedgerRecordConflict("record identity differs from the bound run")
        line = _canonical_record_line(validated)
        for existing in self._records:
            if existing.record_id == validated.record_id:
                if _canonical_record_line(existing) == line:
                    return False
                raise LedgerRecordConflict("record ID identifies different bytes")
        if validated.sequence != self.next_sequence:
            raise LedgerRecordConflict("record sequence is not the next durable sequence")
        if validated.previous_record_sha256 != self.ledger_head_sha256:
            raise LedgerRecordConflict("record previous hash differs from the durable head")
        if isinstance(validated, DurableAttemptStartedV2):
            if validated.attempt_ordinal != self.consumed_attempts + 1:
                raise LedgerRecordConflict("attempt ordinal is not globally contiguous")
            if self.consumed_attempts >= 60:
                raise LedgerRecordConflict("global attempt budget is exhausted")
            if self.reserved_bytes + validated.reserved_bytes > 500_000_000:
                raise LedgerRecordConflict("global byte reservation budget is exhausted")
        if self._records and isinstance(self._records[-1], DurableRunTerminalV2):
            raise AuthorizationSpent("no record may follow a terminal state")
        validate_durable_ledger_graph((*self._records, validated))
        self._ledger_file.append_fsync(line)
        record_hash = _sha256(line[:-1])
        self._inject("after_ledger_fsync_before_anchor")
        sequence, previous = self._next_index_coordinates()
        anchor = UseIndexLedgerAnchorV2(
            schema_version="0.2.0",
            record_type="ledger_anchor",
            index_sequence=sequence,
            previous_index_sha256=previous,
            authorization_id=self._authorization_id,
            run_id=self._run_id,
            ledger_sequence=validated.sequence,
            ledger_head_sha256=record_hash,
            recorded_at=validated.recorded_at,
        )
        self._append_index(anchor)
        self._records = (*self._records, validated)
        self._record_hashes = (*self._record_hashes, record_hash)
        if isinstance(validated, DurableRunTerminalV2):
            self._inject("after_terminal_anchor_before_terminal_index")
            index_sequence, index_previous = self._next_index_coordinates()
            terminal = UseIndexTerminalV2(
                schema_version="0.2.0",
                record_type="authorization_terminal",
                index_sequence=index_sequence,
                previous_index_sha256=index_previous,
                authorization_id=self._authorization_id,
                run_id=self._run_id,
                terminal_status=validated.terminal_status,
                ledger_sequence=validated.sequence,
                ledger_head_sha256=record_hash,
                recorded_at=validated.recorded_at,
            )
            self._append_index(terminal)
        return True

    def reconcile_unfinished_attempts(self, *, recorded_at: datetime) -> tuple[str, ...]:
        """Persist unknown crash-window outcomes without refunding reservations."""

        starts = {
            record.attempt_id: record
            for record in self._records
            if isinstance(record, DurableAttemptStartedV2)
        }
        finishes = {
            record.attempt_id: record
            for record in self._records
            if isinstance(record, DurableAttemptFinishedV2)
        }
        unfinished = tuple(
            sorted(
                (start for attempt_id, start in starts.items() if attempt_id not in finishes),
                key=lambda record: record.attempt_ordinal,
            )
        )
        for start in unfinished:
            finish = DurableAttemptFinishedV2(
                schema_version="0.2.0",
                record_type="attempt_finished",
                record_id=f"{start.attempt_id}-finish",
                authorization_id=self.authorization_id,
                run_id=self.run_id,
                plan_id=self.plan_id,
                sequence=self.next_sequence,
                previous_record_sha256=self.ledger_head_sha256,
                recorded_at=recorded_at,
                attempt_id=start.attempt_id,
                attempt_ordinal=start.attempt_ordinal,
                outcome="crash_outcome_unknown",
                status_code=None,
                accepted_bytes=None,
                body_sha256=None,
                error_code="process_crash_outcome_unknown",
                response_headers=None,
            )
            self.append(finish)
            finishes[start.attempt_id] = finish

        crash_attempts = tuple(
            sorted(
                (
                    starts[attempt_id]
                    for attempt_id, finish in finishes.items()
                    if finish.outcome == "crash_outcome_unknown"
                ),
                key=lambda record: record.attempt_ordinal,
            )
        )
        issue_ids = {
            record.record_id for record in self._records if isinstance(record, DurableIssueV2)
        }
        for start in crash_attempts:
            issue_id = f"issue-crash-outcome-unknown-{start.attempt_id}"
            if issue_id in issue_ids:
                continue
            self.append(
                DurableIssueV2(
                    schema_version="0.2.0",
                    record_type="issue",
                    record_id=issue_id,
                    authorization_id=self.authorization_id,
                    run_id=self.run_id,
                    plan_id=self.plan_id,
                    sequence=self.next_sequence,
                    previous_record_sha256=self.ledger_head_sha256,
                    recorded_at=recorded_at,
                    report_number=start.report_number,
                    classification="MISSING_EVIDENCE",
                    reason_code="attempt_outcome_unknown_after_process_crash",
                )
            )
            issue_ids.add(issue_id)
        return tuple(start.attempt_id for start in crash_attempts)

    def __enter__(self) -> Self:
        if self._closed:
            raise PersistentLedgerError("ledger store is closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._lock is not None:
            self._lock.release()
        for bound_file in (self._ledger_file, self._index_file, self._lock_file):
            if bound_file is not None:
                bound_file.close()
        for lease in (self._manifest_lease, self._raw_lease, self._root_lease):
            if lease is not None:
                with suppress(DirectoryLeaseError):
                    lease.close()
