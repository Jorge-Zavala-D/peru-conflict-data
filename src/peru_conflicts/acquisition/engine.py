"""Transport-neutral future acquisition core, exercised only with injected fakes in M1-03A."""

from __future__ import annotations

import email.utils
import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol, cast
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.acquisition.models import (
    SAFE_RATE_LIMIT_HEADER_NAMES,
    AcquisitionAttemptOutcome,
    AcquisitionAttemptReceipt,
    AcquisitionFailureReceipt,
    AcquisitionFailureStage,
    AcquisitionRequestKind,
    SafeRateLimitHeader,
    SafeResponseHeaders,
)
from peru_conflicts.acquisition.policy import (
    AttemptBudget,
    AttemptBudgetExhausted,
    NetworkAccessGrant,
    SerialScheduler,
    validate_redirect_target,
    validate_url,
)
from peru_conflicts.discovery.settings import AUTHORITATIVE_HOSTS

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
_ROBOTS_MAX_BYTES = 500_000
_LANDING_HTML_MAX_BYTES = 2_000_000
_PDF_MAGIC = b"%PDF-"


class StreamingResponse(Protocol):
    """Header-first response exposed by an injected future transport."""

    status_code: int
    headers: Mapping[str, str]

    def iter_bytes(self) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class StreamingTransport(Protocol):
    """Injected interface; M1-03A deliberately provides no live implementation."""

    follows_redirects: bool

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> StreamingResponse: ...


class AcquisitionEngineError(RuntimeError):
    """Base error for future acquisition logic."""


class RobotsDenied(AcquisitionEngineError):
    """robots.txt disallowed the requested source URL."""


class ResponseRejected(AcquisitionEngineError):
    """A response failed the reviewed validation contract."""


class TransportFailure(AcquisitionEngineError):
    """All permitted attempts ended in transport errors."""


class PilotScopeError(AcquisitionEngineError):
    """A requested report/URL pair is outside the reviewed pilot capability."""


class TemporaryPathBoundaryError(AcquisitionEngineError):
    """A run-owned download path escaped or aliased its system-temp root."""


class _TransportAttemptFailed(AcquisitionEngineError):
    """Carry attempt identity across an injected transport exception."""

    def __init__(self, attempt_number: int, requested_at: datetime, error: Exception) -> None:
        super().__init__(str(error))
        self.attempt_number = attempt_number
        self.requested_at = requested_at
        self.original_error = error


class _TransportAttemptInterrupted(BaseException):
    """Carry an interrupted transport attempt to the receipt boundary."""

    def __init__(
        self, attempt_number: int, requested_at: datetime, error: KeyboardInterrupt
    ) -> None:
        super().__init__()
        self.attempt_number = attempt_number
        self.requested_at = requested_at
        self.original_error = error


@dataclass(frozen=True, slots=True)
class DownloadedObject:
    """One completely validated object in a run-owned system-temporary directory."""

    path: Path
    byte_count: int
    sha256: str
    final_url: str


@dataclass(frozen=True, slots=True)
class LandingHtmlEvidence:
    """One bounded, validated official landing-page body held only in memory."""

    body: bytes
    byte_count: int
    sha256: str
    final_url: str


@dataclass(frozen=True, slots=True)
class DownloadByteBudget:
    """Bound the aggregate complete bytes accepted during one pilot run."""

    limit: int = 500_000_000
    used: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 500_000_000:
            raise ValueError("download byte budget must be between 1 and 500000000")
        if self.used != 0:
            raise ValueError("a new download byte budget must start unused")

    def require_capacity(self, amount: int) -> None:
        if amount < 0 or self.used + amount > self.limit:
            raise ResponseRejected("response exceeds the total byte ceiling")

    def commit(self, amount: int) -> None:
        self.require_capacity(amount)
        object.__setattr__(self, "used", self.used + amount)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _media_type(headers: Mapping[str, str]) -> str:
    return (_header(headers, "Content-Type") or "").split(";", maxsplit=1)[0].strip().lower()


def _safe_exception_label(error: BaseException) -> str:
    """Retain an error class without copying secret-bearing exception text."""

    return type(error).__name__


def _sanitize_location(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    try:
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            host = parsed.hostname or "redacted-host"
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            port = f":{parsed.port}" if parsed.port is not None else ""
            sanitized = urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, "", ""))
        else:
            sanitized = urlunsplit(("", "", parsed.path, "", ""))
    except ValueError:
        sanitized = "[redacted-invalid-location]"
    return (
        _sanitize_receipt_header_value(sanitized or "[redacted-empty-location]"),
        digest,
    )


def _sanitize_receipt_header_value(value: str | None) -> str | None:
    """Retain bounded single-line evidence or a non-secret content hash."""

    if value is None:
        return None
    if len(value) <= 200 and "\r" not in value and "\n" not in value:
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"[redacted unsafe metadata sha256={digest}]"


def _safe_headers(headers: Mapping[str, str]) -> SafeResponseHeaders:
    selected_rate_limits = tuple(
        SafeRateLimitHeader.model_validate(
            {
                "name": name.lower(),
                "value": _sanitize_receipt_header_value(value),
            },
            strict=True,
        )
        for name, value in sorted(headers.items(), key=lambda item: item[0].lower())
        if name.lower() in SAFE_RATE_LIMIT_HEADER_NAMES
    )
    location_sanitized, location_sha256 = _sanitize_location(_header(headers, "Location"))
    return SafeResponseHeaders(
        content_type_original=_sanitize_receipt_header_value(_header(headers, "Content-Type")),
        content_length_original=_sanitize_receipt_header_value(_header(headers, "Content-Length")),
        content_encoding_original=_sanitize_receipt_header_value(
            _header(headers, "Content-Encoding")
        ),
        etag_original=_sanitize_receipt_header_value(_header(headers, "ETag")),
        last_modified_original=_sanitize_receipt_header_value(_header(headers, "Last-Modified")),
        retry_after_original=_sanitize_receipt_header_value(_header(headers, "Retry-After")),
        location_sanitized=location_sanitized,
        location_sha256=location_sha256,
        rate_limit_headers=selected_rate_limits,
    )


def _absolute_logical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = cast(int, getattr(path.lstat(), "st_file_attributes", 0))
    except (FileNotFoundError, OSError):
        return False
    marker = cast(int, getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return bool(marker and attributes & marker)


def _validate_temp_chain(path: Path, *, logical_boundary: Path, resolved_boundary: Path) -> None:
    if not path.is_relative_to(logical_boundary):
        raise TemporaryPathBoundaryError("download path escapes the logical system temp root")
    relative = path.relative_to(logical_boundary)
    cursor = logical_boundary
    for part in relative.parts:
        cursor /= part
        if not os.path.lexists(cursor):
            break
        if _is_reparse_point(cursor):
            raise TemporaryPathBoundaryError("download path contains a symlink or reparse point")
        if not cursor.resolve(strict=True).is_relative_to(resolved_boundary):
            raise TemporaryPathBoundaryError("download path escapes resolved system temp")
    nearest = path
    while not os.path.lexists(nearest):
        if nearest.parent == nearest:
            raise TemporaryPathBoundaryError("download path has no existing ancestor")
        nearest = nearest.parent
    if not nearest.resolve(strict=True).is_relative_to(resolved_boundary):
        raise TemporaryPathBoundaryError("download path escapes resolved system temp")


def _retry_after_seconds(value: str | None, *, now: datetime) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return 0.0
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - now).total_seconds())


class AcquisitionClient:
    """Serial, bounded downloader that can operate only through an injected transport."""

    def __init__(
        self,
        *,
        grant: NetworkAccessGrant[StreamingTransport],
        system_temp_root: Path,
        attempt_limit: int | None = None,
        total_byte_limit: int | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        grant.require_valid()
        limits = grant.limits
        if limits.concurrency != 1 or limits.retry_cap != 2:
            raise ValueError("acquisition client requires the reviewed serial retry envelope")
        if limits.timeout_seconds != 30 or limits.max_total_attempts != 60:
            raise ValueError("acquisition client requires the reviewed timeout and attempt limits")
        requested_attempt_limit = (
            limits.max_total_attempts if attempt_limit is None else attempt_limit
        )
        requested_byte_limit = (
            limits.total_download_max_bytes if total_byte_limit is None else total_byte_limit
        )
        if not 1 <= requested_attempt_limit <= limits.max_total_attempts:
            raise ValueError("attempt budget cannot exceed the reviewed total ceiling")
        if not 1 <= requested_byte_limit <= limits.total_download_max_bytes:
            raise ValueError("download byte budget cannot exceed the reviewed total ceiling")
        if grant.approved_hosts != frozenset(AUTHORITATIVE_HOSTS):
            raise ValueError("network grant hosts do not match the reviewed authority")
        if grant.transport.follows_redirects:
            raise ValueError("streaming transport must not automatically follow redirects")
        allowed_landings = dict(grant.allowed_landing_targets)
        allowed_targets = dict(grant.allowed_pdf_targets)
        logical_urls = {
            *(url for _, url in grant.allowed_landing_targets),
            *(url for _, url in grant.allowed_pdf_targets),
        }
        if (
            len(allowed_landings) != limits.max_reports
            or len(allowed_targets) != limits.max_reports
            or len(grant.allowed_landing_targets) != 10
            or len(grant.allowed_pdf_targets) != 10
            or len(logical_urls) != limits.max_urls
        ):
            raise ValueError("network grant does not contain the exact reviewed report/URL scope")
        self.approved_hosts = grant.approved_hosts
        self.plan_id = grant.plan_id
        self.allowed_landing_targets = allowed_landings
        self.allowed_pdf_targets = allowed_targets
        self.limits = limits
        system_temporary_logical = _absolute_logical(Path(tempfile.gettempdir()))
        system_temporary_resolved = system_temporary_logical.resolve(strict=True)
        self._system_temporary_logical = system_temporary_logical
        self.system_temp_root = _absolute_logical(system_temp_root)
        if not self.system_temp_root.is_relative_to(system_temporary_logical):
            raise ValueError(
                "download root must remain below the operating-system temporary directory"
            )
        _validate_temp_chain(
            self.system_temp_root,
            logical_boundary=system_temporary_logical,
            resolved_boundary=system_temporary_resolved,
        )
        self._system_temporary_resolved = system_temporary_resolved
        self._scheduler = SerialScheduler(
            delay_seconds=limits.delay_seconds,
            budget=AttemptBudget(limit=requested_attempt_limit),
            clock=monotonic_clock,
            sleep=sleeper,
        )
        self._byte_budget = DownloadByteBudget(limit=requested_byte_limit)
        self.utc_clock = utc_clock
        self.receipts: list[AcquisitionAttemptReceipt] = []
        self.failure_receipts: list[AcquisitionFailureReceipt] = []
        self._robots: dict[str, RobotFileParser] = {}
        self.transport = grant.claim_transport()

    @contextmanager
    def _lease_run_directory(self, run_id: str) -> Generator[DirectoryLease]:
        """Create and hold every temp-directory component until stream cleanup ends."""

        relative_root = self.system_temp_root.relative_to(self._system_temporary_logical)
        try:
            with ExitStack() as stack:
                current = stack.enter_context(
                    DirectoryLease.acquire(self._system_temporary_logical)
                )
                for part in relative_root.parts:
                    current = stack.enter_context(current.acquire_child(part, create=True))
                if current.resolved != self.system_temp_root.resolve(strict=True):
                    raise DirectoryLeaseError("system temporary root binding is inconsistent")
                run_directory = stack.enter_context(current.acquire_child(run_id, create=True))
                if not run_directory.resolved.is_relative_to(current.resolved):
                    raise DirectoryLeaseError("run directory escapes the system temporary root")
                yield run_directory
        except DirectoryLeaseError as error:
            raise TemporaryPathBoundaryError(
                "temporary directory could not be held safely"
            ) from error

    def _record(
        self,
        *,
        run_id: str,
        report_number: int,
        kind: AcquisitionRequestKind,
        url: str,
        attempt_number: int,
        redirect_index: int,
        requested_at: datetime,
        outcome: AcquisitionAttemptOutcome,
        status_code: int | None,
        headers: Mapping[str, str] | None,
        transferred_bytes: int,
        complete_sha256: str | None = None,
        redirect_target_url: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AcquisitionAttemptReceipt:
        receipt = AcquisitionAttemptReceipt(
            schema_version="0.1.0",
            attempt_id=f"{run_id}-attempt-{attempt_number:02d}",
            run_id=run_id,
            plan_id=self.plan_id,
            report_number=report_number,
            request_kind=kind,
            url=url,
            attempt_number=attempt_number,
            redirect_index=redirect_index,
            requested_at=requested_at,
            completed_at=self.utc_clock(),
            status_code=status_code,
            outcome=outcome,
            response_headers=_safe_headers(headers) if headers is not None else None,
            transferred_bytes=transferred_bytes,
            complete_body_sha256=complete_sha256,
            redirect_target_url=redirect_target_url,
            error_code=error_code,
            error_message=error_message,
        )
        self.receipts.append(receipt)
        return receipt

    def _record_failure(
        self,
        *,
        run_id: str,
        report_number: int,
        stage: AcquisitionFailureStage,
        url: str,
        error_code: str,
        error_message: str,
        transferred_bytes: int = 0,
        related_attempt_id: str | None = None,
        cleanup_completed: bool = True,
    ) -> AcquisitionFailureReceipt:
        receipt = AcquisitionFailureReceipt(
            schema_version="0.1.0",
            failure_id=f"{run_id}-failure-{len(self.failure_receipts) + 1:02d}",
            run_id=run_id,
            plan_id=self.plan_id,
            report_number=report_number,
            stage=stage,
            url=url,
            occurred_at=self.utc_clock(),
            error_code=error_code,
            error_message=error_message or error_code,
            related_attempt_id=related_attempt_id,
            transferred_bytes=transferred_bytes,
            cleanup_completed=cleanup_completed,
        )
        self.failure_receipts.append(receipt)
        return receipt

    def _safe_close(
        self,
        response: StreamingResponse,
        *,
        run_id: str,
        report_number: int,
        url: str,
    ) -> None:
        """Preserve a close failure without masking the primary request outcome."""

        try:
            response.close()
        except KeyboardInterrupt:
            related = self.receipts[-1].attempt_id if self.receipts else None
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.RESPONSE_CLOSE,
                url=url,
                error_code="response_close_interrupted",
                error_message="response close was interrupted",
                related_attempt_id=related,
                cleanup_completed=False,
            )
            raise
        except Exception as error:
            related = self.receipts[-1].attempt_id if self.receipts else None
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.RESPONSE_CLOSE,
                url=url,
                error_code="response_close_failure",
                error_message=_safe_exception_label(error),
                related_attempt_id=related,
                cleanup_completed=False,
            )

    def _cleanup_temp_path(
        self,
        path: Path,
        *,
        run_id: str,
        report_number: int,
        url: str,
        related_attempt_id: str,
    ) -> None:
        try:
            expected_parent = self.system_temp_root / run_id
            if _absolute_logical(path.parent) != expected_parent:
                raise TemporaryPathBoundaryError(
                    "temporary cleanup path does not match the reviewed run directory"
                )
            with self._lease_run_directory(run_id) as run_directory:
                run_directory.unlink_child(path.name, missing_ok=True)
        except (DirectoryLeaseError, OSError, TemporaryPathBoundaryError) as error:
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.TEMP_CLEANUP,
                url=url,
                error_code="temporary_cleanup_failure",
                error_message=_safe_exception_label(error),
                related_attempt_id=related_attempt_id,
                cleanup_completed=False,
            )

    def _transport_request(
        self,
        *,
        url: str,
        kind: AcquisitionRequestKind,
        requested_wait: float = 0.0,
    ) -> tuple[int, datetime, StreamingResponse]:
        attempt_number = self._scheduler.before_attempt(requested_wait=requested_wait)
        requested_at = self.utc_clock()
        if kind is AcquisitionRequestKind.ROBOTS:
            accept = "text/plain"
        elif kind is AcquisitionRequestKind.LANDING_HTML:
            accept = "text/html, application/xhtml+xml"
        else:
            accept = "application/pdf"
        try:
            response = self.transport.request(
                url,
                headers={
                    "User-Agent": "peru-conflict-data-m1-acquisition/0.1 (+research)",
                    "Accept": accept,
                    "Accept-Encoding": "identity",
                },
                timeout_seconds=self.limits.timeout_seconds,
            )
        except KeyboardInterrupt as error:
            raise _TransportAttemptInterrupted(attempt_number, requested_at, error) from error
        except Exception as error:
            raise _TransportAttemptFailed(attempt_number, requested_at, error) from error
        return attempt_number, requested_at, response

    def _read_robots_response(
        self,
        *,
        response: StreamingResponse,
        run_id: str,
        report_number: int,
        robots_url: str,
        attempt_number: int,
        requested_at: datetime,
    ) -> bytes:
        if response.status_code != 200:
            self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.ROBOTS,
                url=robots_url,
                attempt_number=attempt_number,
                redirect_index=0,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=0,
                error_code="robots_http_status",
            )
            raise ResponseRejected(f"robots.txt returned HTTP {response.status_code}")
        if _media_type(response.headers) != "text/plain":
            self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.ROBOTS,
                url=robots_url,
                attempt_number=attempt_number,
                redirect_index=0,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=0,
                error_code="robots_content_type",
            )
            raise ResponseRejected("robots.txt Content-Type is not text/plain")
        body = bytearray()
        try:
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > _ROBOTS_MAX_BYTES:
                    raise ResponseRejected("robots.txt exceeds its byte ceiling")
        except KeyboardInterrupt:
            attempt = self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.ROBOTS,
                url=robots_url,
                attempt_number=attempt_number,
                redirect_index=0,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="robots_body_interrupted",
            )
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.ROBOTS_BODY,
                url=robots_url,
                error_code="robots_body_interrupted",
                error_message="robots.txt body iteration was interrupted",
                transferred_bytes=len(body),
                related_attempt_id=attempt.attempt_id,
            )
            raise
        except ResponseRejected as error:
            attempt = self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.ROBOTS,
                url=robots_url,
                attempt_number=attempt_number,
                redirect_index=0,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="robots_body_too_large",
                error_message=str(error),
            )
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.ROBOTS_BODY,
                url=robots_url,
                error_code="robots_body_too_large",
                error_message=str(error),
                transferred_bytes=len(body),
                related_attempt_id=attempt.attempt_id,
            )
            raise
        except Exception as error:
            message = _safe_exception_label(error)
            attempt = self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.ROBOTS,
                url=robots_url,
                attempt_number=attempt_number,
                redirect_index=0,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="robots_body_stream_failure",
                error_message=message,
            )
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.ROBOTS_BODY,
                url=robots_url,
                error_code="robots_body_stream_failure",
                error_message=message,
                transferred_bytes=len(body),
                related_attempt_id=attempt.attempt_id,
            )
            raise ResponseRejected("robots.txt body stream failed") from error
        digest = hashlib.sha256(body).hexdigest()
        self._record(
            run_id=run_id,
            report_number=report_number,
            kind=AcquisitionRequestKind.ROBOTS,
            url=robots_url,
            attempt_number=attempt_number,
            redirect_index=0,
            requested_at=requested_at,
            outcome=AcquisitionAttemptOutcome.SUCCESS,
            status_code=response.status_code,
            headers=response.headers,
            transferred_bytes=len(body),
            complete_sha256=digest,
        )
        return bytes(body)

    def _ensure_robots(self, url: str, *, run_id: str, report_number: int) -> None:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots.get(origin)
        if parser is None:
            robots_url = f"{origin}/robots.txt"
            retry_wait = 0.0
            body: bytes | None = None
            for retry_index in range(self.limits.retry_cap + 1):
                response: StreamingResponse | None = None
                try:
                    attempt_number, requested_at, response = self._transport_request(
                        url=robots_url,
                        kind=AcquisitionRequestKind.ROBOTS,
                        requested_wait=retry_wait,
                    )
                except _TransportAttemptInterrupted as interruption:
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.ROBOTS,
                        url=robots_url,
                        attempt_number=interruption.attempt_number,
                        redirect_index=0,
                        requested_at=interruption.requested_at,
                        outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                        status_code=None,
                        headers=None,
                        transferred_bytes=0,
                        error_code="transport_interrupted",
                    )
                    raise interruption.original_error from interruption
                except _TransportAttemptFailed as failure:
                    final = retry_index == self.limits.retry_cap
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.ROBOTS,
                        url=robots_url,
                        attempt_number=failure.attempt_number,
                        redirect_index=0,
                        requested_at=failure.requested_at,
                        outcome=(
                            AcquisitionAttemptOutcome.REJECTED
                            if final
                            else AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                        ),
                        status_code=None,
                        headers=None,
                        transferred_bytes=0,
                        error_code="robots_transport_error",
                        error_message=_safe_exception_label(failure.original_error),
                    )
                    if final:
                        raise TransportFailure(
                            "robots transport failed after three attempts"
                        ) from failure.original_error
                    retry_wait = self.limits.delay_seconds
                    continue
                try:
                    if response.status_code in _TRANSIENT_STATUSES:
                        final = retry_index == self.limits.retry_cap
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.ROBOTS,
                            url=robots_url,
                            attempt_number=attempt_number,
                            redirect_index=0,
                            requested_at=requested_at,
                            outcome=(
                                AcquisitionAttemptOutcome.REJECTED
                                if final
                                else AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                            ),
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="robots_transient_http_status",
                        )
                        if final:
                            raise ResponseRejected("robots transient response exceeded retry cap")
                        retry_wait = max(
                            self.limits.delay_seconds,
                            _retry_after_seconds(
                                _header(response.headers, "Retry-After"), now=self.utc_clock()
                            ),
                        )
                        continue
                    body = self._read_robots_response(
                        response=response,
                        run_id=run_id,
                        report_number=report_number,
                        robots_url=robots_url,
                        attempt_number=attempt_number,
                        requested_at=requested_at,
                    )
                    break
                finally:
                    self._safe_close(
                        response,
                        run_id=run_id,
                        report_number=report_number,
                        url=robots_url,
                    )
            if body is None:
                raise ResponseRejected("robots.txt was not accepted")
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
            self._robots[origin] = parser
        if not parser.can_fetch("peru-conflict-data-m1-acquisition/0.1 (+research)", url):
            self._record_failure(
                run_id=run_id,
                report_number=report_number,
                stage=AcquisitionFailureStage.ROBOTS_POLICY,
                url=url,
                error_code="robots_policy_denied",
                error_message="robots.txt disallows the reviewed acquisition URL",
            )
            raise RobotsDenied(f"robots.txt disallows acquisition URL: {url}")

    def _validate_pdf_headers(self, response: StreamingResponse) -> int | None:
        if response.status_code != 200:
            raise ResponseRejected(f"PDF response requires HTTP 200, got {response.status_code}")
        if _media_type(response.headers) != "application/pdf":
            raise ResponseRejected("PDF response Content-Type is not application/pdf")
        encoding = (_header(response.headers, "Content-Encoding") or "identity").strip().lower()
        if encoding != "identity":
            raise ResponseRejected("PDF response Content-Encoding must be identity")
        original_length = _header(response.headers, "Content-Length")
        if original_length is None:
            return None
        try:
            content_length = int(original_length)
        except ValueError as error:
            raise ResponseRejected("PDF Content-Length is not a non-negative integer") from error
        if content_length < 0:
            raise ResponseRejected("PDF Content-Length is not a non-negative integer")
        if content_length < self.limits.per_file_min_bytes:
            raise ResponseRejected("PDF Content-Length is below the per-file minimum")
        if content_length > self.limits.per_file_max_bytes:
            raise ResponseRejected("PDF Content-Length exceeds the per-file maximum")
        self._byte_budget.require_capacity(content_length)
        return content_length

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if (
            not run_id.strip()
            or len(run_id) > 100
            or "/" in run_id
            or "\\" in run_id
            or run_id in {".", ".."}
        ):
            raise ValueError("run_id must be a path-safe identifier")

    def _read_landing_html(
        self,
        *,
        response: StreamingResponse,
        url: str,
        run_id: str,
        report_number: int,
        attempt_number: int,
        redirect_index: int,
        requested_at: datetime,
    ) -> LandingHtmlEvidence:
        if response.status_code != 200:
            raise ResponseRejected(
                f"landing HTML response requires HTTP 200, got {response.status_code}"
            )
        if _media_type(response.headers) not in {"text/html", "application/xhtml+xml"}:
            raise ResponseRejected("landing response Content-Type is not approved HTML/XHTML")
        encoding = (_header(response.headers, "Content-Encoding") or "identity").strip().lower()
        if encoding != "identity":
            raise ResponseRejected("landing response Content-Encoding must be identity")
        original_length = _header(response.headers, "Content-Length")
        expected_length: int | None = None
        if original_length is not None:
            try:
                expected_length = int(original_length)
            except ValueError as error:
                raise ResponseRejected(
                    "landing Content-Length is not a non-negative integer"
                ) from error
            if expected_length < 0:
                raise ResponseRejected("landing Content-Length is not a non-negative integer")
            if expected_length > _LANDING_HTML_MAX_BYTES:
                raise ResponseRejected("landing Content-Length exceeds the HTML byte ceiling")

        body = bytearray()
        try:
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > _LANDING_HTML_MAX_BYTES:
                    raise ResponseRejected("landing body exceeds the HTML byte ceiling")
            if expected_length is not None and len(body) != expected_length:
                raise ResponseRejected("landing byte count does not match Content-Length")
        except KeyboardInterrupt:
            self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.LANDING_HTML,
                url=url,
                attempt_number=attempt_number,
                redirect_index=redirect_index,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="landing_body_interrupted",
            )
            raise
        except ResponseRejected as error:
            self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.LANDING_HTML,
                url=url,
                attempt_number=attempt_number,
                redirect_index=redirect_index,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="landing_response_rejected",
                error_message=str(error),
            )
            raise
        except Exception as error:
            message = _safe_exception_label(error)
            self._record(
                run_id=run_id,
                report_number=report_number,
                kind=AcquisitionRequestKind.LANDING_HTML,
                url=url,
                attempt_number=attempt_number,
                redirect_index=redirect_index,
                requested_at=requested_at,
                outcome=AcquisitionAttemptOutcome.REJECTED,
                status_code=response.status_code,
                headers=response.headers,
                transferred_bytes=len(body),
                error_code="landing_body_stream_failure",
                error_message=message,
            )
            raise ResponseRejected("landing body stream failed") from error

        rendered = bytes(body)
        digest = hashlib.sha256(rendered).hexdigest()
        self._record(
            run_id=run_id,
            report_number=report_number,
            kind=AcquisitionRequestKind.LANDING_HTML,
            url=url,
            attempt_number=attempt_number,
            redirect_index=redirect_index,
            requested_at=requested_at,
            outcome=AcquisitionAttemptOutcome.SUCCESS,
            status_code=response.status_code,
            headers=response.headers,
            transferred_bytes=len(rendered),
            complete_sha256=digest,
        )
        return LandingHtmlEvidence(
            body=rendered,
            byte_count=len(rendered),
            sha256=digest,
            final_url=url,
        )

    def _stream_pdf(
        self,
        *,
        response: StreamingResponse,
        url: str,
        run_id: str,
        report_number: int,
        attempt_number: int,
        redirect_index: int,
        requested_at: datetime,
    ) -> DownloadedObject:
        expected_length = self._validate_pdf_headers(response)
        if "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a path-safe identifier")
        object_token = uuid.uuid4().hex
        partial_name = f"report-{report_number}-{object_token}.pdf.partial"
        complete_name = partial_name.removesuffix(".partial")
        transferred = 0
        digest = hashlib.sha256()
        prefix = bytearray()
        with self._lease_run_directory(run_id) as run_directory:

            def cleanup_bound(name: str, *, related_attempt_id: str) -> None:
                try:
                    run_directory.unlink_child(name, missing_ok=True)
                except DirectoryLeaseError as error:
                    self._record_failure(
                        run_id=run_id,
                        report_number=report_number,
                        stage=AcquisitionFailureStage.TEMP_CLEANUP,
                        url=url,
                        error_code="temporary_cleanup_failure",
                        error_message=_safe_exception_label(error),
                        related_attempt_id=related_attempt_id,
                        cleanup_completed=False,
                    )

            try:
                with run_directory.open_child_exclusive(partial_name) as output:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        run_directory.require_bound()
                        transferred += len(chunk)
                        if transferred > self.limits.per_file_max_bytes:
                            raise ResponseRejected("PDF stream exceeds the per-file maximum")
                        self._byte_budget.require_capacity(transferred)
                        if len(prefix) < len(_PDF_MAGIC):
                            prefix.extend(chunk[: len(_PDF_MAGIC) - len(prefix)])
                            if not _PDF_MAGIC.startswith(bytes(prefix)):
                                raise ResponseRejected("PDF magic signature is invalid")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if bytes(prefix) != _PDF_MAGIC:
                    raise ResponseRejected("PDF magic signature is incomplete or invalid")
                if transferred < self.limits.per_file_min_bytes:
                    raise ResponseRejected("PDF stream is below the per-file minimum")
                if expected_length is not None and transferred != expected_length:
                    raise ResponseRejected("PDF byte count does not match Content-Length")
                observed_sha256 = digest.hexdigest()
                self._byte_budget.commit(transferred)
                run_directory.rename_child_no_replace(partial_name, complete_name)
                self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=url,
                    attempt_number=attempt_number,
                    redirect_index=redirect_index,
                    requested_at=requested_at,
                    outcome=AcquisitionAttemptOutcome.SUCCESS,
                    status_code=response.status_code,
                    headers=response.headers,
                    transferred_bytes=transferred,
                    complete_sha256=observed_sha256,
                )
                return DownloadedObject(
                    path=run_directory.child_path(complete_name),
                    byte_count=transferred,
                    sha256=observed_sha256,
                    final_url=url,
                )
            except DirectoryLeaseError:
                raise
            except KeyboardInterrupt:
                attempt = self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=url,
                    attempt_number=attempt_number,
                    redirect_index=redirect_index,
                    requested_at=requested_at,
                    outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                    status_code=response.status_code,
                    headers=response.headers,
                    transferred_bytes=transferred,
                    error_code="stream_interrupted",
                )
                cleanup_bound(complete_name, related_attempt_id=attempt.attempt_id)
                raise
            except ResponseRejected as error:
                attempt = self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=url,
                    attempt_number=attempt_number,
                    redirect_index=redirect_index,
                    requested_at=requested_at,
                    outcome=AcquisitionAttemptOutcome.REJECTED,
                    status_code=response.status_code,
                    headers=response.headers,
                    transferred_bytes=transferred,
                    error_code="response_rejected",
                    error_message=_safe_exception_label(error),
                )
                cleanup_bound(complete_name, related_attempt_id=attempt.attempt_id)
                raise
            except Exception as error:
                attempt = self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=url,
                    attempt_number=attempt_number,
                    redirect_index=redirect_index,
                    requested_at=requested_at,
                    outcome=AcquisitionAttemptOutcome.REJECTED,
                    status_code=response.status_code,
                    headers=response.headers,
                    transferred_bytes=transferred,
                    error_code="stream_failure",
                    error_message=_safe_exception_label(error),
                )
                cleanup_bound(complete_name, related_attempt_id=attempt.attempt_id)
                raise ResponseRejected("PDF stream failed before completion") from error
            finally:
                if self.receipts:
                    cleanup_bound(partial_name, related_attempt_id=self.receipts[-1].attempt_id)

    def fetch_landing_html(
        self, url: str, *, run_id: str, report_number: int
    ) -> LandingHtmlEvidence:
        """Fetch one exact reviewed landing page through the bounded fakeable transport."""

        self._validate_run_id(run_id)
        current_url = validate_url(url, self.approved_hosts)
        expected_url = self.allowed_landing_targets.get(report_number)
        if expected_url is None or current_url != validate_url(expected_url, self.approved_hosts):
            raise PilotScopeError("URL does not match the reviewed landing-page target")
        seen = frozenset((current_url,))
        redirect_index = 0
        retry_wait = 0.0
        attempts_at_url = 0
        while True:
            self._ensure_robots(current_url, run_id=run_id, report_number=report_number)
            response_url = current_url
            response: StreamingResponse | None = None
            attempt_number = 0
            requested_at = self.utc_clock()
            try:
                attempt_number, requested_at, response = self._transport_request(
                    url=current_url,
                    kind=AcquisitionRequestKind.LANDING_HTML,
                    requested_wait=retry_wait,
                )
            except AttemptBudgetExhausted:
                raise
            except _TransportAttemptInterrupted as interruption:
                self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.LANDING_HTML,
                    url=current_url,
                    attempt_number=interruption.attempt_number,
                    redirect_index=redirect_index,
                    requested_at=interruption.requested_at,
                    outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                    status_code=None,
                    headers=None,
                    transferred_bytes=0,
                    error_code="transport_interrupted",
                )
                raise interruption.original_error from interruption
            except _TransportAttemptFailed as failure:
                attempts_at_url += 1
                self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.LANDING_HTML,
                    url=current_url,
                    attempt_number=failure.attempt_number,
                    redirect_index=redirect_index,
                    requested_at=failure.requested_at,
                    outcome=(
                        AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                        if attempts_at_url <= self.limits.retry_cap
                        else AcquisitionAttemptOutcome.REJECTED
                    ),
                    status_code=None,
                    headers=None,
                    transferred_bytes=0,
                    error_code="transport_error",
                    error_message=_safe_exception_label(failure.original_error),
                )
                if attempts_at_url > self.limits.retry_cap:
                    raise TransportFailure(
                        "landing transport failed after three attempts"
                    ) from failure.original_error
                retry_wait = self.limits.delay_seconds
                continue

            try:
                if response.status_code in _TRANSIENT_STATUSES:
                    attempts_at_url += 1
                    retry_wait = max(
                        self.limits.delay_seconds,
                        _retry_after_seconds(
                            _header(response.headers, "Retry-After"), now=self.utc_clock()
                        ),
                    )
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.LANDING_HTML,
                        url=current_url,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                        outcome=(
                            AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                            if attempts_at_url <= self.limits.retry_cap
                            else AcquisitionAttemptOutcome.REJECTED
                        ),
                        status_code=response.status_code,
                        headers=response.headers,
                        transferred_bytes=0,
                        error_code="transient_http_status",
                    )
                    if attempts_at_url > self.limits.retry_cap:
                        raise ResponseRejected("transient landing response exceeded retry cap")
                    continue
                if response.status_code in _REDIRECT_STATUSES:
                    location = _header(response.headers, "Location")
                    if location is None:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.LANDING_HTML,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="redirect_without_location",
                        )
                        raise ResponseRejected("redirect response has no Location header")
                    try:
                        target = validate_redirect_target(
                            current_url=current_url,
                            location=location,
                            approved_hosts=self.approved_hosts,
                            seen=seen,
                            redirect_hop=redirect_index + 1,
                            max_redirects=self.limits.max_redirects_per_url,
                        )
                    except Exception as error:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.LANDING_HTML,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="redirect_rejected",
                            error_message=str(error),
                        )
                        raise
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.LANDING_HTML,
                        url=current_url,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                        outcome=AcquisitionAttemptOutcome.REDIRECT,
                        status_code=response.status_code,
                        headers=response.headers,
                        transferred_bytes=0,
                        redirect_target_url=target,
                    )
                    current_url = target
                    seen = seen | {target}
                    redirect_index += 1
                    attempts_at_url = 0
                    retry_wait = 0.0
                    continue
                try:
                    return self._read_landing_html(
                        response=response,
                        url=current_url,
                        run_id=run_id,
                        report_number=report_number,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                    )
                except ResponseRejected as error:
                    if not self.receipts or self.receipts[-1].attempt_number != attempt_number:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.LANDING_HTML,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="landing_response_rejected",
                            error_message=str(error),
                        )
                    raise
            finally:
                self._safe_close(
                    response,
                    run_id=run_id,
                    report_number=report_number,
                    url=response_url,
                )

    def fetch_pdf(self, url: str, *, run_id: str, report_number: int) -> DownloadedObject:
        """Validate robots/redirects and stream one synthetic-or-future PDF object."""

        self._validate_run_id(run_id)
        current_url = validate_url(url, self.approved_hosts)
        expected_url = self.allowed_pdf_targets.get(report_number)
        if expected_url is None or current_url != validate_url(expected_url, self.approved_hosts):
            raise PilotScopeError("URL does not match the reviewed report/URL target")
        seen = frozenset((current_url,))
        redirect_index = 0
        retry_wait = 0.0
        attempts_at_url = 0
        while True:
            self._ensure_robots(current_url, run_id=run_id, report_number=report_number)
            response_url = current_url
            response: StreamingResponse | None = None
            downloaded: DownloadedObject | None = None
            attempt_number = 0
            requested_at = self.utc_clock()
            try:
                attempt_number, requested_at, response = self._transport_request(
                    url=current_url,
                    kind=AcquisitionRequestKind.PDF,
                    requested_wait=retry_wait,
                )
            except AttemptBudgetExhausted:
                raise
            except _TransportAttemptInterrupted as interruption:
                self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=current_url,
                    attempt_number=interruption.attempt_number,
                    redirect_index=redirect_index,
                    requested_at=interruption.requested_at,
                    outcome=AcquisitionAttemptOutcome.INTERRUPTED,
                    status_code=None,
                    headers=None,
                    transferred_bytes=0,
                    error_code="transport_interrupted",
                )
                raise interruption.original_error from interruption
            except _TransportAttemptFailed as failure:
                attempts_at_url += 1
                self._record(
                    run_id=run_id,
                    report_number=report_number,
                    kind=AcquisitionRequestKind.PDF,
                    url=current_url,
                    attempt_number=failure.attempt_number,
                    redirect_index=redirect_index,
                    requested_at=failure.requested_at,
                    outcome=(
                        AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                        if attempts_at_url <= self.limits.retry_cap
                        else AcquisitionAttemptOutcome.REJECTED
                    ),
                    status_code=None,
                    headers=None,
                    transferred_bytes=0,
                    error_code="transport_error",
                    error_message=_safe_exception_label(failure.original_error),
                )
                if attempts_at_url > self.limits.retry_cap:
                    raise TransportFailure(
                        "PDF transport failed after three attempts"
                    ) from failure.original_error
                retry_wait = self.limits.delay_seconds
                continue

            try:
                if response.status_code in _TRANSIENT_STATUSES:
                    attempts_at_url += 1
                    retry_wait = max(
                        self.limits.delay_seconds,
                        _retry_after_seconds(
                            _header(response.headers, "Retry-After"), now=self.utc_clock()
                        ),
                    )
                    outcome = (
                        AcquisitionAttemptOutcome.RETRYABLE_FAILURE
                        if attempts_at_url <= self.limits.retry_cap
                        else AcquisitionAttemptOutcome.REJECTED
                    )
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.PDF,
                        url=current_url,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                        outcome=outcome,
                        status_code=response.status_code,
                        headers=response.headers,
                        transferred_bytes=0,
                        error_code="transient_http_status",
                    )
                    if attempts_at_url > self.limits.retry_cap:
                        raise ResponseRejected("transient PDF response exceeded retry cap")
                    continue
                if response.status_code in _REDIRECT_STATUSES:
                    location = _header(response.headers, "Location")
                    if location is None:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.PDF,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="redirect_without_location",
                        )
                        raise ResponseRejected("redirect response has no Location header")
                    try:
                        target = validate_redirect_target(
                            current_url=current_url,
                            location=location,
                            approved_hosts=self.approved_hosts,
                            seen=seen,
                            redirect_hop=redirect_index + 1,
                            max_redirects=self.limits.max_redirects_per_url,
                        )
                    except Exception as error:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.PDF,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="redirect_rejected",
                            error_message=str(error),
                        )
                        raise
                    self._record(
                        run_id=run_id,
                        report_number=report_number,
                        kind=AcquisitionRequestKind.PDF,
                        url=current_url,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                        outcome=AcquisitionAttemptOutcome.REDIRECT,
                        status_code=response.status_code,
                        headers=response.headers,
                        transferred_bytes=0,
                        redirect_target_url=target,
                    )
                    current_url = target
                    seen = seen | {target}
                    redirect_index += 1
                    attempts_at_url = 0
                    retry_wait = 0.0
                    continue
                try:
                    downloaded = self._stream_pdf(
                        response=response,
                        url=current_url,
                        run_id=run_id,
                        report_number=report_number,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_at=requested_at,
                    )
                    return downloaded
                except TemporaryPathBoundaryError as error:
                    if not self.receipts or self.receipts[-1].attempt_number != attempt_number:
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.PDF,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code="temporary_path_boundary",
                            error_message=str(error),
                        )
                    raise
                except ResponseRejected as error:
                    if not self.receipts or self.receipts[-1].attempt_number != attempt_number:
                        message = str(error)
                        error_code = (
                            "rejected_content_type"
                            if "Content-Type" in message
                            else "response_rejected"
                        )
                        self._record(
                            run_id=run_id,
                            report_number=report_number,
                            kind=AcquisitionRequestKind.PDF,
                            url=current_url,
                            attempt_number=attempt_number,
                            redirect_index=redirect_index,
                            requested_at=requested_at,
                            outcome=AcquisitionAttemptOutcome.REJECTED,
                            status_code=response.status_code,
                            headers=response.headers,
                            transferred_bytes=0,
                            error_code=error_code,
                            error_message=message,
                        )
                    raise
            finally:
                try:
                    self._safe_close(
                        response,
                        run_id=run_id,
                        report_number=report_number,
                        url=response_url,
                    )
                except KeyboardInterrupt:
                    if downloaded is not None:
                        self._cleanup_temp_path(
                            downloaded.path,
                            run_id=run_id,
                            report_number=report_number,
                            url=response_url,
                            related_attempt_id=self.receipts[-1].attempt_id,
                        )
                    raise
