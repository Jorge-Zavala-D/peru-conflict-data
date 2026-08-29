"""Durable hash-chained operational ledger tested only in synthetic roots."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.authorization import compute_data_root_identity_sha256
from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableIssueV2,
    DurableRunOpenedV2,
    DurableRunTerminalV2,
    StorageNamespaceMarkerV2,
    marker_bytes,
)
from peru_conflicts.acquisition.persistent_ledger import (
    AuthorizationSpent,
    FaultInjector,
    LedgerLockUnavailable,
    LedgerRecordConflict,
    LedgerRollbackDetected,
    ManifestLedgerStore,
    MarkerMismatch,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64
NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "01_raw" / "manifests").mkdir(parents=True)
    return root


def _marker() -> StorageNamespaceMarkerV2:
    return StorageNamespaceMarkerV2(
        schema_version="0.2.0",
        namespace_id="m1-03b-pilot",
        owner_nonce_sha256=SHA,
    )


def _open(
    root: Path,
    *,
    fault_injector: FaultInjector | None = None,
    authorization_artifact_sha256: str = SHA,
) -> ManifestLedgerStore:
    identity = compute_data_root_identity_sha256(
        root,
        marker_nonce_sha256=SHA,
        execution_host_identity_sha256=OTHER_SHA,
    )
    return ManifestLedgerStore.open(
        data_root=root,
        marker=_marker(),
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=OTHER_SHA,
        expected_execution_tree_sha256=SHA,
        expected_authorization_artifact_sha256=authorization_artifact_sha256,
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        recorded_at=NOW,
        fault_injector=fault_injector,
    )


def _opened(store: ManifestLedgerStore) -> DurableRunOpenedV2:
    return DurableRunOpenedV2(
        schema_version="0.2.0",
        record_type="run_opened",
        record_id="run-opened",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=store.next_sequence,
        previous_record_sha256=store.ledger_head_sha256,
        recorded_at=NOW,
        authorization_artifact_sha256=SHA,
        execution_tree_sha256=SHA,
        data_root_identity_sha256=store.data_root_identity_sha256,
        execution_host_identity_sha256=OTHER_SHA,
    )


def _attempt(store: ManifestLedgerStore, ordinal: int = 1) -> DurableAttemptStartedV2:
    attempt_id = f"attempt-{ordinal:04d}"
    return DurableAttemptStartedV2(
        schema_version="0.2.0",
        record_type="attempt_started",
        record_id=f"{attempt_id}-start",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=store.next_sequence,
        previous_record_sha256=store.ledger_head_sha256,
        recorded_at=NOW,
        attempt_id=attempt_id,
        attempt_ordinal=ordinal,
        report_number=260,
        request_kind="pdf",
        source_url_sha256=SHA,
        normalized_url="https://www.defensoria.gob.pe/file.pdf",
        wire_target="/file.pdf",
        reserved_bytes=50_000_000,
    )


def _infrastructure_issue(store: ManifestLedgerStore) -> DurableIssueV2:
    return DurableIssueV2(
        schema_version="0.2.0",
        record_type="issue",
        record_id="issue-infrastructure_failure-synthetic-run",
        authorization_id="authorization-1",
        run_id="run-1",
        plan_id="plan-1",
        sequence=store.next_sequence,
        previous_record_sha256=store.ledger_head_sha256,
        recorded_at=NOW,
        report_number=None,
        classification="INFRASTRUCTURE_FAILURE",
        reason_code="synthetic_failure",
        evidence_sha256=None,
    )


def test_marker_claim_ledger_and_every_high_water_anchor_are_durable(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        assert store.marker_path.read_bytes() == marker_bytes(_marker())
        store.append(_opened(store))
        store.append(_attempt(store))
        ledger_bytes = store.ledger_path.read_bytes()
        index_bytes = store.index_path.read_bytes()
        assert ledger_bytes.endswith(b"\n")
        assert index_bytes.endswith(b"\n")
        assert store.next_sequence == 3
        assert store.consumed_attempts == 1
        assert store.reserved_bytes == 50_000_000

    with _open(root) as resumed:
        assert len(resumed.records) == 2
        assert resumed.consumed_attempts == 1
        assert resumed.reserved_bytes == 50_000_000


def test_each_new_manifest_append_file_syncs_its_directory_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    calls: list[Path] = []
    original = DirectoryLease.sync_directory

    def recording_sync(lease: DirectoryLease) -> None:
        calls.append(lease.path)
        original(lease)

    monkeypatch.setattr(DirectoryLease, "sync_directory", recording_sync)
    with _open(root):
        pass

    manifest = root / "01_raw" / "manifests"
    assert calls.count(manifest) >= 4  # marker, lock, use index, authorization ledger


def test_complete_ledger_line_removal_or_index_anchor_rollback_is_detected(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_attempt(store))
        ledger_path = store.ledger_path
        index_path = store.index_path

    ledger_lines = ledger_path.read_bytes().splitlines(keepends=True)
    ledger_path.write_bytes(b"".join(ledger_lines[:-1]))
    with pytest.raises(LedgerRollbackDetected):
        _open(root)

    root = _root(tmp_path / "second")
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_attempt(store))
        index_path = store.index_path
    index_lines = index_path.read_bytes().splitlines(keepends=True)
    index_path.write_bytes(b"".join(index_lines[:-1]))
    with pytest.raises(LedgerRollbackDetected):
        _open(root)


def test_crash_between_ledger_fsync_and_anchor_is_non_resumable(tmp_path: Path) -> None:
    root = _root(tmp_path)

    def fail(stage: str) -> None:
        if stage == "after_ledger_fsync_before_anchor":
            raise RuntimeError("synthetic crash")

    store = _open(root, fault_injector=fail)
    with store, pytest.raises(RuntimeError, match="synthetic crash"):
        store.append(_opened(store))
    with pytest.raises(LedgerRollbackDetected):
        _open(root)


def test_marker_conflict_fails_before_claim_or_ledger_creation(tmp_path: Path) -> None:
    root = _root(tmp_path)
    marker_path = root / "01_raw" / "manifests" / "m1-03b-namespace-v2.json"
    marker_path.write_bytes(b"conflicting marker\n")

    with pytest.raises(MarkerMismatch):
        _open(root)
    assert not (root / "01_raw" / "manifests" / "authorization-use-index-v2.jsonl").exists()


def test_kernel_lock_rejects_concurrent_writer_and_releases_after_close(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _open(root)
    try:
        with pytest.raises(LedgerLockUnavailable):
            _open(root)
    finally:
        first.close()
    with _open(root) as reopened:
        assert reopened.records == ()


def test_deterministic_ledger_name_does_not_expose_authorization_text(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        expected_fragment = hashlib.sha256(b"authorization-1").hexdigest()[:32]
        assert expected_fragment in store.ledger_path.name
        assert "authorization-1" not in store.ledger_path.name


def test_logical_event_ids_and_references_are_validated_before_append(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        wrong_open = _opened(store).model_copy(update={"record_id": "alternate-open"})
        with pytest.raises(LedgerRecordConflict, match="run-opened"):
            store.append(wrong_open)

        store.append(_opened(store))
        orphan_finish = DurableAttemptFinishedV2(
            schema_version="0.2.0",
            record_type="attempt_finished",
            record_id="attempt-0001-finish",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            attempt_id="attempt-0001",
            attempt_ordinal=1,
            outcome="retryable_failure",
            status_code=None,
            accepted_bytes=0,
            body_sha256=None,
            error_code="transport_OSError",
            response_headers=None,
        )
        with pytest.raises(LedgerRecordConflict, match="attempt start"):
            store.append(orphan_finish)


def test_incomplete_graph_cannot_claim_completed_terminal(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_infrastructure_issue(store))
        terminal = DurableRunTerminalV2(
            schema_version="0.2.0",
            record_type="run_terminal",
            record_id="run-terminal",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            terminal_status="completed",
            reason_code="all_ten_remote_bytes_identical",
        )
        with pytest.raises(LedgerRecordConflict, match="completed terminal"):
            store.append(terminal)


def test_terminal_authorization_is_spent_on_reopen(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_infrastructure_issue(store))
        terminal = DurableRunTerminalV2(
            schema_version="0.2.0",
            record_type="run_terminal",
            record_id="run-terminal",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            terminal_status="abandoned",
            reason_code="synthetic_failure",
        )
        store.append(terminal)

    with pytest.raises(AuthorizationSpent):
        _open(root)


def test_terminal_is_rejected_while_any_durable_attempt_has_no_outcome(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_attempt(store))
        store.append(_infrastructure_issue(store))
        terminal = DurableRunTerminalV2(
            schema_version="0.2.0",
            record_type="run_terminal",
            record_id="run-terminal",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            terminal_status="abandoned",
            reason_code="synthetic_failure",
        )
        with pytest.raises(LedgerRecordConflict, match="unfinished attempt"):
            store.append(terminal)


def test_resume_records_explicit_unknown_crash_evidence_without_fabricating_zero(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_attempt(store))

    with _open(root) as resumed:
        reconciled = resumed.reconcile_unfinished_attempts(recorded_at=NOW)
        assert reconciled == ("attempt-0001",)
        finish = resumed.records[-2]
        assert isinstance(finish, DurableAttemptFinishedV2)
        assert finish.outcome == "crash_outcome_unknown"
        assert finish.error_code == "process_crash_outcome_unknown"
        assert finish.accepted_bytes is None
        issue = resumed.records[-1]
        assert isinstance(issue, DurableIssueV2)
        assert issue.classification == "MISSING_EVIDENCE"
        assert issue.reason_code == "attempt_outcome_unknown_after_process_crash"
        assert resumed.consumed_attempts == 1
        assert resumed.reserved_bytes == 50_000_000
        assert resumed.reconcile_unfinished_attempts(recorded_at=NOW) == ("attempt-0001",)
        resumed.append(
            DurableRunTerminalV2(
                schema_version="0.2.0",
                record_type="run_terminal",
                record_id="run-terminal",
                authorization_id="authorization-1",
                run_id="run-1",
                plan_id="plan-1",
                sequence=resumed.next_sequence,
                previous_record_sha256=resumed.ledger_head_sha256,
                recorded_at=NOW,
                terminal_status="stop_for_review",
                reason_code="attempt_outcome_unknown_after_process_crash",
            )
        )
        assert isinstance(resumed.records[-1], DurableRunTerminalV2)
        assert resumed.records[-1].terminal_status == "stop_for_review"


def test_resume_repairs_missing_issue_after_crash_between_unknown_finish_and_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        store.append(_attempt(store))
        append = store.append

        def crash_before_issue(record: object) -> bool:
            if isinstance(record, DurableIssueV2):
                raise RuntimeError("synthetic crash after anchored unknown finish")
            return append(record)  # type: ignore[arg-type]

        monkeypatch.setattr(store, "append", crash_before_issue)
        with pytest.raises(RuntimeError, match="after anchored unknown finish"):
            store.reconcile_unfinished_attempts(recorded_at=NOW)
        assert isinstance(store.records[-1], DurableAttemptFinishedV2)
        assert store.records[-1].outcome == "crash_outcome_unknown"

    with _open(root) as resumed:
        assert resumed.reconcile_unfinished_attempts(recorded_at=NOW) == ("attempt-0001",)
        issues = tuple(record for record in resumed.records if isinstance(record, DurableIssueV2))
        assert len(issues) == 1
        assert issues[0].record_id == "issue-crash-outcome-unknown-attempt-0001"
        assert issues[0].classification == "MISSING_EVIDENCE"


def test_unknown_crash_terminal_requires_matching_missing_evidence_issue(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        store.append(_opened(store))
        start = _attempt(store)
        store.append(start)
        store.append(
            DurableAttemptFinishedV2(
                schema_version="0.2.0",
                record_type="attempt_finished",
                record_id=f"{start.attempt_id}-finish",
                authorization_id=store.authorization_id,
                run_id=store.run_id,
                plan_id=store.plan_id,
                sequence=store.next_sequence,
                previous_record_sha256=store.ledger_head_sha256,
                recorded_at=NOW,
                attempt_id=start.attempt_id,
                attempt_ordinal=start.attempt_ordinal,
                outcome="crash_outcome_unknown",
                status_code=None,
                accepted_bytes=None,
                body_sha256=None,
                error_code="process_crash_outcome_unknown",
                response_headers=None,
            )
        )
        terminal = DurableRunTerminalV2(
            schema_version="0.2.0",
            record_type="run_terminal",
            record_id="run-terminal",
            authorization_id=store.authorization_id,
            run_id=store.run_id,
            plan_id=store.plan_id,
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            terminal_status="stop_for_review",
            reason_code="attempt_outcome_unknown_after_process_crash",
        )
        with pytest.raises(LedgerRecordConflict, match="MISSING_EVIDENCE"):
            store.append(terminal)


def test_resume_rejects_run_opened_under_another_execution_tree(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root) as store:
        opened = _opened(store).model_copy(update={"execution_tree_sha256": "c" * 64})
        store.append(opened)

    with pytest.raises(LedgerRollbackDetected, match="execution identity"):
        _open(root)


def test_resume_rejects_same_id_with_different_authorization_artifact(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with _open(root):
        pass

    with pytest.raises(LedgerRollbackDetected, match="authorization claim identity"):
        _open(root, authorization_artifact_sha256=OTHER_SHA)


def test_crash_before_terminal_index_is_non_resumable(tmp_path: Path) -> None:
    root = _root(tmp_path)

    def fail(stage: str) -> None:
        if stage == "after_terminal_anchor_before_terminal_index":
            raise RuntimeError("synthetic terminal crash")

    with _open(root, fault_injector=fail) as store:
        store.append(_opened(store))
        store.append(_infrastructure_issue(store))
        terminal = DurableRunTerminalV2(
            schema_version="0.2.0",
            record_type="run_terminal",
            record_id="run-terminal",
            authorization_id="authorization-1",
            run_id="run-1",
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            terminal_status="abandoned",
            reason_code="synthetic_failure",
        )
        with pytest.raises(RuntimeError, match="synthetic terminal crash"):
            store.append(terminal)

    with pytest.raises(LedgerRollbackDetected, match="terminal states differ"):
        _open(root)


def test_subprocess_lock_contention_and_abrupt_release(tmp_path: Path) -> None:
    root = _root(tmp_path)
    ready = tmp_path / "child-ready"
    child_code = "\n".join(
        (
            "import sys, time",
            "from datetime import UTC, datetime",
            "from pathlib import Path",
            (
                "from peru_conflicts.acquisition.authorization "
                "import compute_data_root_identity_sha256"
            ),
            ("from peru_conflicts.acquisition.models_v2 import StorageNamespaceMarkerV2"),
            ("from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore"),
            "root, ready = Path(sys.argv[1]), Path(sys.argv[2])",
            (
                "marker = StorageNamespaceMarkerV2(schema_version='0.2.0', "
                "namespace_id='m1-03b-pilot', owner_nonce_sha256='a' * 64)"
            ),
            (
                "identity = compute_data_root_identity_sha256(root, "
                "marker_nonce_sha256='a' * 64, "
                "execution_host_identity_sha256='b' * 64)"
            ),
            (
                "store = ManifestLedgerStore.open(data_root=root, marker=marker, "
                "expected_data_root_identity_sha256=identity, "
                "execution_host_identity_sha256='b' * 64, "
                "expected_execution_tree_sha256='a' * 64, "
                "expected_authorization_artifact_sha256='a' * 64, "
                "authorization_id='authorization-1', run_id='run-1', "
                "plan_id='plan-1', recorded_at=datetime(2026, 8, 29, 12, 0, "
                "tzinfo=UTC))"
            ),
            "ready.write_text('ready', encoding='utf-8')",
            "time.sleep(30)",
            "store.close()",
        )
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(root), str(ready)],
        cwd=Path(__file__).resolve().parents[2],
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "child did not acquire the manifest lock"
        with pytest.raises(LedgerLockUnavailable):
            _open(root)
    finally:
        process.kill()
        process.wait(timeout=10)

    with _open(root) as resumed:
        assert resumed.records == ()
