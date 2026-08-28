"""Robots-aware, serial HTML client with an explicit no-binary boundary."""

from __future__ import annotations

import email.utils
import hashlib
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from time import monotonic
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from peru_conflicts.discovery.models import RedirectHop, UrlObservation, UrlRole
from peru_conflicts.discovery.policy import classify_host, normalize_url
from peru_conflicts.discovery.receipts import (
    RateLimitHeader,
    RequestAttemptReceipt,
    RequestKind,
    RequestOutcome,
    SelectedHttpHeaders,
)
from peru_conflicts.discovery.settings import MAX_LIVE_RETRY_CAP, MIN_LIVE_DELAY_SECONDS

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_ROBOTS_CONTENT_TYPES = frozenset({"text/plain"})
_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_BINARY_MAGIC = (b"%PDF-", b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class DiscoveryClientError(RuntimeError):
    """Base class for safe-client failures."""


class RobotsDenied(DiscoveryClientError):
    """The requested URL is disallowed by the host's robots policy."""


class PdfBodyRejected(DiscoveryClientError):
    """A PDF or PDF redirect was encountered where HTML-only retrieval is required."""


class BinaryBodyRejected(DiscoveryClientError):
    """A non-HTML response was rejected before body interpretation."""


class UnapprovedRedirect(DiscoveryClientError):
    """A redirect destination is outside the configured authoritative hosts."""


class HttpRequestError(DiscoveryClientError):
    """The bounded request/retry policy could not obtain an acceptable response."""


class ResponseBodyTooLarge(DiscoveryClientError):
    """An allowlisted response exceeded its explicit byte cap."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Transport-neutral response used by the client and deterministic test doubles."""

    requested_url: str
    final_url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    redirect_hops: tuple[RedirectHop, ...] = ()
    body_read: bool = True
    body_complete: bool = True
    body_too_large: bool = False


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        allowed_content_types: frozenset[str],
        max_body_bytes: int,
    ) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class FetchedHtml:
    observation: UrlObservation
    body: str
    receipts: tuple[RequestAttemptReceipt, ...]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class UrllibTransport:
    """Default transport that gates Content-Type before reading a response body."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        allowed_content_types: frozenset[str],
        max_body_bytes: int,
    ) -> HttpResponse:
        request = urllib.request.Request(url, method=method, headers=headers or {})
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as error:
            # HTTP errors and redirects are receipt evidence, never body-reading authority.
            return HttpResponse(
                requested_url=url,
                final_url=url,
                status=error.code,
                headers={key: value for key, value in error.headers.items()},
                body=b"",
                body_read=False,
                body_complete=False,
            )
        with response:
            response_headers = {key: value for key, value in response.headers.items()}
            content_type = _content_type(response_headers)
            if response.status in _REDIRECT_STATUSES or content_type not in allowed_content_types:
                return HttpResponse(
                    requested_url=url,
                    final_url=response.geturl(),
                    status=response.status,
                    headers=response_headers,
                    body=b"",
                    body_read=False,
                    body_complete=False,
                )
            content_length = _content_length(response_headers)
            if content_length is not None and content_length > max_body_bytes:
                return HttpResponse(
                    requested_url=url,
                    final_url=response.geturl(),
                    status=response.status,
                    headers=response_headers,
                    body=b"",
                    body_read=False,
                    body_complete=False,
                    body_too_large=True,
                )
            body = response.read(max_body_bytes + 1)
            if len(body) > max_body_bytes:
                return HttpResponse(
                    requested_url=url,
                    final_url=response.geturl(),
                    status=response.status,
                    headers=response_headers,
                    body=body,
                    body_read=True,
                    body_complete=False,
                    body_too_large=True,
                )
            return HttpResponse(
                requested_url=url,
                final_url=response.geturl(),
                status=response.status,
                headers=response_headers,
                body=body,
                body_read=True,
                body_complete=True,
            )


def _header(headers: Mapping[str, str] | Message, name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return str(value)
    return None


def _content_type(headers: Mapping[str, str]) -> str | None:
    value = _header(headers, "Content-Type")
    return value.split(";", maxsplit=1)[0].strip().lower() if value else None


def _content_length(headers: Mapping[str, str]) -> int | None:
    value = _header(headers, "Content-Length")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _selected_headers(headers: Mapping[str, str]) -> SelectedHttpHeaders:
    rate_limit: list[RateLimitHeader] = []
    for name, value in headers.items():
        normalized = name.lower()
        if normalized.startswith(("ratelimit-", "x-ratelimit-", "x-rate-limit-")):
            rate_limit.append(RateLimitHeader(name=name, value=value))
    return SelectedHttpHeaders(
        content_type_original=_header(headers, "Content-Type"),
        content_length_original=_header(headers, "Content-Length"),
        etag_original=_header(headers, "ETag"),
        last_modified_original=_header(headers, "Last-Modified"),
        retry_after_original=_header(headers, "Retry-After"),
        location_original=_header(headers, "Location"),
        rate_limit_headers=tuple(rate_limit),
    )


def _is_binary_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".pdf", ".zip", ".xlsx", ".xls", ".doc", ".docx", ".csv", ".tsv"))


def _require_authoritative_https_url(url: str, approved_hosts: frozenset[str]) -> str:
    """Normalize and require an approved host over HTTPS on its default port."""

    try:
        normalized = normalize_url(url)
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as error:
        raise UnapprovedRedirect(f"URL is not a valid authoritative HTTPS URL: {url}") from error
    if (
        classify_host(normalized, approved_hosts) != "authoritative"
        or parsed.scheme != "https"
        or port not in {None, 443}
    ):
        raise UnapprovedRedirect(
            f"authoritative discovery URLs must use HTTPS on the default port: {normalized}"
        )
    return normalized


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


def _default_utc_now() -> datetime:
    return datetime.now(UTC)


class HtmlClient:
    """Serial HTML client with robots checks and one receipt per transport attempt."""

    def __init__(
        self,
        approved_hosts: frozenset[str],
        *,
        transport: HttpTransport | None = None,
        user_agent: str = "peru-conflict-data-m1-discovery/1.0 (+research)",
        delay_seconds: float = 2.0,
        retry_cap: int = 2,
        max_html_body_bytes: int = 5_000_000,
        max_robots_body_bytes: int = 500_000,
        max_redirects: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = monotonic,
        utc_clock: Callable[[], datetime] = _default_utc_now,
    ) -> None:
        live_transport = transport is None
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if retry_cap < 0:
            raise ValueError("retry_cap must be non-negative")
        if live_transport and delay_seconds < MIN_LIVE_DELAY_SECONDS:
            raise ValueError(f"live delay must be at least {MIN_LIVE_DELAY_SECONDS:.1f} seconds")
        if live_transport and retry_cap > MAX_LIVE_RETRY_CAP:
            raise ValueError(f"live retry cap must be at most {MAX_LIVE_RETRY_CAP}")
        if max_html_body_bytes < 1 or max_robots_body_bytes < 1:
            raise ValueError("response body byte caps must be positive")
        if not 0 <= max_redirects <= 5:
            raise ValueError("max_redirects must be between zero and five")
        self.approved_hosts = approved_hosts
        self.transport = transport or UrllibTransport()
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.retry_cap = retry_cap
        self.max_html_body_bytes = max_html_body_bytes
        self.max_robots_body_bytes = max_robots_body_bytes
        self.max_redirects = max_redirects
        self._sleep = sleep
        self._clock = clock
        self._utc_clock = utc_clock
        self._last_request_at: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self.request_receipts: list[RequestAttemptReceipt] = []

    def _wait_before_request(self, requested_wait: float = 0.0) -> None:
        required = max(self.delay_seconds, requested_wait)
        if self._last_request_at is not None:
            elapsed = max(0.0, self._clock() - self._last_request_at)
            remaining = max(0.0, required - elapsed)
            if remaining:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _append_receipt(
        self,
        *,
        observation_id: str | None,
        request_kind: RequestKind,
        attempt_number: int,
        redirect_index: int,
        requested_url: str,
        requested_at: datetime,
        completed_at: datetime,
        outcome: RequestOutcome,
        response: HttpResponse | None,
        body_read: bool,
        body_complete: bool,
        redirect_target_url: str | None = None,
        retry_delay: float | None = None,
        error: Exception | None = None,
    ) -> RequestAttemptReceipt:
        body = response.body if response is not None and body_read else None
        receipt = RequestAttemptReceipt(
            schema_version="0.3.0",
            receipt_id="request-attempt-"
            + hashlib.sha256(
                (
                    f"{requested_url}\x1f{requested_at.isoformat()}\x1f{attempt_number}"
                    f"\x1f{redirect_index}"
                ).encode()
            ).hexdigest()[:16],
            observation_id=observation_id,
            request_kind=request_kind,
            attempt_number=attempt_number,
            redirect_index=redirect_index,
            requested_url=requested_url,
            requested_at=requested_at,
            completed_at=completed_at,
            outcome=outcome,
            status_code=response.status if response is not None else None,
            response_url=response.final_url if response is not None else None,
            selected_headers=(
                _selected_headers(response.headers)
                if response is not None
                else SelectedHttpHeaders()
            ),
            body_read=body_read,
            body_complete=body_complete,
            body_byte_count=len(body) if body is not None else None,
            body_sha256=hashlib.sha256(body).hexdigest() if body is not None else None,
            redirect_target_url=redirect_target_url,
            retry_scheduled=retry_delay is not None,
            retry_delay_seconds=retry_delay,
            error_type=type(error).__name__ if error is not None else None,
            error_message=(str(error) or repr(error)) if error is not None else None,
        )
        self.request_receipts.append(receipt)
        return receipt

    def _request_with_retries(
        self,
        url: str,
        *,
        request_kind: RequestKind,
        observation_id: str | None,
        redirect_index: int,
    ) -> tuple[HttpResponse, tuple[RequestAttemptReceipt, ...]]:
        receipts: list[RequestAttemptReceipt] = []
        retry_wait = 0.0
        allowed = (
            _ROBOTS_CONTENT_TYPES if request_kind is RequestKind.ROBOTS else _HTML_CONTENT_TYPES
        )
        max_bytes = (
            self.max_robots_body_bytes
            if request_kind is RequestKind.ROBOTS
            else self.max_html_body_bytes
        )
        for attempt_index in range(self.retry_cap + 1):
            attempt_number = attempt_index + 1
            self._wait_before_request(retry_wait)
            retry_wait = 0.0
            requested_at = self._utc_clock()
            try:
                response = self.transport.request(
                    url,
                    method="GET",
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": ", ".join(sorted(allowed)),
                    },
                    allowed_content_types=allowed,
                    max_body_bytes=max_bytes,
                )
            except Exception as error:
                completed_at = self._utc_clock()
                retry_delay = self.delay_seconds if attempt_index < self.retry_cap else None
                receipts.append(
                    self._append_receipt(
                        observation_id=observation_id,
                        request_kind=request_kind,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_url=url,
                        requested_at=requested_at,
                        completed_at=completed_at,
                        outcome=RequestOutcome.TRANSPORT_ERROR,
                        response=None,
                        body_read=False,
                        body_complete=False,
                        retry_delay=retry_delay,
                        error=error,
                    )
                )
                if retry_delay is None:
                    raise HttpRequestError(
                        f"request failed after {attempt_number} attempts: {url}"
                    ) from error
                retry_wait = retry_delay
                continue

            completed_at = self._utc_clock()
            content_type = _content_type(response.headers)
            if response.status in _TRANSIENT_STATUSES:
                retry_delay = None
                if attempt_index < self.retry_cap:
                    retry_delay = max(
                        self.delay_seconds,
                        _retry_after_seconds(
                            _header(response.headers, "Retry-After"), now=completed_at
                        ),
                    )
                receipts.append(
                    self._append_receipt(
                        observation_id=observation_id,
                        request_kind=request_kind,
                        attempt_number=attempt_number,
                        redirect_index=redirect_index,
                        requested_url=url,
                        requested_at=requested_at,
                        completed_at=completed_at,
                        outcome=RequestOutcome.TRANSIENT_HTTP,
                        response=response,
                        body_read=False,
                        body_complete=False,
                        retry_delay=retry_delay,
                    )
                )
                if retry_delay is None:
                    raise HttpRequestError(
                        f"transient HTTP status {response.status} after {attempt_number} "
                        f"attempts: {url}"
                    )
                retry_wait = retry_delay
                continue

            redirect_target_url: str | None = None
            redirect_error: HttpRequestError | None = None
            if response.status in _REDIRECT_STATUSES:
                body_read = False
                location = _header(response.headers, "Location")
                if not location:
                    outcome = RequestOutcome.REJECTED_REDIRECT
                    redirect_error = HttpRequestError(f"redirect has no Location header: {url}")
                else:
                    try:
                        redirect_target_url = normalize_url(location, base_url=url)
                    except ValueError:
                        outcome = RequestOutcome.REJECTED_REDIRECT
                        redirect_error = HttpRequestError(
                            f"redirect has an invalid Location header: {url}"
                        )
                    else:
                        if redirect_target_url == normalize_url(url):
                            outcome = RequestOutcome.REJECTED_REDIRECT
                            redirect_target_url = None
                            redirect_error = HttpRequestError(
                                f"redirect Location does not identify a new URL: {url}"
                            )
                        else:
                            outcome = RequestOutcome.REDIRECT
            elif response.status < 200 or response.status >= 300:
                outcome = RequestOutcome.HTTP_ERROR
                body_read = False
            elif response.body_too_large:
                outcome = RequestOutcome.REJECTED_BODY_SIZE
                body_read = response.body_read
            elif content_type not in allowed or not response.body_read:
                outcome = RequestOutcome.REJECTED_CONTENT_TYPE
                body_read = False
            elif response.body.startswith(_BINARY_MAGIC):
                outcome = RequestOutcome.REJECTED_BODY_SIGNATURE
                body_read = True
            else:
                outcome = RequestOutcome.SUCCESS
                body_read = True
            receipts.append(
                self._append_receipt(
                    observation_id=observation_id,
                    request_kind=request_kind,
                    attempt_number=attempt_number,
                    redirect_index=redirect_index,
                    requested_url=url,
                    requested_at=requested_at,
                    completed_at=completed_at,
                    outcome=outcome,
                    response=response,
                    body_read=body_read,
                    body_complete=body_read and response.body_complete,
                    redirect_target_url=redirect_target_url,
                    error=redirect_error,
                )
            )
            return response, tuple(receipts)
        raise HttpRequestError(f"request failed: {url}")

    def _fetch_robots(self, url: str) -> RobotFileParser:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None:
            raise DiscoveryClientError("robots URL has no host")
        cache_key = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        if cache_key in self._robots:
            return self._robots[cache_key]
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        observation_id = "robots-" + hashlib.sha256(robots_url.encode("utf-8")).hexdigest()[:16]
        response, _ = self._request_with_retries(
            robots_url,
            request_kind=RequestKind.ROBOTS,
            observation_id=observation_id,
            redirect_index=0,
        )
        if response.body_too_large:
            raise ResponseBodyTooLarge(
                f"robots.txt exceeded {self.max_robots_body_bytes} bytes: {robots_url}"
            )
        content_type = _content_type(response.headers)
        if content_type != "text/plain" or not response.body_read:
            raise BinaryBodyRejected(f"robots.txt content type is not text/plain: {content_type}")
        if response.body.startswith(_BINARY_MAGIC):
            raise BinaryBodyRejected("robots.txt body has a rejected binary signature")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
        self._robots[cache_key] = parser
        return parser

    def fetch_html(
        self,
        url: str,
        *,
        role: UrlRole,
        observation_id: str | None = None,
        captured_at: datetime | None = None,
    ) -> FetchedHtml:
        """Fetch one approved HTML page, never a linked binary body."""

        captured = captured_at or datetime.now(UTC)
        normalized = _require_authoritative_https_url(url, self.approved_hosts)
        page_observation_id = (
            observation_id
            or "observation-"
            + hashlib.sha256(f"{normalized}\x1f{captured.isoformat()}".encode()).hexdigest()[:16]
        )
        if _is_binary_url(normalized):
            raise PdfBodyRejected(f"binary/PDF URL is outside the HTML-only boundary: {normalized}")
        robots = self._fetch_robots(normalized)
        if not robots.can_fetch(self.user_agent, normalized):
            raise RobotsDenied(f"robots.txt disallows the requested URL: {normalized}")

        receipt_start = len(self.request_receipts)
        current_url = normalized
        redirect_hops: list[RedirectHop] = []
        response: HttpResponse | None = None
        for redirect_index in range(self.max_redirects + 1):
            response, attempt_receipts = self._request_with_retries(
                current_url,
                request_kind=RequestKind.HTML,
                observation_id=page_observation_id,
                redirect_index=redirect_index,
            )
            content_type = _content_type(response.headers)
            if response.body_too_large:
                raise ResponseBodyTooLarge(
                    f"HTML response exceeded {self.max_html_body_bytes} bytes: {current_url}"
                )
            if response.status in _REDIRECT_STATUSES:
                attempt_receipt = attempt_receipts[-1]
                if attempt_receipt.outcome is RequestOutcome.REJECTED_REDIRECT:
                    raise HttpRequestError(
                        attempt_receipt.error_message
                        or f"redirect evidence was invalid: {current_url}"
                    )
                target = attempt_receipt.redirect_target_url
                if target is None:
                    raise HttpRequestError(f"redirect target was not recorded: {current_url}")
                target = _require_authoritative_https_url(target, self.approved_hosts)
                if _is_binary_url(target):
                    raise PdfBodyRejected(f"redirect points to a binary/PDF URL: {target}")
                target_robots = self._fetch_robots(target)
                if not target_robots.can_fetch(self.user_agent, target):
                    raise RobotsDenied(f"robots.txt disallows redirect destination: {target}")
                completed_at = self.request_receipts[-1].completed_at
                redirect_hops.append(
                    RedirectHop(
                        from_url=current_url,
                        to_url=target,
                        status_code=response.status,
                        captured_at=completed_at,
                    )
                )
                current_url = target
                continue
            if response.status < 200 or response.status >= 300:
                raise HttpRequestError(f"unexpected HTTP status {response.status}: {current_url}")
            if content_type not in _HTML_CONTENT_TYPES or not response.body_read:
                if content_type == "application/pdf":
                    raise PdfBodyRejected(f"PDF response content type: {content_type}")
                raise BinaryBodyRejected(f"unlisted response content type: {content_type}")
            if response.body.startswith(_BINARY_MAGIC):
                if response.body.startswith(b"%PDF-"):
                    raise PdfBodyRejected("HTML-labelled response has a PDF body signature")
                raise BinaryBodyRejected("HTML-labelled response has a binary archive signature")
            break
        else:
            raise HttpRequestError(f"redirect limit exceeded: {url}")
        assert response is not None
        final_url = _require_authoritative_https_url(
            response.final_url or current_url, self.approved_hosts
        )
        all_hops = tuple(response.redirect_hops) + tuple(redirect_hops)
        if all_hops and all_hops[-1].to_url != final_url:
            all_hops = tuple(redirect_hops)
        observation = UrlObservation(
            observation_id=page_observation_id,
            role=role,
            url=final_url,
            captured_at=captured,
            http_status=response.status,
            content_type=_content_type(response.headers),
            redirect_hops=all_hops,
        )
        return FetchedHtml(
            observation=observation,
            body=response.body.decode("utf-8", errors="replace"),
            receipts=tuple(self.request_receipts[receipt_start:]),
        )
