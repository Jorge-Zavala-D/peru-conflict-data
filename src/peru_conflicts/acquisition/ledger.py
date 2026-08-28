"""Pure append-only operational-ledger semantics for future authorized acquisition."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import ValidationError

from peru_conflicts.acquisition.models import (
    AcquisitionAttemptOutcome,
    AcquisitionDisposition,
    AcquisitionFailureStage,
    AcquisitionRequestKind,
    LedgerRecordType,
    OperationalLedgerRecord,
    SourceVersionRelationship,
)
from peru_conflicts.acquisition.plan import (
    LoadedPilotPlan,
    PlanFingerprintMismatch,
    validate_reviewed_loaded_plan,
)
from peru_conflicts.acquisition.policy import UnapprovedAcquisitionUrl, validate_url
from peru_conflicts.discovery.pilot import PilotTarget
from peru_conflicts.hashing import canonical_json_bytes

Disposition = AcquisitionDisposition


class LedgerConflict(ValueError):
    """An append-only record identity was reused with different content."""


def decide_disposition(*, existing_sha256: str, observed_sha256: str) -> Disposition:
    """Never promote bytes different from the pinned existing source hash."""

    return (
        Disposition.IDENTICAL if existing_sha256 == observed_sha256 else Disposition.STOP_FOR_REVIEW
    )


def _record_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:20]}"


class InMemoryOperationalLedger:
    """Idempotent in-memory ledger; M1-03A provides no production path writer."""

    def __init__(
        self,
        initial_records: Iterable[OperationalLedgerRecord] = (),
        *,
        reviewed_plan: LoadedPilotPlan | None = None,
    ) -> None:
        self._records: list[OperationalLedgerRecord] = []
        self._by_id: dict[str, OperationalLedgerRecord] = {}
        self._byte_objects: dict[str, int] = {}
        self._url_observations: dict[tuple[str, int, str, str, str], OperationalLedgerRecord] = {}
        self._collisions: dict[
            tuple[str, str, int, str, str, str, str], OperationalLedgerRecord
        ] = {}
        self._collision_runs: set[tuple[str, str]] = set()
        self._attempts: dict[str, OperationalLedgerRecord] = {}
        self._failures: dict[str, OperationalLedgerRecord] = {}
        self._terminals: dict[tuple[str, str], OperationalLedgerRecord] = {}
        self._reviewed_plan_id: str | None = None
        self._reviewed_hosts: frozenset[str] = frozenset()
        self._reviewed_targets: dict[int, PilotTarget] = {}
        if reviewed_plan is not None:
            self.bind_reviewed_plan(reviewed_plan)
        for record in initial_records:
            self.append(record)

    @property
    def records(self) -> tuple[OperationalLedgerRecord, ...]:
        return tuple(self._records)

    def bind_reviewed_plan(self, loaded_plan: LoadedPilotPlan) -> None:
        """Bind comparison-bearing records to one exact reviewed target set."""

        try:
            plan = validate_reviewed_loaded_plan(loaded_plan)
        except PlanFingerprintMismatch as error:
            raise LedgerConflict("ledger requires the exact reviewed pilot") from error
        if self._reviewed_plan_id is not None and self._reviewed_plan_id != plan.plan_id:
            raise LedgerConflict("ledger is already bound to a different reviewed pilot")
        self._reviewed_plan_id = plan.plan_id
        self._reviewed_hosts = frozenset(plan.approved_hosts)
        self._reviewed_targets = {target.report_number: target for target in plan.targets}

    def _require_pinned_target(self, record: OperationalLedgerRecord) -> None:
        if self._reviewed_plan_id is None:
            raise LedgerConflict("comparison records require an exact reviewed pilot binding")
        if record.plan_id != self._reviewed_plan_id:
            raise LedgerConflict("comparison record plan does not match the reviewed pilot")
        assert record.report_number is not None
        target = self._reviewed_targets.get(record.report_number)
        if target is None:
            raise LedgerConflict("comparison report is outside the reviewed pilot")
        if (
            record.expected_source_sha256 != target.existing_local_sha256
            or record.local_relative_path != target.existing_local_relative_path
        ):
            raise LedgerConflict("comparison hash or path does not match the reviewed pilot")
        if (
            record.url_role == "direct_download"
            and record.normalized_url != target.direct_download_url
        ):
            raise LedgerConflict("direct-download URL does not match the reviewed pilot")

    def append(self, record: OperationalLedgerRecord) -> bool:
        try:
            record = OperationalLedgerRecord.model_validate(
                record.model_dump(mode="python"), strict=True
            )
        except ValidationError as error:
            raise LedgerConflict("ledger record failed strict model revalidation") from error
        run_key = (record.plan_id, record.run_id)
        if record.record_type in {
            LedgerRecordType.URL_OBSERVATION,
            LedgerRecordType.COLLISION,
        }:
            self._require_pinned_target(record)
            self._require_source_attempt(record)
        if record.record_type is LedgerRecordType.COLLISION:
            assert record.report_number is not None
            assert record.url_role is not None
            assert record.normalized_url is not None
            assert record.expected_source_sha256 is not None
            assert record.observed_sha256 is not None
            collision_key = (
                record.plan_id,
                record.run_id,
                record.report_number,
                record.url_role,
                record.normalized_url,
                record.expected_source_sha256,
                record.observed_sha256,
            )
            existing_collision = self._collisions.get(collision_key)
            if existing_collision is not None:
                stable_fields = (
                    "observed_bytes",
                    "disposition",
                    "version_relationship",
                    "local_relative_path",
                    "collision_evidence_summary",
                    "reason_code",
                )
                if any(
                    getattr(existing_collision, field) != getattr(record, field)
                    for field in stable_fields
                ):
                    raise LedgerConflict("an idempotent collision cannot change pinned provenance")
                return False

        previous = self._by_id.get(record.record_id)
        if previous is not None:
            if previous != record:
                raise LedgerConflict(
                    f"record ID {record.record_id} already identifies different content"
                )
            return False
        if run_key in self._terminals:
            raise LedgerConflict("no record may follow a terminal record for the same run")
        if (
            record.record_type is LedgerRecordType.RUN_TERMINAL
            and run_key in self._collision_runs
            and record.terminal_status != "stop_for_review"
        ):
            raise LedgerConflict("a collision-bearing run must terminate as stop_for_review")

        if record.record_type is LedgerRecordType.BYTE_OBJECT:
            assert record.observed_sha256 is not None
            assert record.observed_bytes is not None
            known_size = self._byte_objects.get(record.observed_sha256)
            if known_size is not None and known_size != record.observed_bytes:
                raise LedgerConflict("one SHA-256 cannot identify two byte counts")
        elif record.record_type is LedgerRecordType.URL_OBSERVATION:
            assert record.report_number is not None
            assert record.url_role is not None
            assert record.normalized_url is not None
            assert record.observed_sha256 is not None
            assert record.observed_bytes is not None
            if self._byte_objects.get(record.observed_sha256) != record.observed_bytes:
                raise LedgerConflict("URL observation must follow its matching byte-object record")
            key = (
                record.plan_id,
                record.report_number,
                record.url_role,
                record.normalized_url,
                record.observed_sha256,
            )
            known_observation = self._url_observations.get(key)
            if known_observation is not None and known_observation != record:
                raise LedgerConflict("URL observation identity has conflicting provenance")
        elif record.record_type is LedgerRecordType.ATTEMPT:
            assert record.attempt is not None
            known_attempt = self._attempts.get(record.attempt.attempt_id)
            if known_attempt is not None and known_attempt != record:
                raise LedgerConflict("attempt ID identifies conflicting receipt content")
        elif record.record_type is LedgerRecordType.FAILURE:
            assert record.failure is not None
            known_failure = self._failures.get(record.failure.failure_id)
            if known_failure is not None and known_failure != record:
                raise LedgerConflict("failure ID identifies conflicting receipt content")
            related_id = record.failure.related_attempt_id
            if related_id is not None:
                related_record = self._attempts.get(related_id)
                if related_record is None:
                    raise LedgerConflict("failure related attempt is absent from the ledger")
                assert related_record.attempt is not None
                if (
                    related_record.run_id != record.run_id
                    or related_record.plan_id != record.plan_id
                ):
                    raise LedgerConflict("failure related attempt belongs to another run")
                if related_record.attempt.report_number != record.failure.report_number:
                    raise LedgerConflict("failure report does not match its related attempt")
                if related_record.attempt.url != record.failure.url:
                    raise LedgerConflict("failure URL does not match its related attempt")
                if (
                    record.failure.stage is AcquisitionFailureStage.ROBOTS_BODY
                    and related_record.attempt.request_kind is not AcquisitionRequestKind.ROBOTS
                ):
                    raise LedgerConflict("robots-body failure kind does not match its attempt")
                if (
                    record.failure.stage is AcquisitionFailureStage.TEMP_CLEANUP
                    and related_record.attempt.request_kind is not AcquisitionRequestKind.PDF
                ):
                    raise LedgerConflict("cleanup failure kind does not match its PDF attempt")

        self._records.append(record)
        self._by_id[record.record_id] = record
        if record.record_type is LedgerRecordType.BYTE_OBJECT:
            assert record.observed_sha256 is not None
            assert record.observed_bytes is not None
            self._byte_objects[record.observed_sha256] = record.observed_bytes
        elif record.record_type is LedgerRecordType.URL_OBSERVATION:
            assert record.report_number is not None
            assert record.url_role is not None
            assert record.normalized_url is not None
            assert record.observed_sha256 is not None
            key = (
                record.plan_id,
                record.report_number,
                record.url_role,
                record.normalized_url,
                record.observed_sha256,
            )
            self._url_observations[key] = record
        elif record.record_type is LedgerRecordType.COLLISION:
            assert record.report_number is not None
            assert record.url_role is not None
            assert record.normalized_url is not None
            assert record.expected_source_sha256 is not None
            assert record.observed_sha256 is not None
            collision_key = (
                record.plan_id,
                record.run_id,
                record.report_number,
                record.url_role,
                record.normalized_url,
                record.expected_source_sha256,
                record.observed_sha256,
            )
            self._collisions[collision_key] = record
            self._collision_runs.add(run_key)
        elif record.record_type is LedgerRecordType.ATTEMPT:
            assert record.attempt is not None
            self._attempts[record.attempt.attempt_id] = record
        elif record.record_type is LedgerRecordType.FAILURE:
            assert record.failure is not None
            self._failures[record.failure.failure_id] = record
        elif record.record_type is LedgerRecordType.RUN_TERMINAL:
            self._terminals[run_key] = record
        return True

    def _require_source_attempt(self, record: OperationalLedgerRecord) -> None:
        assert record.source_attempt_id is not None
        assert record.report_number is not None
        assert record.normalized_url is not None
        assert record.observed_sha256 is not None
        assert record.observed_bytes is not None
        attempt_record = self._attempts.get(record.source_attempt_id)
        if attempt_record is None or attempt_record.attempt is None:
            raise LedgerConflict("source attempt is absent from the ledger")
        attempt = attempt_record.attempt
        if attempt.run_id != record.run_id or attempt.plan_id != record.plan_id:
            raise LedgerConflict("source attempt belongs to another run")
        if attempt.report_number != record.report_number:
            raise LedgerConflict("source attempt report does not match the observation")
        if attempt.request_kind is not AcquisitionRequestKind.PDF:
            raise LedgerConflict("source attempt kind is not a PDF request")
        if attempt.outcome is not AcquisitionAttemptOutcome.SUCCESS:
            raise LedgerConflict("source attempt is not successful")
        if attempt.url != record.normalized_url:
            raise LedgerConflict("source attempt URL does not match the observation")
        if (
            attempt.complete_body_sha256 != record.observed_sha256
            or attempt.transferred_bytes != record.observed_bytes
        ):
            raise LedgerConflict("source attempt bytes do not match the observation")
        target = self._reviewed_targets[record.report_number]
        if record.url_role == "direct_download":
            if attempt.redirect_index != 0 or attempt.url != target.direct_download_url:
                raise LedgerConflict(
                    "direct-download observation requires the exact non-redirected target"
                )
            return
        try:
            normalized = validate_url(record.normalized_url, self._reviewed_hosts)
        except UnapprovedAcquisitionUrl as error:
            raise LedgerConflict(
                "redirect-destination URL is outside the reviewed authoritative hosts"
            ) from error
        if normalized != record.normalized_url or normalized == target.direct_download_url:
            raise LedgerConflict(
                "redirect-destination must be a distinct normalized authoritative URL"
            )
        if attempt.redirect_index <= 0:
            raise LedgerConflict("redirect-destination attempt requires a positive redirect index")
        current_url = record.normalized_url
        later_attempt_number = attempt.attempt_number
        for expected_index in range(attempt.redirect_index - 1, -1, -1):
            same_index = tuple(
                candidate.attempt
                for candidate in self._attempts.values()
                if candidate.attempt is not None
                and candidate.attempt.run_id == attempt.run_id
                and candidate.attempt.plan_id == attempt.plan_id
                and candidate.attempt.report_number == attempt.report_number
                and candidate.attempt.request_kind is AcquisitionRequestKind.PDF
                and candidate.attempt.outcome is AcquisitionAttemptOutcome.REDIRECT
                and candidate.attempt.redirect_index == expected_index
                and candidate.attempt.attempt_number < later_attempt_number
            )
            if len(same_index) != 1:
                raise LedgerConflict(
                    "redirect-destination requires one complete, unforked chain to index zero"
                )
            redirect = same_index[0]
            if redirect.redirect_target_url != current_url:
                raise LedgerConflict("redirect chain target does not match its next request URL")
            try:
                redirect_url = validate_url(redirect.url, self._reviewed_hosts)
            except UnapprovedAcquisitionUrl as error:
                raise LedgerConflict("redirect chain contains a non-authoritative URL") from error
            if redirect_url != redirect.url:
                raise LedgerConflict("redirect chain contains a non-normalized URL")
            current_url = redirect.url
            later_attempt_number = redirect.attempt_number
        if current_url != target.direct_download_url:
            raise LedgerConflict("redirect chain is not rooted at the reviewed direct URL")

    def record_observation(
        self,
        *,
        run_id: str,
        plan_id: str,
        report_number: int,
        url_role: Literal["direct_download", "redirect_destination"],
        normalized_url: str,
        observed_sha256: str,
        observed_bytes: int,
        expected_source_sha256: str,
        local_relative_path: str,
        source_attempt_id: str,
        recorded_at: datetime,
    ) -> tuple[OperationalLedgerRecord, ...]:
        """Preserve URL multiplicity while deduplicating identical byte objects."""

        if observed_sha256 != expected_source_sha256:
            raise LedgerConflict("different bytes require a collision record and STOP FOR REVIEW")
        source_probe = OperationalLedgerRecord(
            schema_version="0.1.0",
            record_id=_record_id(
                "url-observation",
                plan_id,
                str(report_number),
                url_role,
                normalized_url,
                observed_sha256,
            ),
            run_id=run_id,
            plan_id=plan_id,
            recorded_at=recorded_at,
            record_type=LedgerRecordType.URL_OBSERVATION,
            report_number=report_number,
            url_role=url_role,
            normalized_url=normalized_url,
            observed_sha256=observed_sha256,
            observed_bytes=observed_bytes,
            expected_source_sha256=expected_source_sha256,
            disposition=AcquisitionDisposition.IDENTICAL,
            version_relationship=SourceVersionRelationship.IDENTICAL_BYTES,
            local_relative_path=local_relative_path,
            source_attempt_id=source_attempt_id,
        )
        self._require_pinned_target(source_probe)
        self._require_source_attempt(source_probe)
        added: list[OperationalLedgerRecord] = []
        known_size = self._byte_objects.get(observed_sha256)
        if known_size is not None and known_size != observed_bytes:
            raise LedgerConflict("one SHA-256 cannot identify two byte counts")
        if known_size is None:
            byte_record = OperationalLedgerRecord(
                schema_version="0.1.0",
                record_id=_record_id("byte-object", observed_sha256),
                run_id=run_id,
                plan_id=plan_id,
                recorded_at=recorded_at,
                record_type=LedgerRecordType.BYTE_OBJECT,
                observed_sha256=observed_sha256,
                observed_bytes=observed_bytes,
            )
            if self.append(byte_record):
                added.append(byte_record)

        observation_key = (
            plan_id,
            report_number,
            url_role,
            normalized_url,
            observed_sha256,
        )
        existing_observation = self._url_observations.get(observation_key)
        if existing_observation is not None:
            if (
                existing_observation.expected_source_sha256 != expected_source_sha256
                or existing_observation.local_relative_path != local_relative_path
                or existing_observation.observed_bytes != observed_bytes
            ):
                raise LedgerConflict(
                    "an idempotent URL observation cannot change pinned provenance"
                )
        else:
            observation_record = source_probe
            if self.append(observation_record):
                added.append(observation_record)
        return tuple(added)


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Fail-closed result of comparing downloaded bytes with the pinned source."""

    disposition: AcquisitionDisposition
    records: tuple[OperationalLedgerRecord, ...]


def record_pilot_comparison(
    ledger: InMemoryOperationalLedger,
    *,
    loaded_plan: LoadedPilotPlan,
    run_id: str,
    report_number: int,
    url_role: Literal["direct_download", "redirect_destination"],
    normalized_url: str,
    observed_sha256: str,
    observed_bytes: int,
    source_attempt_id: str,
    recorded_at: datetime,
) -> ComparisonResult:
    """Record equality or collision evidence without invoking any storage primitive."""

    try:
        plan = validate_reviewed_loaded_plan(loaded_plan)
    except PlanFingerprintMismatch as error:
        raise LedgerConflict("comparison requires the exact reviewed pilot") from error
    ledger.bind_reviewed_plan(loaded_plan)
    targets = {target.report_number: target for target in plan.targets}
    target = targets.get(report_number)
    if target is None:
        raise LedgerConflict("report is outside the exact reviewed pilot")
    if url_role == "direct_download" and normalized_url != target.direct_download_url:
        raise LedgerConflict("direct-download URL does not match the reviewed pilot target")
    plan_id = plan.plan_id
    expected_source_sha256 = target.existing_local_sha256
    local_relative_path = target.existing_local_relative_path

    disposition = decide_disposition(
        existing_sha256=expected_source_sha256,
        observed_sha256=observed_sha256,
    )
    if disposition is AcquisitionDisposition.IDENTICAL:
        records = ledger.record_observation(
            run_id=run_id,
            plan_id=plan_id,
            report_number=report_number,
            url_role=url_role,
            normalized_url=normalized_url,
            observed_sha256=observed_sha256,
            observed_bytes=observed_bytes,
            expected_source_sha256=expected_source_sha256,
            local_relative_path=local_relative_path,
            source_attempt_id=source_attempt_id,
            recorded_at=recorded_at,
        )
        return ComparisonResult(disposition=disposition, records=records)

    collision = OperationalLedgerRecord(
        schema_version="0.1.0",
        record_id=_record_id(
            "collision",
            plan_id,
            run_id,
            str(report_number),
            url_role,
            normalized_url,
            expected_source_sha256,
            observed_sha256,
        ),
        run_id=run_id,
        plan_id=plan_id,
        recorded_at=recorded_at,
        record_type=LedgerRecordType.COLLISION,
        report_number=report_number,
        url_role=url_role,
        normalized_url=normalized_url,
        observed_sha256=observed_sha256,
        observed_bytes=observed_bytes,
        expected_source_sha256=expected_source_sha256,
        disposition=AcquisitionDisposition.STOP_FOR_REVIEW,
        version_relationship=SourceVersionRelationship.CANDIDATE_ALTERNATE_OFFICIAL_BYTES,
        local_relative_path=local_relative_path,
        source_attempt_id=source_attempt_id,
        collision_evidence_summary="pinned existing SHA-256 differs from observed SHA-256",
        reason_code="pinned_source_hash_mismatch",
    )
    added = (collision,) if ledger.append(collision) else ()
    return ComparisonResult(disposition=disposition, records=added)


def serialize_ledger(
    records: Iterable[OperationalLedgerRecord], *, reviewed_plan: LoadedPilotPlan | None = None
) -> bytes:
    """Serialize append order as canonical newline-delimited JSON, without writing it."""

    validated = InMemoryOperationalLedger(records, reviewed_plan=reviewed_plan)
    rendered = b"".join(
        canonical_json_bytes(record.model_dump(mode="json")) + b"\n" for record in validated.records
    )
    return rendered
