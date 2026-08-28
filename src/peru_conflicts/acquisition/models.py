"""Strict acquisition-plan and dry-run models for M1-03A."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self, cast
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from peru_conflicts.discovery.pilot import (
    PilotDryRun,
    PilotLimits,
    PilotPromotionPolicy,
    PilotTarget,
)
from peru_conflicts.discovery.policy import classify_host
from peru_conflicts.discovery.settings import AUTHORITATIVE_HOSTS
from peru_conflicts.models.common import Identifier, Sha256, StrictModel

GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


def _validate_raw_report_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    raw_parts = value.split("/")
    if (
        "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.parts[:2] != ("01_raw", "reports")
        or len(path.parts) < 3
    ):
        raise ValueError("path must be a safe 01_raw/reports relative path")
    return value


RawReportRelativePath = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r".*\S.*"),
    AfterValidator(_validate_raw_report_relative_path),
]


class AcquisitionPilotPlan(StrictModel):
    """A structurally closed v2 pilot whose exact bytes are pinned by its loader."""

    schema_version: Literal["0.1.0"]
    plan_id: Identifier
    authorization_status: Literal["not_authorized"]
    purpose: Identifier
    approved_hosts: tuple[Identifier, ...]
    limits: PilotLimits
    dry_run: PilotDryRun
    baseline_receipt_path: Identifier
    baseline_receipt_git_commit: GitCommit
    baseline_receipt_sha256: Sha256
    promotion_policy: PilotPromotionPolicy
    targets: tuple[PilotTarget, ...]

    @field_validator("approved_hosts", "targets", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_scope_and_authority(self) -> Self:
        if self.approved_hosts != AUTHORITATIVE_HOSTS:
            raise ValueError("approved_hosts must be the exact reviewed authoritative hosts")
        if self.limits.max_reports != len(self.targets):
            raise ValueError("max_reports must equal the exact target count")
        if self.limits.max_urls != len(self.targets) * 2:
            raise ValueError("max_urls must equal the two logical URLs per target")
        if [target.report_number for target in self.targets] != list(range(260, 270)):
            raise ValueError("pilot must contain exactly reports 260 through 269 in order")

        approved = frozenset(self.approved_hosts)
        landing_urls: set[str] = set()
        direct_urls: set[str] = set()
        for target in self.targets:
            for url in (target.landing_page_url, target.direct_download_url):
                parsed = urlsplit(url)
                if (
                    parsed.scheme != "https"
                    or parsed.port not in (None, 443)
                    or parsed.username is not None
                    or parsed.password is not None
                    or classify_host(url, approved) != "authoritative"
                ):
                    raise ValueError(
                        "every pilot URL must use an approved HTTPS host and default port"
                    )
            if target.landing_page_url in landing_urls:
                raise ValueError("pilot landing URLs must be unique")
            if target.direct_download_url in direct_urls:
                raise ValueError("pilot direct-download URLs must be unique")
            landing_urls.add(target.landing_page_url)
            direct_urls.add(target.direct_download_url)
        return self


class DryRunAction(StrictModel):
    """One deterministic validation or future-operation action."""

    sequence: int = Field(ge=1)
    phase: Literal["preflight", "future_network", "future_disposition"]
    action: Identifier
    report_number: int | None = Field(default=None, ge=260, le=269)
    url_role: Literal["landing", "direct_download"] | None = None
    url: Identifier | None = None
    relative_path: Identifier | None = None


class DryRunResult(StrictModel):
    """Deterministic proof that M1-03A planned actions without side effects."""

    schema_version: Literal["0.1.0"]
    run_type: Literal["m1_03a_dry_run"]
    plan_id: Identifier
    plan_file_sha256: Sha256
    plan_semantic_sha256: Sha256
    target_set_sha256: Sha256
    baseline_git_commit: GitCommit
    baseline_receipt_path: Identifier
    baseline_receipt_sha256: Sha256
    verified_source_count: Literal[10]
    verified_source_bytes: int = Field(ge=1)
    logical_url_count: Literal[20]
    network_requests: Literal[0]
    dropbox_writes: Literal[0]
    actions: tuple[DryRunAction, ...]

    @field_validator("actions", mode="before")
    @classmethod
    def freeze_actions(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_ordered_actions(self) -> Self:
        if [action.sequence for action in self.actions] != list(range(1, len(self.actions) + 1)):
            raise ValueError("dry-run actions must be consecutively ordered")
        return self


class NetworkAuthorizationArtifact(StrictModel):
    """Shape of a future owner-reviewed artifact; M1-03A creates no instance."""

    schema_version: Literal["0.1.0"]
    authorization_id: Identifier
    authorization_status: Literal["authorized"]
    scope: Literal["m1_03b_reports_260_269_network"]
    plan_id: Identifier
    plan_file_sha256: Sha256
    baseline_git_commit: GitCommit
    approved_by: Identifier
    approved_at: datetime

    @field_validator("approved_at")
    @classmethod
    def require_aware_approval_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization approval time must include a timezone")
        return value


class AcquisitionRequestKind(StrEnum):
    ROBOTS = "robots"
    LANDING_HTML = "landing_html"
    PDF = "pdf"


class AcquisitionAttemptOutcome(StrEnum):
    SUCCESS = "success"
    REDIRECT = "redirect"
    RETRYABLE_FAILURE = "retryable_failure"
    REJECTED = "rejected"
    INTERRUPTED = "interrupted"


class AcquisitionFailureStage(StrEnum):
    """Stage at which a non-attempt or policy-level acquisition failure occurred."""

    ROBOTS_BODY = "robots_body"
    ROBOTS_POLICY = "robots_policy"
    RESPONSE_CLOSE = "response_close"
    TEMP_CLEANUP = "temp_cleanup"


class AcquisitionDisposition(StrEnum):
    """Disposition of observed bytes relative to the pinned local source."""

    IDENTICAL = "identical_no_duplicate_raw_file"
    STOP_FOR_REVIEW = "stop_for_review"


class SourceVersionRelationship(StrEnum):
    """Source-safe relationship between observed and pinned byte objects."""

    IDENTICAL_BYTES = "identical_bytes"
    CANDIDATE_ALTERNATE_OFFICIAL_BYTES = "candidate_alternate_official_bytes"


SAFE_RATE_LIMIT_HEADER_NAMES = frozenset(
    {
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
        "x-rate-limit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
)


SafeRateLimitHeaderName = Literal[
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
]
SafeHeaderValue = Annotated[
    str,
    StringConstraints(max_length=200, pattern=r"^[^\r\n]*$"),
]


class SafeRateLimitHeader(StrictModel):
    """One allowlisted rate-limit header without request-secret material."""

    name: SafeRateLimitHeaderName
    value: SafeHeaderValue


class SafeResponseHeaders(StrictModel):
    """Selected response evidence; request credentials and cookies are never retained."""

    content_type_original: SafeHeaderValue | None = None
    content_length_original: SafeHeaderValue | None = None
    content_encoding_original: SafeHeaderValue | None = None
    etag_original: SafeHeaderValue | None = None
    last_modified_original: SafeHeaderValue | None = None
    retry_after_original: SafeHeaderValue | None = None
    location_sanitized: SafeHeaderValue | None = None
    location_sha256: Sha256 | None = None
    rate_limit_headers: tuple[SafeRateLimitHeader, ...] = ()

    @model_validator(mode="after")
    def require_paired_location_evidence(self) -> Self:
        if (self.location_sanitized is None) != (self.location_sha256 is None):
            raise ValueError("sanitized redirect location and its hash must be paired")
        return self


class AcquisitionAttemptReceipt(StrictModel):
    """One future acquisition attempt, including rejected or interrupted streams."""

    schema_version: Literal["0.1.0"]
    attempt_id: Identifier
    run_id: Identifier
    plan_id: Identifier
    report_number: int = Field(ge=260, le=269)
    request_kind: AcquisitionRequestKind
    url: Identifier
    attempt_number: int = Field(ge=1)
    redirect_index: int = Field(ge=0)
    requested_at: datetime
    completed_at: datetime
    status_code: int | None = Field(default=None, ge=100, le=599)
    outcome: AcquisitionAttemptOutcome
    response_headers: SafeResponseHeaders | None = None
    transferred_bytes: int = Field(ge=0)
    complete_body_sha256: Sha256 | None = None
    redirect_target_url: Identifier | None = None
    error_code: Identifier | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_attempt_evidence(self) -> Self:
        for timestamp in (self.requested_at, self.completed_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("attempt timestamps must include a timezone")
        if self.completed_at < self.requested_at:
            raise ValueError("attempt completion cannot precede its request")
        if self.outcome is AcquisitionAttemptOutcome.SUCCESS:
            if (
                self.status_code is None
                or not 200 <= self.status_code < 300
                or self.complete_body_sha256 is None
                or self.error_code
                or self.error_message
                or self.redirect_target_url is not None
            ):
                raise ValueError(
                    "a successful attempt requires status and a complete body hash with no "
                    "error message or redirect"
                )
        elif self.outcome is AcquisitionAttemptOutcome.REDIRECT:
            if (
                self.status_code not in {301, 302, 303, 307, 308}
                or self.redirect_target_url is None
                or self.response_headers is None
                or self.response_headers.location_sanitized is None
                or self.response_headers.location_sha256 is None
                or self.complete_body_sha256 is not None
                or self.error_code is not None
                or self.error_message is not None
                or self.transferred_bytes != 0
            ):
                raise ValueError("a redirect requires status and a target but no body or error")
        elif (
            not self.error_code
            or self.complete_body_sha256 is not None
            or self.redirect_target_url is not None
        ):
            raise ValueError("a failed attempt requires an error code and no complete body hash")
        return self


class AcquisitionFailureReceipt(StrictModel):
    """A policy/body/cleanup failure not fully represented by an HTTP attempt."""

    schema_version: Literal["0.1.0"]
    failure_id: Identifier
    run_id: Identifier
    plan_id: Identifier
    report_number: int = Field(ge=260, le=269)
    stage: AcquisitionFailureStage
    url: Identifier
    occurred_at: datetime
    error_code: Identifier
    error_message: Identifier
    related_attempt_id: Identifier | None = None
    transferred_bytes: int = Field(default=0, ge=0)
    cleanup_completed: bool

    @field_validator("occurred_at")
    @classmethod
    def require_aware_failure_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("failure time must include a timezone")
        return value

    @model_validator(mode="after")
    def require_stage_specific_attempt_reference(self) -> Self:
        if self.stage in {
            AcquisitionFailureStage.ROBOTS_BODY,
            AcquisitionFailureStage.RESPONSE_CLOSE,
            AcquisitionFailureStage.TEMP_CLEANUP,
        }:
            if self.related_attempt_id is None:
                raise ValueError("body, response-close, and cleanup failures require an attempt")
        elif self.related_attempt_id is not None:
            raise ValueError("robots-policy failures must not claim a related attempt")
        return self


class LedgerRecordType(StrEnum):
    ATTEMPT = "attempt"
    FAILURE = "failure"
    URL_OBSERVATION = "url_observation"
    BYTE_OBJECT = "byte_object"
    COLLISION = "collision"
    RUN_TERMINAL = "run_terminal"


class OperationalLedgerRecord(StrictModel):
    """Typed append-only record for a future Dropbox operational ledger."""

    schema_version: Literal["0.1.0"]
    record_id: Identifier
    run_id: Identifier
    plan_id: Identifier
    recorded_at: datetime
    record_type: LedgerRecordType
    attempt: AcquisitionAttemptReceipt | None = None
    failure: AcquisitionFailureReceipt | None = None
    report_number: int | None = Field(default=None, ge=260, le=269)
    url_role: Literal["direct_download", "redirect_destination"] | None = None
    normalized_url: Identifier | None = None
    observed_sha256: Sha256 | None = None
    observed_bytes: int | None = Field(default=None, ge=0)
    expected_source_sha256: Sha256 | None = None
    disposition: AcquisitionDisposition | None = None
    version_relationship: SourceVersionRelationship | None = None
    local_relative_path: RawReportRelativePath | None = None
    source_attempt_id: Identifier | None = None
    collision_evidence_summary: Identifier | None = None
    terminal_status: Literal["completed", "abandoned", "stop_for_review"] | None = None
    reason_code: Identifier | None = None

    @model_validator(mode="after")
    def validate_record_variant(self) -> Self:
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("ledger record time must include a timezone")
        evidence_fields = (
            self.report_number,
            self.url_role,
            self.normalized_url,
            self.observed_sha256,
            self.observed_bytes,
            self.expected_source_sha256,
            self.disposition,
            self.version_relationship,
            self.local_relative_path,
            self.source_attempt_id,
            self.collision_evidence_summary,
        )
        if self.record_type is LedgerRecordType.ATTEMPT:
            if self.attempt is not None and (
                self.attempt.run_id != self.run_id or self.attempt.plan_id != self.plan_id
            ):
                raise ValueError("attempt run identity and plan identity must match the ledger")
            if (
                self.attempt is None
                or self.failure is not None
                or any(value is not None for value in evidence_fields)
                or self.terminal_status is not None
            ):
                raise ValueError("attempt ledger records contain exactly one attempt")
        elif self.record_type is LedgerRecordType.FAILURE:
            if (
                self.failure is None
                or self.attempt is not None
                or any(value is not None for value in evidence_fields)
                or self.terminal_status is not None
                or self.failure.run_id != self.run_id
                or self.failure.plan_id != self.plan_id
            ):
                raise ValueError("failure ledger records contain exactly one matching failure")
        elif self.record_type is LedgerRecordType.URL_OBSERVATION:
            if (
                self.report_number is None
                or self.url_role is None
                or self.normalized_url is None
                or self.observed_sha256 is None
                or self.observed_bytes is None
                or self.expected_source_sha256 is None
                or self.disposition is not AcquisitionDisposition.IDENTICAL
                or self.version_relationship is not SourceVersionRelationship.IDENTICAL_BYTES
                or self.local_relative_path is None
                or self.source_attempt_id is None
                or self.observed_sha256 != self.expected_source_sha256
                or self.attempt is not None
                or self.failure is not None
                or self.terminal_status is not None
                or self.collision_evidence_summary is not None
            ):
                raise ValueError(
                    "URL observations require exact pinned comparison, source attempt, and path"
                )
        elif self.record_type is LedgerRecordType.BYTE_OBJECT:
            if (
                self.observed_sha256 is None
                or self.observed_bytes is None
                or self.attempt is not None
                or self.failure is not None
                or any(
                    value is not None
                    for value in (
                        self.report_number,
                        self.url_role,
                        self.normalized_url,
                        self.expected_source_sha256,
                        self.disposition,
                        self.version_relationship,
                        self.local_relative_path,
                        self.source_attempt_id,
                        self.collision_evidence_summary,
                    )
                )
                or self.terminal_status is not None
            ):
                raise ValueError("byte-object records require only hash and byte count evidence")
        elif self.record_type is LedgerRecordType.COLLISION:
            if (
                self.report_number is None
                or self.url_role is None
                or self.normalized_url is None
                or self.observed_sha256 is None
                or self.observed_bytes is None
                or self.expected_source_sha256 is None
                or self.observed_sha256 == self.expected_source_sha256
                or self.disposition is not AcquisitionDisposition.STOP_FOR_REVIEW
                or self.version_relationship
                is not SourceVersionRelationship.CANDIDATE_ALTERNATE_OFFICIAL_BYTES
                or self.local_relative_path is None
                or self.source_attempt_id is None
                or self.collision_evidence_summary is None
                or self.attempt is not None
                or self.failure is not None
                or self.terminal_status is not None
            ):
                raise ValueError(
                    "collision records require different-byte STOP FOR REVIEW evidence"
                )
        elif (
            self.terminal_status is None
            or self.attempt is not None
            or self.failure is not None
            or any(value is not None for value in evidence_fields)
        ):
            raise ValueError("terminal records require only a terminal status and optional reason")
        return self
