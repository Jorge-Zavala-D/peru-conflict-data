"""Strict, source-safe receipts for HTML reconnaissance attempts and runs."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from peru_conflicts.models.common import Identifier, Sha256, StrictModel

RECEIPT_SCHEMA_VERSION = "0.3.0"


class RequestKind(StrEnum):
    """The only response-body purposes authorized during M1 discovery."""

    HTML = "html"
    ROBOTS = "robots"


class RequestOutcome(StrEnum):
    """Outcome of one actual HTTP transport attempt."""

    SUCCESS = "success"
    REDIRECT = "redirect"
    TRANSIENT_HTTP = "transient_http"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    REJECTED_CONTENT_TYPE = "rejected_content_type"
    REJECTED_BODY_SIGNATURE = "rejected_body_signature"
    REJECTED_BODY_SIZE = "rejected_body_size"
    REJECTED_REDIRECT = "rejected_redirect"


class RateLimitHeader(StrictModel):
    """One explicitly allowlisted rate-limit response header."""

    name: Identifier
    value: str

    @model_validator(mode="after")
    def require_rate_limit_name(self) -> Self:
        normalized = self.name.lower()
        if not normalized.startswith(("ratelimit-", "x-ratelimit-", "x-rate-limit-")):
            raise ValueError("header name is not a recognized rate-limit header")
        return self


class SelectedHttpHeaders(StrictModel):
    """Fixed safe subset of response headers; never cookies or credentials."""

    content_type_original: str | None = None
    content_length_original: str | None = None
    etag_original: str | None = None
    last_modified_original: str | None = None
    retry_after_original: str | None = None
    location_original: str | None = None
    rate_limit_headers: tuple[RateLimitHeader, ...] = ()


class RequestAttemptReceipt(StrictModel):
    """One actual request attempt, preserved before retry, rejection, or return."""

    schema_version: Literal["0.3.0"]
    receipt_id: Identifier
    observation_id: Identifier | None = None
    request_kind: RequestKind
    attempt_number: int = Field(ge=1)
    redirect_index: int = Field(ge=0)
    requested_url: Identifier
    requested_at: AwareDatetime
    completed_at: AwareDatetime
    outcome: RequestOutcome
    status_code: int | None = Field(default=None, ge=100, le=599)
    response_url: str | None = None
    selected_headers: SelectedHttpHeaders
    body_read: bool
    body_complete: bool = True
    body_byte_count: int | None = Field(default=None, ge=0)
    body_sha256: Sha256 | None = None
    redirect_target_url: str | None = None
    retry_scheduled: bool = False
    retry_delay_seconds: float | None = Field(default=None, ge=0)
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_attempt_closure(self) -> Self:
        if self.completed_at < self.requested_at:
            raise ValueError("completed_at cannot precede requested_at")

        has_body_evidence = self.body_byte_count is not None or self.body_sha256 is not None
        if self.body_read and (self.body_byte_count is None or self.body_sha256 is None):
            raise ValueError("a read body requires both body byte count and body SHA-256")
        if not self.body_read and has_body_evidence:
            raise ValueError("an unread body cannot carry body byte count or body SHA-256")
        if self.body_complete and not self.body_read:
            if self.outcome is RequestOutcome.TRANSPORT_ERROR:
                raise ValueError("a transport error cannot claim a complete response body")
            raise ValueError("a complete body must have been read")

        if self.body_read:
            content_type = (
                (self.selected_headers.content_type_original or "")
                .split(";", maxsplit=1)[0]
                .strip()
                .lower()
            )
            allowed = (
                {"text/plain"}
                if self.request_kind is RequestKind.ROBOTS
                else {"text/html", "application/xhtml+xml"}
            )
            if content_type not in allowed:
                raise ValueError("body content type is outside the request-kind allowlist")
            if self.outcome not in {
                RequestOutcome.SUCCESS,
                RequestOutcome.REJECTED_BODY_SIGNATURE,
                RequestOutcome.REJECTED_BODY_SIZE,
            }:
                raise ValueError(
                    "only success or a body-rejected response may retain read-body evidence"
                )

        if self.outcome is RequestOutcome.TRANSPORT_ERROR:
            if (
                self.status_code is not None
                or self.response_url is not None
                or self.body_read
                or self.body_complete
            ):
                raise ValueError("a transport error cannot claim an HTTP response or body")
            if not self.error_type:
                raise ValueError("a transport error requires error_type evidence")
        elif self.status_code is None:
            raise ValueError("an HTTP attempt outcome requires a status code")

        status = self.status_code
        is_success_status = status is not None and 200 <= status < 300
        is_redirect_status = status in {301, 302, 303, 307, 308}
        is_transient_status = status in {429, 500, 502, 503, 504}
        unread_incomplete = not self.body_read and not self.body_complete

        if self.outcome is RequestOutcome.SUCCESS and not (
            is_success_status and self.body_read and self.body_complete
        ):
            raise ValueError("success outcome requires 2xx status and a complete read body")
        if self.outcome is RequestOutcome.REDIRECT:
            if not (is_redirect_status and unread_incomplete):
                raise ValueError("redirect outcome requires a redirect status and no response body")
            if not self.selected_headers.location_original or not self.redirect_target_url:
                raise ValueError(
                    "redirect outcome requires Location and normalized target evidence"
                )
        elif self.redirect_target_url is not None:
            raise ValueError("redirect target evidence is valid only for a redirect outcome")
        if self.outcome is RequestOutcome.REJECTED_REDIRECT:
            if not (is_redirect_status and unread_incomplete):
                raise ValueError(
                    "rejected redirect requires a redirect status and no response body"
                )
            if not self.error_type or self.redirect_target_url is not None:
                raise ValueError(
                    "rejected redirect requires error evidence and no normalized target"
                )
        if self.outcome is RequestOutcome.TRANSIENT_HTTP and not (
            is_transient_status and unread_incomplete
        ):
            raise ValueError(
                "transient outcome requires an allowlisted transient status and no body"
            )
        if self.outcome is RequestOutcome.HTTP_ERROR and not (
            status is not None
            and not is_success_status
            and not is_redirect_status
            and not is_transient_status
            and unread_incomplete
        ):
            raise ValueError("HTTP-error outcome requires a terminal non-2xx status and no body")
        if self.outcome is RequestOutcome.REJECTED_CONTENT_TYPE and not (
            is_success_status and unread_incomplete
        ):
            raise ValueError("content-type rejection requires a 2xx status and an unread body")
        if self.outcome is RequestOutcome.REJECTED_BODY_SIGNATURE and not (
            is_success_status and self.body_read and self.body_complete
        ):
            raise ValueError("signature rejection requires a 2xx status and a complete read body")
        if self.outcome is RequestOutcome.REJECTED_BODY_SIZE and not (
            is_success_status and not self.body_complete
        ):
            raise ValueError("body-size rejection requires a 2xx status and an incomplete body")

        if self.retry_scheduled != (self.retry_delay_seconds is not None):
            raise ValueError("a scheduled retry requires exactly one retry delay")
        if self.retry_scheduled and self.outcome not in {
            RequestOutcome.TRANSIENT_HTTP,
            RequestOutcome.TRANSPORT_ERROR,
        }:
            raise ValueError("only transient HTTP or transport failures may schedule a retry")
        return self


class SurfaceStopReason(StrEnum):
    """Observed reason a bounded starting-surface traversal stopped."""

    NO_NEXT_LINK = "no_next_link"
    REPEATED_URL = "repeated_url"
    NON_AUTHORITATIVE_NEXT = "non_authoritative_next"
    PAGE_CAP = "page_cap"
    ERROR = "error"
    SINGLE_PAGE = "single_page"


class StopClass(StrEnum):
    """Scientific interpretation of a local traversal stop."""

    LOCAL_TERMINAL = "local_terminal"
    SAFETY_STOP = "safety_stop"
    ERROR = "error"


class SurfaceTraversalReceipt(StrictModel):
    """Per-surface stop evidence without a corpus-completeness claim."""

    start_url: Identifier
    pages_visited: int = Field(ge=0)
    seen_urls: tuple[Identifier, ...] = ()
    stop_reason: SurfaceStopReason
    stop_class: StopClass
    reached_local_terminal: bool
    pagination_contract_verified: bool
    pagination_exhausted: bool

    @model_validator(mode="after")
    def validate_stop_interpretation(self) -> Self:
        if self.stop_reason is SurfaceStopReason.REPEATED_URL and (
            self.reached_local_terminal or self.pagination_exhausted
        ):
            raise ValueError("a repeated URL is a safety stop, not a local terminal or exhaustion")
        if self.pagination_exhausted and (
            self.stop_reason is not SurfaceStopReason.NO_NEXT_LINK
            or not self.pagination_contract_verified
            or not self.reached_local_terminal
        ):
            raise ValueError(
                "pagination exhaustion requires a verified contract and observed no-next terminal"
            )
        return self


class LandingTraversalCounts(StrictModel):
    """Accounting for discovered landing URLs under the bounded landing cap."""

    discovered: int = Field(ge=0)
    selected: int = Field(ge=0)
    fetched: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    cap_reached: bool

    @model_validator(mode="after")
    def close_counts(self) -> Self:
        if self.selected + self.skipped != self.discovered:
            raise ValueError("landing selected plus skipped must equal discovered")
        if self.fetched + self.failed != self.selected:
            raise ValueError("landing fetched plus failed must equal selected")
        if self.cap_reached != (self.skipped > 0):
            raise ValueError("landing cap_reached must agree with skipped count")
        return self


class ReconnaissanceError(StrictModel):
    """One bounded runner error retained without swallowing the run evidence."""

    url: Identifier
    error_type: Identifier
    message: Identifier


class CorpusCompletenessStatus(StrEnum):
    """M1 is not authorized to assert corpus completeness."""

    NOT_ASSESSED = "not_assessed"


class ReconnaissanceSummary(StrictModel):
    """Versioned run summary separating traversal from corpus completeness."""

    schema_version: Literal["0.3.0"]
    run_id: Identifier
    started_at: AwareDatetime
    completed_at: AwareDatetime
    start_urls: tuple[Identifier, ...]
    pages_visited: int = Field(ge=0)
    records_written: int = Field(ge=0)
    request_attempt_count: int = Field(ge=0)
    surface_traversals: tuple[SurfaceTraversalReceipt, ...]
    errors: tuple[ReconnaissanceError, ...] = ()
    landing_pages: LandingTraversalCounts
    all_surfaces_reached_local_terminal: bool
    corpus_completeness_status: Literal[CorpusCompletenessStatus.NOT_ASSESSED]
    boundary: Identifier

    @model_validator(mode="after")
    def validate_run_closure(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        observed_terminal = bool(self.surface_traversals) and all(
            item.reached_local_terminal for item in self.surface_traversals
        )
        if self.all_surfaces_reached_local_terminal != observed_terminal:
            raise ValueError("all_surfaces_reached_local_terminal must match surface receipts")
        return self
