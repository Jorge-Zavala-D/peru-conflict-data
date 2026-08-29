"""Durable attempt-claim wrapper around the production streaming transport."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from peru_conflicts.acquisition.engine import (
    StreamingResponse,
    StreamingTransport,
    safe_response_headers,
)
from peru_conflicts.acquisition.models_v2 import (
    DurableAttemptFinishedV2,
    DurableAttemptStartedV2,
)
from peru_conflicts.acquisition.persistent_ledger import ManifestLedgerStore
from peru_conflicts.acquisition.policy import SealedTransportPolicyError
from peru_conflicts.acquisition.transport import canonicalize_acquisition_url

_RESERVATIONS = {
    "robots": 500_000,
    "landing_html": 2_000_000,
    "pdf": 50_000_000,
}
RequestKind = Literal["robots", "landing_html", "pdf"]
AttemptOutcome = Literal[
    "success",
    "redirect",
    "rejected",
    "retryable_failure",
    "interrupted",
]


class _Digest(Protocol):
    def update(self, value: bytes, /) -> None: ...

    def hexdigest(self) -> str: ...


def _request_kind(headers: Mapping[str, str]) -> RequestKind:
    accept = next(
        (value.casefold() for name, value in headers.items() if name.casefold() == "accept"),
        "",
    )
    if "application/pdf" in accept:
        return "pdf"
    if "text/plain" in accept:
        return "robots"
    if "text/html" in accept or "application/xhtml+xml" in accept:
        return "landing_html"
    raise SealedTransportPolicyError(
        "request Accept header does not identify an approved acquisition role"
    )


@dataclass(slots=True)
class _DurableResponse:
    status_code: int
    headers: Mapping[str, str]
    _response: StreamingResponse
    _ledger: ManifestLedgerStore
    _started: DurableAttemptStartedV2
    _utc_clock: Callable[[], datetime]
    _digest: _Digest
    _on_finished: Callable[[DurableAttemptStartedV2, AttemptOutcome], None]
    _accepted_bytes: int = 0
    _body_exhausted: bool = False
    _finished: bool = False
    _closed: bool = False

    def _finish(self, outcome: AttemptOutcome, error_code: str | None) -> None:
        if self._finished:
            return
        self._finished = True
        successful = outcome == "success"
        body_sha256 = self._digest.hexdigest() if successful else None
        record = DurableAttemptFinishedV2(
            schema_version="0.2.0",
            record_type="attempt_finished",
            record_id=f"attempt-{self._started.attempt_ordinal:04d}-finish",
            authorization_id=self._started.authorization_id,
            run_id=self._started.run_id,
            plan_id=self._started.plan_id,
            sequence=self._ledger.next_sequence,
            previous_record_sha256=self._ledger.ledger_head_sha256,
            recorded_at=self._utc_clock(),
            attempt_id=self._started.attempt_id,
            attempt_ordinal=self._started.attempt_ordinal,
            outcome=outcome,
            status_code=self.status_code,
            accepted_bytes=self._accepted_bytes,
            body_sha256=body_sha256,
            error_code=error_code,
            response_headers=safe_response_headers(self.headers),
        )
        self._ledger.append(record)
        self._on_finished(self._started, outcome)

    def iter_bytes(self) -> Iterable[bytes]:
        try:
            for chunk in self._response.iter_bytes():
                self._accepted_bytes += len(chunk)
                self._digest.update(chunk)
                yield chunk
        except KeyboardInterrupt:
            self._finish("interrupted", "body_interrupted")
            raise
        except BaseException as error:
            self._finish("rejected", f"body_{type(error).__name__}")
            raise
        self._body_exhausted = True
        if self.status_code in {301, 302, 303, 307, 308}:
            self._finish("redirect", "http_redirect")
        elif self.status_code in {429, 500, 502, 503, 504}:
            self._finish("retryable_failure", "transient_http_status")
        elif not 200 <= self.status_code < 300:
            self._finish("rejected", "http_status_rejected")

    def mark_accepted(self) -> None:
        """Commit success only after the engine validates the complete body contract."""

        if self._closed or self._finished:
            raise SealedTransportPolicyError("attempt cannot be accepted after closure or finish")
        if not self._body_exhausted:
            raise SealedTransportPolicyError(
                "attempt body must be fully consumed before acceptance"
            )
        if not 200 <= self.status_code < 300:
            raise SealedTransportPolicyError("only a 2xx response body may be accepted")
        self._finish("success", None)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        except BaseException as error:
            self._finish("rejected", f"close_{type(error).__name__}")
            raise
        if not self._finished:
            if self.status_code in {301, 302, 303, 307, 308}:
                self._finish("redirect", "http_redirect")
            elif self.status_code in {429, 500, 502, 503, 504}:
                self._finish("retryable_failure", "transient_http_status")
            elif 200 <= self.status_code < 300:
                self._finish("rejected", "body_not_accepted")
            else:
                self._finish("rejected", "body_not_fully_consumed")


class DurableAttemptTransport:
    """Append a durable reservation before every underlying transport call."""

    follows_redirects = False

    def __init__(
        self,
        *,
        transport: StreamingTransport,
        ledger: ManifestLedgerStore,
        approved_hosts: frozenset[str],
        reviewed_landing_urls: Mapping[int, str],
        reviewed_pdf_urls: Mapping[int, str],
        utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if transport.follows_redirects:
            raise SealedTransportPolicyError("underlying transport must not follow redirects")
        self._transport = transport
        self._ledger = ledger
        self._approved_hosts = approved_hosts
        self._landing_urls = dict(reviewed_landing_urls)
        self._pdf_urls = dict(reviewed_pdf_urls)
        self._utc_clock = utc_clock
        self._report_number: int | None = None
        self._pending_continuations: dict[
            tuple[int, RequestKind], tuple[str, Literal["redirect", "retry"]]
        ] = {}
        self.last_completed_attempt_id: str | None = None

    def _register_continuation(
        self,
        started: DurableAttemptStartedV2,
        outcome: AttemptOutcome,
    ) -> None:
        key = (started.report_number, started.request_kind)
        if outcome == "redirect":
            self._pending_continuations[key] = (started.attempt_id, "redirect")
        elif outcome == "retryable_failure":
            self._pending_continuations[key] = (started.attempt_id, "retry")

    def set_report_context(self, report_number: int) -> None:
        if report_number not in self._landing_urls or report_number not in self._pdf_urls:
            raise SealedTransportPolicyError("report context is outside the exact reviewed pilot")
        self._report_number = report_number

    def _reviewed_url(self, request_kind: RequestKind, requested_url: str) -> str:
        if self._report_number is None:
            raise SealedTransportPolicyError("report context must be sealed before transport use")
        if request_kind == "landing_html":
            return self._landing_urls[self._report_number]
        if request_kind == "pdf":
            return self._pdf_urls[self._report_number]
        requested = canonicalize_acquisition_url(requested_url, self._approved_hosts)
        if requested.wire_target != "/robots.txt":
            raise SealedTransportPolicyError("robots request must use the origin robots.txt path")
        return requested_url

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> _DurableResponse:
        if timeout_seconds != 30:
            raise SealedTransportPolicyError(
                "attempt transport timeout must remain exactly 30 seconds"
            )
        if self._report_number is None:
            raise SealedTransportPolicyError("report context must be sealed before transport use")
        kind = _request_kind(headers)
        reviewed = canonicalize_acquisition_url(self._reviewed_url(kind, url), self._approved_hosts)
        requested = canonicalize_acquisition_url(url, self._approved_hosts)
        if requested.wire_target != reviewed.wire_target:
            raise SealedTransportPolicyError(
                "request or redirect changes the reviewed canonical path"
            )
        prior_at_url = sum(
            isinstance(record, DurableAttemptStartedV2)
            and record.request_kind == kind
            and record.normalized_url == requested.normalized_url
            for record in self._ledger.records
        )
        if prior_at_url >= 3:
            raise SealedTransportPolicyError(
                "request retry cap is already exhausted in durable state"
            )
        ordinal = self._ledger.consumed_attempts + 1
        attempt_id = f"attempt-{ordinal:04d}"
        continuation = self._pending_continuations.pop(
            (self._report_number, kind),
            None,
        )
        started = DurableAttemptStartedV2(
            schema_version="0.2.0",
            record_type="attempt_started",
            record_id=f"{attempt_id}-start",
            authorization_id=self._ledger.authorization_id,
            run_id=self._ledger.run_id,
            plan_id=self._ledger.plan_id,
            sequence=self._ledger.next_sequence,
            previous_record_sha256=self._ledger.ledger_head_sha256,
            recorded_at=self._utc_clock(),
            attempt_id=attempt_id,
            attempt_ordinal=ordinal,
            report_number=self._report_number,
            request_kind=kind,
            source_url_sha256=hashlib.sha256(url.encode("utf-8")).hexdigest(),
            normalized_url=requested.normalized_url,
            wire_target=requested.wire_target,
            reserved_bytes=_RESERVATIONS[kind],
            continued_from_attempt_id=continuation[0] if continuation is not None else None,
            continuation_reason=continuation[1] if continuation is not None else None,
        )
        self._ledger.append(started)
        try:
            response = self._transport.request(
                url,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
        except BaseException as error:
            outcome: AttemptOutcome = (
                "interrupted" if isinstance(error, KeyboardInterrupt) else "retryable_failure"
            )
            finished = DurableAttemptFinishedV2(
                schema_version="0.2.0",
                record_type="attempt_finished",
                record_id=f"{attempt_id}-finish",
                authorization_id=started.authorization_id,
                run_id=started.run_id,
                plan_id=started.plan_id,
                sequence=self._ledger.next_sequence,
                previous_record_sha256=self._ledger.ledger_head_sha256,
                recorded_at=self._utc_clock(),
                attempt_id=attempt_id,
                attempt_ordinal=ordinal,
                outcome=outcome,
                status_code=None,
                accepted_bytes=0,
                body_sha256=None,
                error_code=f"transport_{type(error).__name__}",
                response_headers=None,
            )
            self._ledger.append(finished)
            self._register_continuation(started, outcome)
            self.last_completed_attempt_id = attempt_id
            raise
        wrapped = _DurableResponse(
            status_code=response.status_code,
            headers=response.headers,
            _response=response,
            _ledger=self._ledger,
            _started=started,
            _utc_clock=self._utc_clock,
            _digest=hashlib.sha256(),
            _on_finished=self._register_continuation,
        )
        self.last_completed_attempt_id = attempt_id
        return wrapped
