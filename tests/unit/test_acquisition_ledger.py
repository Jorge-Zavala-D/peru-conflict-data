from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger
from peru_conflicts.acquisition.models import (
    AcquisitionAttemptOutcome,
    AcquisitionAttemptReceipt,
    AcquisitionDisposition,
    AcquisitionFailureReceipt,
    AcquisitionFailureStage,
    AcquisitionRequestKind,
    LedgerRecordType,
    OperationalLedgerRecord,
    SafeResponseHeaders,
    SourceVersionRelationship,
)
from peru_conflicts.acquisition.plan import LoadedPilotPlan, load_reviewed_pilot_plan

SHA = hashlib.sha256(b"synthetic pdf").hexdigest()
NOW = datetime(2026, 8, 28, tzinfo=UTC)
V2_PATH = "config/acquisition_pilots/m1_03_reports_260_269_v2.yaml"
V2_SHA256 = "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"


def _reviewed_plan() -> LoadedPilotPlan:
    from pathlib import Path

    return load_reviewed_pilot_plan(Path(V2_PATH), required_sha256=V2_SHA256)


def _append_pdf_attempt(
    ledger: InMemoryOperationalLedger,
    *,
    attempt_id: str,
    run_id: str,
    url: str,
    sha256: str,
    byte_count: int = 13,
    report_number: int = 260,
    attempt_number: int = 1,
    redirect_index: int = 0,
    when: datetime = NOW,
) -> str:
    attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id=attempt_id,
        run_id=run_id,
        plan_id="m1-03-reports-260-269-v2",
        report_number=report_number,
        request_kind=AcquisitionRequestKind.PDF,
        url=url,
        attempt_number=attempt_number,
        redirect_index=redirect_index,
        requested_at=when,
        completed_at=when,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=byte_count,
        complete_body_sha256=sha256,
    )
    ledger.append(
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id=f"record-{attempt_id}",
            run_id=run_id,
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=when,
            record_type=LedgerRecordType.ATTEMPT,
            attempt=attempt,
        )
    )
    return attempt_id


def _append_redirect_attempt(
    ledger: InMemoryOperationalLedger,
    *,
    attempt_id: str,
    run_id: str,
    source_url: str,
    target_url: str,
    attempt_number: int,
    redirect_index: int,
    report_number: int = 260,
) -> None:
    attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id=attempt_id,
        run_id=run_id,
        plan_id="m1-03-reports-260-269-v2",
        report_number=report_number,
        request_kind=AcquisitionRequestKind.PDF,
        url=source_url,
        attempt_number=attempt_number,
        redirect_index=redirect_index,
        requested_at=NOW,
        completed_at=NOW,
        status_code=302,
        outcome=AcquisitionAttemptOutcome.REDIRECT,
        response_headers=SafeResponseHeaders(
            location_sanitized=target_url,
            location_sha256=hashlib.sha256(target_url.encode()).hexdigest(),
        ),
        transferred_bytes=0,
        redirect_target_url=target_url,
    )
    ledger.append(
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id=f"record-{attempt_id}",
            run_id=run_id,
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.ATTEMPT,
            attempt=attempt,
        )
    )


def test_disposition_equal_deduplicates_and_different_stops_for_review() -> None:
    from peru_conflicts.acquisition.ledger import Disposition, decide_disposition

    assert decide_disposition(existing_sha256=SHA, observed_sha256=SHA) is Disposition.IDENTICAL
    assert (
        decide_disposition(existing_sha256=SHA, observed_sha256="0" * 64)
        is Disposition.STOP_FOR_REVIEW
    )


def test_two_urls_preserve_two_observations_but_one_byte_object_and_rerun_is_idempotent() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    ledger = InMemoryOperationalLedger(reviewed_plan=reviewed)
    first_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="first-url-attempt",
        run_id="synthetic-run",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
    )
    first = ledger.record_observation(
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=first_attempt,
        recorded_at=NOW,
    )
    redirected_url = "https://www.defensoria.gob.pe/b.pdf"
    redirect_attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="second-url-redirect",
        run_id="synthetic-run",
        plan_id=reviewed.plan.plan_id,
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url=target.direct_download_url,
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=302,
        outcome=AcquisitionAttemptOutcome.REDIRECT,
        response_headers=SafeResponseHeaders(
            location_sanitized=redirected_url,
            location_sha256=hashlib.sha256(redirected_url.encode()).hexdigest(),
        ),
        transferred_bytes=0,
        redirect_target_url=redirected_url,
    )
    ledger.append(
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="second-url-redirect-record",
            run_id="synthetic-run",
            plan_id=reviewed.plan.plan_id,
            recorded_at=NOW,
            record_type=LedgerRecordType.ATTEMPT,
            attempt=redirect_attempt,
        )
    )
    second_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="second-url-attempt",
        run_id="synthetic-run",
        url=redirected_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
        attempt_number=2,
        redirect_index=1,
    )
    second = ledger.record_observation(
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="redirect_destination",
        normalized_url=redirected_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=second_attempt,
        recorded_at=NOW,
    )
    repeated_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="rerun-url-attempt",
        run_id="synthetic-rerun",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
        when=NOW + timedelta(days=1),
    )
    repeated = ledger.record_observation(
        run_id="synthetic-rerun",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=repeated_attempt,
        recorded_at=NOW + timedelta(days=1),
    )

    assert len(first) == 2
    assert len(second) == 1
    assert repeated == ()
    assert sum(item.record_type.value == "byte_object" for item in ledger.records) == 1
    assert sum(item.record_type.value == "url_observation" for item in ledger.records) == 2


def test_append_only_ledger_rejects_record_id_reuse_with_different_content() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger, LedgerConflict

    ledger = InMemoryOperationalLedger()
    record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="terminal-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.RUN_TERMINAL,
        terminal_status="completed",
        reason_code="synthetic_complete",
    )
    ledger.append(record)

    changed = record.model_copy(update={"terminal_status": "stop_for_review"})
    try:
        ledger.append(changed)
    except LedgerConflict:
        pass
    else:
        raise AssertionError("ledger accepted conflicting reuse of an append-only record ID")
    assert ledger.records == (record,)


def test_failure_attempt_receipt_survives_canonical_jsonl_serialization() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger, serialize_ledger

    attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="synthetic-run-attempt-01",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url="https://defensoria.gob.pe/a.pdf",
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=503,
        outcome=AcquisitionAttemptOutcome.RETRYABLE_FAILURE,
        transferred_bytes=0,
        error_code="transient_http_status",
    )
    record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="attempt-record-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.ATTEMPT,
        attempt=attempt,
        reason_code="attempt_preserved",
    )
    ledger = InMemoryOperationalLedger()
    ledger.append(record)

    rendered = serialize_ledger(ledger.records)

    assert rendered.endswith(b"\n")
    assert b'"outcome":"retryable_failure"' in rendered
    assert b'"error_code":"transient_http_status"' in rendered
    assert rendered == serialize_ledger(ledger.records)


def test_fresh_ledger_hydrated_from_prior_records_is_idempotent_across_runs() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    first = InMemoryOperationalLedger(reviewed_plan=reviewed)
    first_attempt = _append_pdf_attempt(
        first,
        attempt_id="hydration-first-attempt",
        run_id="first-run",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
    )
    first.record_observation(
        run_id="first-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=first_attempt,
        recorded_at=NOW,
    )
    resumed = InMemoryOperationalLedger(first.records, reviewed_plan=reviewed)
    resumed_attempt = _append_pdf_attempt(
        resumed,
        attempt_id="hydration-second-attempt",
        run_id="second-run",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
        when=NOW + timedelta(days=1),
    )

    added = resumed.record_observation(
        run_id="second-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=resumed_attempt,
        recorded_at=NOW + timedelta(days=1),
    )

    assert added == ()
    assert resumed.records[:-1] == first.records
    assert resumed.records[-1].attempt is not None


def test_attempt_and_terminal_variants_reject_contradictory_fields() -> None:
    success = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="success-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url="https://defensoria.gob.pe/a.pdf",
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=13,
        complete_body_sha256=SHA,
    )
    with pytest.raises(ValidationError, match="error message"):
        success.model_copy(update={"error_message": "must not survive"}).model_validate(
            success.model_copy(update={"error_message": "must not survive"}).model_dump()
        )

    with pytest.raises(ValidationError, match="must be paired"):
        SafeResponseHeaders(location_sanitized="https://defensoria.gob.pe/report.pdf")

    with pytest.raises(ValidationError, match="redirect requires"):
        AcquisitionAttemptReceipt(
            schema_version="0.1.0",
            attempt_id="redirect-without-location-evidence",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            report_number=260,
            request_kind=AcquisitionRequestKind.PDF,
            url="https://defensoria.gob.pe/a.pdf",
            attempt_number=2,
            redirect_index=0,
            requested_at=NOW,
            completed_at=NOW,
            status_code=302,
            outcome=AcquisitionAttemptOutcome.REDIRECT,
            transferred_bytes=0,
            redirect_target_url="https://defensoria.gob.pe/b.pdf",
        )

    with pytest.raises(ValidationError, match="run identity"):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="attempt-mismatch",
            run_id="different-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.ATTEMPT,
            attempt=success,
        )

    with pytest.raises(ValidationError, match="terminal records"):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="terminal-contradiction",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.RUN_TERMINAL,
            terminal_status="completed",
            normalized_url="https://defensoria.gob.pe/a.pdf",
            observed_sha256=SHA,
            observed_bytes=13,
        )


def test_url_observation_preserves_pinned_comparison_and_version_semantics() -> None:
    record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="url-observation-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.URL_OBSERVATION,
        report_number=260,
        url_role="direct_download",
        normalized_url="https://defensoria.gob.pe/a.pdf",
        observed_sha256=SHA,
        observed_bytes=13,
        expected_source_sha256=SHA,
        disposition=AcquisitionDisposition.IDENTICAL,
        version_relationship=SourceVersionRelationship.IDENTICAL_BYTES,
        local_relative_path="01_raw/reports/2025/report-260.pdf",
        source_attempt_id="success-one",
    )

    assert record.expected_source_sha256 == SHA
    assert record.disposition is AcquisitionDisposition.IDENTICAL


def test_pilot_comparison_never_calls_storage_and_stops_on_different_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import peru_conflicts.acquisition.storage as storage
    from peru_conflicts.acquisition.ledger import (
        InMemoryOperationalLedger,
        record_pilot_comparison,
    )

    def forbidden_storage(**_: object) -> None:
        raise AssertionError("pinned comparison must not invoke raw storage")

    monkeypatch.setattr(storage, "stage_copy_and_publish_no_replace", forbidden_storage)
    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    ledger = InMemoryOperationalLedger()
    identical_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="comparison-identical-attempt",
        run_id="synthetic-run",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
    )
    identical = record_pilot_comparison(
        ledger,
        loaded_plan=reviewed,
        run_id="synthetic-run",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        source_attempt_id=identical_attempt,
        recorded_at=NOW,
    )
    different_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="comparison-different-attempt",
        run_id="synthetic-run",
        url=target.direct_download_url,
        sha256="0" * 64,
        attempt_number=2,
    )
    different = record_pilot_comparison(
        ledger,
        loaded_plan=reviewed,
        run_id="synthetic-run",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256="0" * 64,
        observed_bytes=13,
        source_attempt_id=different_attempt,
        recorded_at=NOW,
    )

    assert identical.disposition is AcquisitionDisposition.IDENTICAL
    assert different.disposition is AcquisitionDisposition.STOP_FOR_REVIEW
    assert different.records[0].record_type is LedgerRecordType.COLLISION
    assert different.records[0].version_relationship is (
        SourceVersionRelationship.CANDIDATE_ALTERNATE_OFFICIAL_BYTES
    )


def test_collision_is_idempotent_in_same_and_hydrated_ledgers() -> None:
    from peru_conflicts.acquisition.ledger import (
        InMemoryOperationalLedger,
        record_pilot_comparison,
    )

    first = InMemoryOperationalLedger()
    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]

    def compare(ledger: InMemoryOperationalLedger, run_id: str, when: datetime):
        attempt_id = _append_pdf_attempt(
            ledger,
            attempt_id=f"{run_id}-collision-attempt",
            run_id=run_id,
            url=target.direct_download_url,
            sha256="0" * 64,
            when=when,
        )
        return record_pilot_comparison(
            ledger,
            loaded_plan=reviewed,
            run_id=run_id,
            report_number=260,
            url_role="direct_download",
            normalized_url=target.direct_download_url,
            observed_sha256="0" * 64,
            observed_bytes=13,
            source_attempt_id=attempt_id,
            recorded_at=when,
        )

    initial = compare(first, "first-run", NOW)
    same_ledger = compare(first, "second-run", NOW + timedelta(days=1))
    hydrated = InMemoryOperationalLedger(first.records, reviewed_plan=reviewed)
    resumed = compare(hydrated, "third-run", NOW + timedelta(days=2))

    assert len(initial.records) == 1
    assert len(same_ledger.records) == 1
    assert len(resumed.records) == 1
    assert hydrated.records[:-2] == first.records
    assert hydrated.records[-2].attempt is not None
    assert hydrated.records[-1].record_type is LedgerRecordType.COLLISION


def test_collision_run_can_only_close_with_stop_for_review() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, record_pilot_comparison

    run_id = "collision-terminal-run"
    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    ledger = InMemoryOperationalLedger()
    attempt_id = _append_pdf_attempt(
        ledger,
        attempt_id="collision-terminal-attempt",
        run_id=run_id,
        url=target.direct_download_url,
        sha256="0" * 64,
    )
    record_pilot_comparison(
        ledger,
        loaded_plan=reviewed,
        run_id=run_id,
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256="0" * 64,
        observed_bytes=13,
        source_attempt_id=attempt_id,
        recorded_at=NOW,
    )
    completed = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="collision-terminal-completed",
        run_id=run_id,
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.RUN_TERMINAL,
        terminal_status="completed",
    )
    with pytest.raises(LedgerConflict, match=r"collision.*stop_for_review"):
        ledger.append(completed)

    stopped = completed.model_copy(
        update={
            "record_id": "collision-terminal-stopped",
            "terminal_status": "stop_for_review",
            "reason_code": "pinned_source_hash_mismatch",
        }
    )
    assert ledger.append(stopped) is True


def test_pilot_comparison_derives_pinned_hash_and_path_from_exact_reviewed_plan() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, record_pilot_comparison

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    mutated_target = target.model_copy(
        update={
            "existing_local_sha256": "f" * 64,
            "existing_local_relative_path": "01_raw/reports/Wrong.pdf",
        }
    )
    mutated = LoadedPilotPlan(
        plan=reviewed.plan.model_copy(
            update={"targets": (mutated_target, *reviewed.plan.targets[1:])}
        ),
        file_sha256=reviewed.file_sha256,
        semantic_sha256=reviewed.semantic_sha256,
        target_set_sha256=reviewed.target_set_sha256,
    )
    ledger = InMemoryOperationalLedger()
    attempt_id = _append_pdf_attempt(
        ledger,
        attempt_id="pinned-target-attempt",
        run_id="pinned-target-run",
        url=target.direct_download_url,
        sha256="f" * 64,
        byte_count=target.existing_local_byte_count,
    )

    with pytest.raises(LedgerConflict, match="reviewed pilot"):
        record_pilot_comparison(
            ledger,
            loaded_plan=mutated,
            run_id="pinned-target-run",
            report_number=260,
            url_role="direct_download",
            normalized_url=target.direct_download_url,
            observed_sha256="f" * 64,
            observed_bytes=target.existing_local_byte_count,
            source_attempt_id=attempt_id,
            recorded_at=NOW,
        )


def test_rejected_low_level_observation_is_atomic_and_leaves_no_orphan_byte_object() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    ledger = InMemoryOperationalLedger(reviewed_plan=reviewed)
    attempt_id = _append_pdf_attempt(
        ledger,
        attempt_id="invalid-low-level-attempt",
        run_id="invalid-low-level-run",
        url=target.direct_download_url,
        sha256="f" * 64,
        byte_count=target.existing_local_byte_count,
    )
    before = ledger.records

    with pytest.raises(LedgerConflict, match="reviewed pilot"):
        ledger.record_observation(
            run_id="invalid-low-level-run",
            plan_id=reviewed.plan.plan_id,
            report_number=260,
            url_role="direct_download",
            normalized_url=target.direct_download_url,
            observed_sha256="f" * 64,
            observed_bytes=target.existing_local_byte_count,
            expected_source_sha256="f" * 64,
            local_relative_path="01_raw/reports/Wrong.pdf",
            source_attempt_id=attempt_id,
            recorded_at=NOW,
        )

    assert ledger.records == before


def test_redirect_destination_requires_authoritative_preceding_redirect_evidence() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, record_pilot_comparison

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    direct_mislabeled = InMemoryOperationalLedger(reviewed_plan=reviewed)
    direct_attempt = _append_pdf_attempt(
        direct_mislabeled,
        attempt_id="direct-mislabeled-attempt",
        run_id="direct-mislabeled-run",
        url=target.direct_download_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
    )
    with pytest.raises(LedgerConflict, match="redirect-destination"):
        record_pilot_comparison(
            direct_mislabeled,
            loaded_plan=reviewed,
            run_id="direct-mislabeled-run",
            report_number=260,
            url_role="redirect_destination",
            normalized_url=target.direct_download_url,
            observed_sha256=target.existing_local_sha256,
            observed_bytes=target.existing_local_byte_count,
            source_attempt_id=direct_attempt,
            recorded_at=NOW,
        )

    third_party = InMemoryOperationalLedger(reviewed_plan=reviewed)
    third_party_attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="third-party-attempt",
        run_id="third-party-run",
        plan_id=reviewed.plan.plan_id,
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url="https://example.org/third-party.pdf",
        attempt_number=2,
        redirect_index=1,
        requested_at=NOW,
        completed_at=NOW,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=target.existing_local_byte_count,
        complete_body_sha256=target.existing_local_sha256,
    )
    third_party.append(
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="third-party-attempt-record",
            run_id="third-party-run",
            plan_id=reviewed.plan.plan_id,
            recorded_at=NOW,
            record_type=LedgerRecordType.ATTEMPT,
            attempt=third_party_attempt,
        )
    )
    with pytest.raises(LedgerConflict, match=r"authoritative|preceding redirect"):
        record_pilot_comparison(
            third_party,
            loaded_plan=reviewed,
            run_id="third-party-run",
            report_number=260,
            url_role="redirect_destination",
            normalized_url=third_party_attempt.url,
            observed_sha256=target.existing_local_sha256,
            observed_bytes=target.existing_local_byte_count,
            source_attempt_id=third_party_attempt.attempt_id,
            recorded_at=NOW,
        )


def test_redirect_destination_accepts_exact_same_run_redirect_chain() -> None:
    from peru_conflicts.acquisition.ledger import record_pilot_comparison

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    redirected_url = "https://www.defensoria.gob.pe/wp-content/uploads/redirected-260.pdf"
    ledger = InMemoryOperationalLedger(reviewed_plan=reviewed)
    redirect_attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="redirect-chain-attempt-1",
        run_id="redirect-chain-run",
        plan_id=reviewed.plan.plan_id,
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url=target.direct_download_url,
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=302,
        outcome=AcquisitionAttemptOutcome.REDIRECT,
        response_headers=SafeResponseHeaders(
            location_sanitized=redirected_url,
            location_sha256=hashlib.sha256(redirected_url.encode()).hexdigest(),
        ),
        transferred_bytes=0,
        redirect_target_url=redirected_url,
    )
    success_attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="redirect-chain-attempt-2",
        run_id="redirect-chain-run",
        plan_id=reviewed.plan.plan_id,
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url=redirected_url,
        attempt_number=2,
        redirect_index=1,
        requested_at=NOW,
        completed_at=NOW,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=target.existing_local_byte_count,
        complete_body_sha256=target.existing_local_sha256,
    )
    for index, attempt in enumerate((redirect_attempt, success_attempt), start=1):
        ledger.append(
            OperationalLedgerRecord(
                schema_version="0.1.0",
                record_id=f"redirect-chain-record-{index}",
                run_id="redirect-chain-run",
                plan_id=reviewed.plan.plan_id,
                recorded_at=NOW,
                record_type=LedgerRecordType.ATTEMPT,
                attempt=attempt,
            )
        )

    result = record_pilot_comparison(
        ledger,
        loaded_plan=reviewed,
        run_id="redirect-chain-run",
        report_number=260,
        url_role="redirect_destination",
        normalized_url=redirected_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        source_attempt_id=success_attempt.attempt_id,
        recorded_at=NOW,
    )

    assert result.disposition is AcquisitionDisposition.IDENTICAL


def test_redirect_destination_rejects_chain_missing_reviewed_index_zero_root() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, record_pilot_comparison

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    middle_url = "https://www.defensoria.gob.pe/wp-content/uploads/middle-260.pdf"
    final_url = "https://www.defensoria.gob.pe/wp-content/uploads/final-260.pdf"
    ledger = InMemoryOperationalLedger(reviewed_plan=reviewed)
    _append_redirect_attempt(
        ledger,
        attempt_id="rootless-redirect-index-1",
        run_id="rootless-run",
        source_url=middle_url,
        target_url=final_url,
        attempt_number=2,
        redirect_index=1,
    )
    success_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="rootless-success-index-2",
        run_id="rootless-run",
        url=final_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
        attempt_number=3,
        redirect_index=2,
    )
    before = ledger.records

    with pytest.raises(LedgerConflict, match=r"complete|rooted"):
        record_pilot_comparison(
            ledger,
            loaded_plan=reviewed,
            run_id="rootless-run",
            report_number=260,
            url_role="redirect_destination",
            normalized_url=final_url,
            observed_sha256=target.existing_local_sha256,
            observed_bytes=target.existing_local_byte_count,
            source_attempt_id=success_attempt,
            recorded_at=NOW,
        )

    assert ledger.records == before


def test_redirect_destination_rejects_forked_chain_atomically() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, record_pilot_comparison

    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    final_url = "https://www.defensoria.gob.pe/wp-content/uploads/forked-260.pdf"
    ledger = InMemoryOperationalLedger(reviewed_plan=reviewed)
    for attempt_number in (1, 2):
        _append_redirect_attempt(
            ledger,
            attempt_id=f"forked-redirect-{attempt_number}",
            run_id="forked-run",
            source_url=target.direct_download_url,
            target_url=final_url,
            attempt_number=attempt_number,
            redirect_index=0,
        )
    success_attempt = _append_pdf_attempt(
        ledger,
        attempt_id="forked-success",
        run_id="forked-run",
        url=final_url,
        sha256=target.existing_local_sha256,
        byte_count=target.existing_local_byte_count,
        attempt_number=3,
        redirect_index=1,
    )
    before = ledger.records

    with pytest.raises(LedgerConflict, match="unforked"):
        record_pilot_comparison(
            ledger,
            loaded_plan=reviewed,
            run_id="forked-run",
            report_number=260,
            url_role="redirect_destination",
            normalized_url=final_url,
            observed_sha256=target.existing_local_sha256,
            observed_bytes=target.existing_local_byte_count,
            source_attempt_id=success_attempt,
            recorded_at=NOW,
        )

    assert ledger.records == before


def test_ledger_closes_runs_and_requires_failure_attempt_references() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger, LedgerConflict

    ledger = InMemoryOperationalLedger()
    terminal = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="terminal-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.RUN_TERMINAL,
        terminal_status="completed",
        reason_code="synthetic_complete",
    )
    ledger.append(terminal)
    later_object = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="byte-after-terminal",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW + timedelta(seconds=1),
        record_type=LedgerRecordType.BYTE_OBJECT,
        observed_sha256=SHA,
        observed_bytes=13,
    )
    with pytest.raises(LedgerConflict, match="terminal"):
        ledger.append(later_object)

    orphan = AcquisitionFailureReceipt(
        schema_version="0.1.0",
        failure_id="failure-orphan",
        run_id="different-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        stage=AcquisitionFailureStage.ROBOTS_BODY,
        url="https://defensoria.gob.pe/robots.txt",
        occurred_at=NOW,
        error_code="robots_body_too_large",
        error_message="synthetic failure",
        related_attempt_id="missing-attempt",
        cleanup_completed=True,
    )
    orphan_record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="failure-record-orphan",
        run_id="different-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.FAILURE,
        failure=orphan,
    )
    with pytest.raises(LedgerConflict, match="related attempt"):
        InMemoryOperationalLedger().append(orphan_record)


def test_serializer_revalidates_conflicting_records_and_collision_paths_are_safe() -> None:
    from peru_conflicts.acquisition.ledger import LedgerConflict, serialize_ledger

    terminal = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="terminal-conflict",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.RUN_TERMINAL,
        terminal_status="completed",
    )
    conflicting = terminal.model_copy(update={"terminal_status": "abandoned"})
    with pytest.raises(LedgerConflict):
        serialize_ledger((terminal, conflicting))

    valid_observation = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="strict-observation",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.URL_OBSERVATION,
        report_number=260,
        url_role="direct_download",
        normalized_url="https://defensoria.gob.pe/a.pdf",
        observed_sha256=SHA,
        observed_bytes=13,
        expected_source_sha256=SHA,
        disposition=AcquisitionDisposition.IDENTICAL,
        version_relationship=SourceVersionRelationship.IDENTICAL_BYTES,
        local_relative_path="01_raw/reports/2025/report-260.pdf",
        source_attempt_id="strict-attempt",
    )
    invalid_copy = valid_observation.model_copy(update={"observed_sha256": "0" * 64})
    with pytest.raises(LedgerConflict, match="strict model revalidation"):
        serialize_ledger((invalid_copy,))

    with pytest.raises(ValidationError, match="safe 01_raw/reports"):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="unsafe-collision",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.COLLISION,
            report_number=260,
            url_role="direct_download",
            normalized_url="https://defensoria.gob.pe/a.pdf",
            observed_sha256="0" * 64,
            observed_bytes=13,
            expected_source_sha256=SHA,
            disposition=AcquisitionDisposition.STOP_FOR_REVIEW,
            version_relationship=SourceVersionRelationship.CANDIDATE_ALTERNATE_OFFICIAL_BYTES,
            local_relative_path="C:/outside/report.pdf",
            collision_evidence_summary="pinned hash differs from observed hash",
        )


@pytest.mark.parametrize(
    "unsafe_path",
    (
        "01_raw/reports/.",
        "01_raw/reports//",
        "01_raw/reports/2026/./report.pdf",
        "01_raw/reports/2026//report.pdf",
    ),
)
def test_ledger_model_rejects_empty_or_dot_path_segments(unsafe_path: str) -> None:
    with pytest.raises(ValidationError, match="safe 01_raw/reports"):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="unsafe-path-segments",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.COLLISION,
            report_number=260,
            url_role="direct_download",
            normalized_url="https://defensoria.gob.pe/a.pdf",
            observed_sha256="0" * 64,
            observed_bytes=13,
            expected_source_sha256=SHA,
            disposition=AcquisitionDisposition.STOP_FOR_REVIEW,
            version_relationship=SourceVersionRelationship.CANDIDATE_ALTERNATE_OFFICIAL_BYTES,
            local_relative_path=unsafe_path,
            source_attempt_id="attempt-one",
            collision_evidence_summary="pinned hash differs from observed hash",
        )


def test_url_observation_requires_equal_hashes_and_successful_attempt_provenance() -> None:
    reviewed = _reviewed_plan()
    target = reviewed.plan.targets[0]
    success = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="source-attempt-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        request_kind=AcquisitionRequestKind.PDF,
        url=target.direct_download_url,
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=target.existing_local_byte_count,
        complete_body_sha256=target.existing_local_sha256,
    )
    attempt_record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="source-attempt-record-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.ATTEMPT,
        attempt=success,
    )
    with pytest.raises(ValidationError):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="unequal-observation",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.URL_OBSERVATION,
            report_number=260,
            url_role="direct_download",
            normalized_url="https://defensoria.gob.pe/a.pdf",
            observed_sha256="0" * 64,
            observed_bytes=13,
            expected_source_sha256=SHA,
            disposition=AcquisitionDisposition.IDENTICAL,
            version_relationship=SourceVersionRelationship.IDENTICAL_BYTES,
            local_relative_path="01_raw/reports/2025/report-260.pdf",
            source_attempt_id=success.attempt_id,
        )

    with pytest.raises(ValidationError, match="source attempt"):
        OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id="missing-attempt-observation",
            run_id="synthetic-run",
            plan_id="m1-03-reports-260-269-v2",
            recorded_at=NOW,
            record_type=LedgerRecordType.URL_OBSERVATION,
            report_number=260,
            url_role="direct_download",
            normalized_url="https://defensoria.gob.pe/a.pdf",
            observed_sha256=SHA,
            observed_bytes=13,
            expected_source_sha256=SHA,
            disposition=AcquisitionDisposition.IDENTICAL,
            version_relationship=SourceVersionRelationship.IDENTICAL_BYTES,
            local_relative_path="01_raw/reports/2025/report-260.pdf",
        )

    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger

    ledger = InMemoryOperationalLedger((attempt_record,), reviewed_plan=reviewed)
    records = ledger.record_observation(
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        url_role="direct_download",
        normalized_url=target.direct_download_url,
        observed_sha256=target.existing_local_sha256,
        observed_bytes=target.existing_local_byte_count,
        expected_source_sha256=target.existing_local_sha256,
        local_relative_path=target.existing_local_relative_path,
        source_attempt_id=success.attempt_id,
        recorded_at=NOW,
    )
    assert records[-1].source_attempt_id == success.attempt_id


def test_failure_reference_must_match_attempt_report_url_and_kind() -> None:
    from peru_conflicts.acquisition.ledger import InMemoryOperationalLedger, LedgerConflict

    attempt = AcquisitionAttemptReceipt(
        schema_version="0.1.0",
        attempt_id="robots-attempt-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=260,
        request_kind=AcquisitionRequestKind.ROBOTS,
        url="https://defensoria.gob.pe/robots.txt",
        attempt_number=1,
        redirect_index=0,
        requested_at=NOW,
        completed_at=NOW,
        status_code=200,
        outcome=AcquisitionAttemptOutcome.SUCCESS,
        transferred_bytes=13,
        complete_body_sha256=SHA,
    )
    attempt_record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="robots-attempt-record-one",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.ATTEMPT,
        attempt=attempt,
    )
    mismatched = AcquisitionFailureReceipt(
        schema_version="0.1.0",
        failure_id="failure-wrong-report",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        report_number=269,
        stage=AcquisitionFailureStage.ROBOTS_BODY,
        url="https://defensoria.gob.pe/wrong-robots.txt",
        occurred_at=NOW,
        error_code="robots_body_failure",
        error_message="synthetic mismatch",
        related_attempt_id=attempt.attempt_id,
        cleanup_completed=True,
    )
    failure_record = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id="failure-record-wrong-report",
        run_id="synthetic-run",
        plan_id="m1-03-reports-260-269-v2",
        recorded_at=NOW,
        record_type=LedgerRecordType.FAILURE,
        failure=mismatched,
    )
    ledger = InMemoryOperationalLedger((attempt_record,))

    with pytest.raises(LedgerConflict, match=r"report|URL|kind"):
        ledger.append(failure_record)
