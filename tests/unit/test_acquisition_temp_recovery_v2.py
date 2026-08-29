"""Deterministic system-temp recovery never touches raw storage."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.authorization import compute_data_root_identity_sha256
from peru_conflicts.acquisition.fs_safety import (
    DirectoryLease,
    DirectoryLeaseError,
    deletion_quarantine_name,
)
from peru_conflicts.acquisition.models import SafeResponseHeaders
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
    DurableRunOpenedV2,
    DurableTemporaryRecoveryV2,
    StorageNamespaceMarkerV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.temp_recovery import (
    TemporaryRecoveryError,
    TemporaryRecoveryManager,
    temporary_object_names,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
SHA = "a" * 64
HOST_SHA = "b" * 64
AUTHORIZATION_ID = "authorization-1"
RUN_ID = "m103b-synthetic"


def _store(tmp_path: Path) -> ManifestLedgerStore:
    data_root = tmp_path / "data"
    (data_root / "01_raw" / "manifests").mkdir(parents=True)
    identity = compute_data_root_identity_sha256(
        data_root,
        marker_nonce_sha256=SHA,
        execution_host_identity_sha256=HOST_SHA,
    )
    store = ManifestLedgerStore.open(
        data_root=data_root,
        marker=StorageNamespaceMarkerV2(
            schema_version="0.2.0",
            namespace_id="namespace-1",
            owner_nonce_sha256=SHA,
        ),
        expected_data_root_identity_sha256=identity,
        execution_host_identity_sha256=HOST_SHA,
        expected_execution_tree_sha256=SHA,
        expected_authorization_artifact_sha256=SHA,
        authorization_id=AUTHORIZATION_ID,
        run_id=RUN_ID,
        plan_id="plan-1",
        recorded_at=NOW,
    )
    store.append(
        DurableRunOpenedV2(
            schema_version="0.2.0",
            record_type="run_opened",
            record_id="run-opened",
            authorization_id=AUTHORIZATION_ID,
            run_id=RUN_ID,
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            authorization_artifact_sha256=SHA,
            execution_tree_sha256=SHA,
            data_root_identity_sha256=store.data_root_identity_sha256,
            execution_host_identity_sha256=HOST_SHA,
        )
    )
    return store


def _pdf_attempt(
    store: ManifestLedgerStore,
    *,
    body: bytes | None,
) -> str:
    attempt_id = "attempt-0001"
    store.append(
        DurableAttemptStartedV2(
            schema_version="0.2.0",
            record_type="attempt_started",
            record_id=f"{attempt_id}-start",
            authorization_id=AUTHORIZATION_ID,
            run_id=RUN_ID,
            plan_id="plan-1",
            sequence=store.next_sequence,
            previous_record_sha256=store.ledger_head_sha256,
            recorded_at=NOW,
            attempt_id=attempt_id,
            attempt_ordinal=1,
            report_number=260,
            request_kind="pdf",
            source_url_sha256=SHA,
            normalized_url="https://www.defensoria.gob.pe/file.pdf",
            wire_target="/file.pdf",
            reserved_bytes=50_000_000,
        )
    )
    if body is not None:
        store.append(
            DurableAttemptFinishedV2(
                schema_version="0.2.0",
                record_type="attempt_finished",
                record_id=f"{attempt_id}-finish",
                authorization_id=AUTHORIZATION_ID,
                run_id=RUN_ID,
                plan_id="plan-1",
                sequence=store.next_sequence,
                previous_record_sha256=store.ledger_head_sha256,
                recorded_at=NOW,
                attempt_id=attempt_id,
                attempt_ordinal=1,
                outcome="success",
                status_code=200,
                accepted_bytes=len(body),
                body_sha256=hashlib.sha256(body).hexdigest(),
                error_code=None,
                response_headers=SafeResponseHeaders(content_type_original="application/pdf"),
            )
        )
    return attempt_id


def _run_directory(tmp_path: Path) -> Path:
    path = tmp_path / "system-temp" / RUN_ID
    path.mkdir(parents=True)
    return path


def test_dangling_partial_is_removed_and_durably_classified(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        attempt_id = _pdf_attempt(store, body=None)
        partial, _complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / partial
        path.write_bytes(b"%PDF-partial")

        recovered = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        ).reconcile()

        assert recovered == {}
        assert not path.exists()
        record = store.records[-1]
        assert isinstance(record, DurableTemporaryRecoveryV2)
        assert record.attempt_id == attempt_id
        assert record.recovery_action == "removed_partial"


def test_complete_object_is_rehashed_and_returned_for_resume(tmp_path: Path) -> None:
    body = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        attempt_id = _pdf_attempt(store, body=body)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        path.write_bytes(body)

        recovered = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        ).reconcile()

        assert recovered[260].attempt_id == attempt_id
        assert recovered[260].downloaded.path == path
        assert recovered[260].downloaded.sha256 == hashlib.sha256(body).hexdigest()


def test_unexpected_or_mismatched_complete_object_fails_without_deletion(
    tmp_path: Path,
) -> None:
    body = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        _pdf_attempt(store, body=body)
        directory = _run_directory(tmp_path)
        unexpected = directory / "unowned.pdf"
        unexpected.write_bytes(body)

        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        with pytest.raises(TemporaryRecoveryError, match="unexpected"):
            manager.reconcile()
        assert unexpected.exists()

        unexpected.unlink()
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        mismatched = directory / complete
        mismatched.write_bytes(body + b"different")
        with pytest.raises(TemporaryRecoveryError, match="fingerprint"):
            manager.reconcile()
        assert mismatched.exists()


def test_intermediate_symlink_above_configured_temp_root_is_rejected_before_cleanup(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = tmp_path / "redirected-parent"
    try:
        junction.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")

    with _store(tmp_path) as store:
        _pdf_attempt(store, body=None)
        partial, _complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        run_directory = junction / "system-temp" / RUN_ID
        run_directory.mkdir(parents=True)
        owned = run_directory / partial
        owned.write_bytes(b"%PDF-partial")

        manager = TemporaryRecoveryManager(
            system_temp_root=junction / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        with pytest.raises(TemporaryRecoveryError, match="identity-bound"):
            manager.reconcile()
        assert owned.exists()


def test_complete_bytes_without_durable_success_are_removed_not_reused(
    tmp_path: Path,
) -> None:
    body = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        attempt_id = _pdf_attempt(store, body=None)
        store.reconcile_unfinished_attempts(recorded_at=NOW)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        path.write_bytes(body)

        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        if os.name == "nt":
            assert manager.reconcile() == {}
            assert not path.exists()
            record = store.records[-1]
            assert isinstance(record, DurableTemporaryRecoveryV2)
            assert record.attempt_id == attempt_id
            assert record.recovery_action == "removed_unaccepted_complete"
            observation = store.records[-2]
        else:
            with pytest.raises(TemporaryRecoveryError):
                manager.reconcile()
            quarantine = path.with_name(deletion_quarantine_name(path.name))
            assert not path.exists()
            assert quarantine.read_bytes() == body
            observation = store.records[-1]
        assert isinstance(observation, DurableTemporaryRecoveryV2)
        assert observation.recovery_action == "observed_unaccepted_complete"
        assert observation.observed_bytes == len(body)
        assert observation.observed_sha256 == hashlib.sha256(body).hexdigest()


def test_unaccepted_complete_fingerprint_is_durable_before_failed_unlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        attempt_id = _pdf_attempt(store, body=None)
        store.reconcile_unfinished_attempts(recorded_at=NOW)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        path.write_bytes(body)
        original = DirectoryLease.unlink_open_child

        def fail_unlink(
            lease: DirectoryLease,
            name: str,
            source: object,
        ) -> None:
            del lease, name, source
            raise DirectoryLeaseError("synthetic cleanup failure")

        monkeypatch.setattr(DirectoryLease, "unlink_open_child", fail_unlink)
        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        with pytest.raises(TemporaryRecoveryError):
            manager.reconcile()

        observation = store.records[-1]
        assert isinstance(observation, DurableTemporaryRecoveryV2)
        assert observation.attempt_id == attempt_id
        assert observation.recovery_action == "observed_unaccepted_complete"
        assert observation.observed_bytes == len(body)
        assert observation.observed_sha256 == hashlib.sha256(body).hexdigest()
        quarantine = path.with_name(deletion_quarantine_name(path.name))
        assert not path.exists()
        assert quarantine.read_bytes() == body

        monkeypatch.setattr(DirectoryLease, "unlink_open_child", original)
        if os.name == "nt":
            assert manager.reconcile() == {}
            assert not path.exists()
            assert not quarantine.exists()
            removed = store.records[-1]
            assert isinstance(removed, DurableTemporaryRecoveryV2)
            assert removed.recovery_action == "removed_unaccepted_complete"
        else:
            with pytest.raises(TemporaryRecoveryError):
                manager.reconcile()
            assert quarantine.read_bytes() == body


def test_failed_cleanup_restart_refuses_replaced_complete_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_body = b"%PDF-" + b"a" * 1_020
    replacement_body = b"%PDF-" + b"b" * 1_020
    with _store(tmp_path) as store:
        _pdf_attempt(store, body=None)
        store.reconcile_unfinished_attempts(recorded_at=NOW)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        path.write_bytes(first_body)
        original = DirectoryLease.unlink_open_child

        def fail_delete(
            lease: DirectoryLease,
            name: str,
            source: object,
        ) -> None:
            del lease, name, source
            raise DirectoryLeaseError("synthetic cleanup failure")

        monkeypatch.setattr(DirectoryLease, "unlink_open_child", fail_delete)
        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        with pytest.raises(TemporaryRecoveryError):
            manager.reconcile()
        quarantine = path.with_name(deletion_quarantine_name(path.name))
        assert quarantine.read_bytes() == first_body
        path.write_bytes(replacement_body)

        monkeypatch.setattr(DirectoryLease, "unlink_open_child", original)
        with pytest.raises(TemporaryRecoveryError, match="conflicting"):
            manager.reconcile()
        assert path.read_bytes() == replacement_body
        assert quarantine.read_bytes() == first_body
        assert not any(
            isinstance(record, DurableTemporaryRecoveryV2)
            and record.recovery_action == "removed_unaccepted_complete"
            for record in store.records
        )


def test_replacement_between_observation_and_delete_is_not_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_body = b"%PDF-" + b"a" * 1_020
    replacement_body = b"%PDF-" + b"b" * 1_020
    with _store(tmp_path) as store:
        _pdf_attempt(store, body=None)
        store.reconcile_unfinished_attempts(recorded_at=NOW)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        displaced = path.with_name(f"{path.name}.displaced")
        path.write_bytes(first_body)
        append_recovery = TemporaryRecoveryManager._append_recovery  # pyright: ignore[reportPrivateUsage]

        def replace_after_observation(
            manager: TemporaryRecoveryManager,
            **kwargs: object,
        ) -> None:
            append_recovery(manager, **kwargs)  # type: ignore[arg-type]
            if kwargs.get("recovery_action") == "observed_unaccepted_complete":
                path.replace(displaced)
                path.write_bytes(replacement_body)

        monkeypatch.setattr(
            TemporaryRecoveryManager,
            "_append_recovery",
            replace_after_observation,
        )
        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )
        with pytest.raises(TemporaryRecoveryError, match="identity"):
            manager.reconcile()
        quarantine = path.with_name(deletion_quarantine_name(path.name))
        assert quarantine.read_bytes() == replacement_body
        assert displaced.read_bytes() == first_body
        assert not any(
            isinstance(record, DurableTemporaryRecoveryV2)
            and record.recovery_action == "removed_unaccepted_complete"
            for record in store.records
        )


def test_replacement_during_quarantine_move_is_preserved_for_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_body = b"%PDF-" + b"a" * 1_020
    replacement_body = b"%PDF-" + b"b" * 1_020
    with _store(tmp_path) as store:
        _pdf_attempt(store, body=None)
        store.reconcile_unfinished_attempts(recorded_at=NOW)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        path = _run_directory(tmp_path) / complete
        displaced = path.with_name(f"{path.name}.displaced")
        path.write_bytes(first_body)
        real_quarantine = DirectoryLease.quarantine_open_child

        def replace_before_move(
            directory: DirectoryLease,
            name: str,
            source: object,
            quarantine_name: str,
        ) -> None:
            path.replace(displaced)
            path.write_bytes(replacement_body)
            real_quarantine(directory, name, source, quarantine_name)  # type: ignore[arg-type]

        monkeypatch.setattr(
            DirectoryLease,
            "quarantine_open_child",
            replace_before_move,
        )
        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )

        with pytest.raises(TemporaryRecoveryError, match="identity-bound"):
            manager.reconcile()

        quarantined = path.with_name(deletion_quarantine_name(path.name))
        assert quarantined.read_bytes() == replacement_body
        assert displaced.read_bytes() == first_body
        assert not any(
            isinstance(record, DurableTemporaryRecoveryV2)
            and record.recovery_action == "removed_unaccepted_complete"
            for record in store.records
        )


def test_successful_complete_in_delete_quarantine_is_resumable(tmp_path: Path) -> None:
    body = b"%PDF-" + b"x" * 1_020
    with _store(tmp_path) as store:
        attempt_id = _pdf_attempt(store, body=body)
        _partial, complete = temporary_object_names(
            AUTHORIZATION_ID,
            report_number=260,
            attempt_ordinal=1,
        )
        quarantine_name = deletion_quarantine_name(complete)
        quarantine = _run_directory(tmp_path) / quarantine_name
        quarantine.write_bytes(body)
        manager = TemporaryRecoveryManager(
            system_temp_root=tmp_path / "system-temp",
            run_id=RUN_ID,
            authorization_id=AUTHORIZATION_ID,
            ledger=store,
            utc_clock=lambda: NOW,
        )

        recovered = manager.reconcile()

        assert recovered[260].attempt_id == attempt_id
        assert recovered[260].downloaded.path == quarantine
        assert recovered[260].downloaded.sha256 == hashlib.sha256(body).hexdigest()


def test_posix_no_replace_rename_never_falls_back_to_link_unlink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from peru_conflicts.acquisition import fs_safety

    class NoRenameAt2:
        pass

    def forbidden_link(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("non-atomic link/unlink fallback was attempted")

    def no_renameat2(*args: object, **kwargs: object) -> NoRenameAt2:
        del args, kwargs
        return NoRenameAt2()

    monkeypatch.setattr(fs_safety.ctypes, "CDLL", no_renameat2)
    monkeypatch.setattr(fs_safety.os, "link", forbidden_link)

    with pytest.raises(OSError, match="atomic no-replace rename is unavailable"):
        fs_safety._posix_rename_no_replace(1, "source", 1, "destination")  # pyright: ignore[reportPrivateUsage]
