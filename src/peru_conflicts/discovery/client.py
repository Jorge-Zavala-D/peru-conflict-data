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


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Transport-neutral response used by the client and deterministic test doubles."""

    requested_url: str
    final_url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    redirect_hops: tuple[RedirectHop, ...] = ()


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class RequestReceipt:
    requested_url: str
    final_url: str
    status: int
    content_type: str | None
    attempts: int
    captured_at: datetime
    redirect_count: int


@dataclass(frozen=True, slots=True)
class FetchedHtml:
    observation: UrlObservation
    body: str
    receipts: tuple[RequestReceipt, ...]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class UrllibTransport:
    """Default transport that never follows redirects or reads rejected bodies."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        request = urllib.request.Request(url, method=method, headers=headers or {})
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as error:
            response_headers = {key: value for key, value in error.headers.items()}
            body = b"" if error.code in {301, 302, 303, 307, 308} else error.read(0)
            return HttpResponse(
                requested_url=url,
                final_url=url,
                status=error.code,
                headers=response_headers,
                body=body,
            )
        with response:
            response_headers = {key: value for key, value in response.headers.items()}
            content_type = _header(response.headers, "Content-Type")
            if response.status in {301, 302, 303, 307, 308} or _is_binary_content_type(
                content_type
            ):
                body = b""
            else:
                body = response.read()
            return HttpResponse(
                requested_url=url,
                final_url=response.geturl(),
                status=response.status,
                headers=response_headers,
                body=body,
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


def _is_binary_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    return content_type in {
        "application/pdf",
        "application/octet-stream",
        "application/zip",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }


def _is_binary_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith((".pdf", ".zip", ".xlsx", ".xls", ".doc", ".docx", ".csv", ".tsv"))


def _retry_after_seconds(value: str | None) -> float:
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
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


class HtmlClient:
    """Serial HTML client with robots checks, bounded retries, and request receipts."""

    def __init__(
        self,
        approved_hosts: frozenset[str],
        *,
        transport: HttpTransport | None = None,
        user_agent: str = "peru-conflict-data-m1-discovery/1.0 (+research)",
        delay_seconds: float = 2.0,
        retry_cap: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if retry_cap < 0:
            raise ValueError("retry_cap must be non-negative")
        self.approved_hosts = approved_hosts
        self.transport = transport or UrllibTransport()
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.retry_cap = retry_cap
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self.request_receipts: list[RequestReceipt] = []

    def _wait_before_request(self, requested_wait: float = 0.0) -> None:
        required = max(self.delay_seconds, requested_wait)
        if self._last_request_at is not None:
            elapsed = max(0.0, self._clock() - self._last_request_at)
            remaining = max(0.0, required - elapsed)
            if remaining:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _request_with_retries(self, url: str, *, captured_at: datetime) -> tuple[HttpResponse, int]:
        last_error: Exception | None = None
        retry_wait = 0.0
        for attempt in range(self.retry_cap + 1):
            try:
                self._wait_before_request(retry_wait)
                retry_wait = 0.0
                response = self.transport.request(
                    url,
                    method="GET",
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html, application/xhtml+xml",
                    },
                )
            except Exception as error:
                last_error = error
                if attempt >= self.retry_cap:
                    raise HttpRequestError(
                        f"request failed after {attempt + 1} attempts: {url}"
                    ) from error
                retry_wait = self.delay_seconds
                continue
            if response.status not in {429, 500, 502, 503, 504}:
                return response, attempt + 1
            if attempt >= self.retry_cap:
                raise HttpRequestError(
                    f"transient HTTP status {response.status} after {attempt + 1} attempts: {url}"
                )
            retry_wait = _retry_after_seconds(_header(response.headers, "Retry-After"))
            retry_wait = max(self.delay_seconds, retry_wait)
        raise HttpRequestError(f"request failed: {url}") from last_error

    def _fetch_robots(self, url: str, *, captured_at: datetime) -> RobotFileParser:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host is None:
            raise DiscoveryClientError("robots URL has no host")
        cache_key = host.lower()
        if cache_key in self._robots:
            return self._robots[cache_key]
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        response, attempts = self._request_with_retries(robots_url, captured_at=captured_at)
        content_type = _content_type(response.headers)
        if content_type != "text/plain":
            raise BinaryBodyRejected(f"robots.txt content type is not text/plain: {content_type}")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
        self._robots[cache_key] = parser
        self.request_receipts.append(
            RequestReceipt(
                requested_url=robots_url,
                final_url=normalize_url(response.final_url),
                status=response.status,
                content_type=content_type,
                attempts=attempts,
                captured_at=captured_at,
                redirect_count=len(response.redirect_hops),
            )
        )
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
        normalized = normalize_url(url)
        if classify_host(normalized, self.approved_hosts) != "authoritative":
            raise UnapprovedRedirect(f"URL host is not authoritative: {normalized}")
        if _is_binary_url(normalized):
            raise PdfBodyRejected(f"binary/PDF URL is outside the HTML-only boundary: {normalized}")
        robots = self._fetch_robots(normalized, captured_at=captured)
        if not robots.can_fetch(self.user_agent, normalized):
            raise RobotsDenied(f"robots.txt disallows the requested URL: {normalized}")

        current_url = normalized
        redirect_hops: list[RedirectHop] = []
        response: HttpResponse | None = None
        attempts = 0
        for _ in range(5):
            response, request_attempts = self._request_with_retries(
                current_url, captured_at=captured
            )
            attempts += request_attempts
            content_type = _content_type(response.headers)
            if response.status in {301, 302, 303, 307, 308}:
                location = _header(response.headers, "Location")
                if not location:
                    raise HttpRequestError(f"redirect has no Location header: {current_url}")
                target = normalize_url(location, base_url=current_url)
                if _is_binary_url(target):
                    raise PdfBodyRejected(f"redirect points to a binary/PDF URL: {target}")
                if classify_host(target, self.approved_hosts) != "authoritative":
                    raise UnapprovedRedirect(f"redirect destination is not authoritative: {target}")
                target_robots = self._fetch_robots(target, captured_at=captured)
                if not target_robots.can_fetch(self.user_agent, target):
                    raise RobotsDenied(f"robots.txt disallows redirect destination: {target}")
                redirect_hops.append(
                    RedirectHop(
                        from_url=current_url,
                        to_url=target,
                        status_code=response.status,
                        captured_at=captured,
                    )
                )
                current_url = target
                continue
            if response.status < 200 or response.status >= 300:
                raise HttpRequestError(f"unexpected HTTP status {response.status}: {current_url}")
            if content_type not in {"text/html", "application/xhtml+xml"}:
                if _is_binary_content_type(content_type):
                    raise PdfBodyRejected(f"binary/PDF response content type: {content_type}")
                raise BinaryBodyRejected(f"unlisted response content type: {content_type}")
            break
        else:
            raise HttpRequestError(f"redirect limit exceeded: {url}")
        assert response is not None
        final_url = normalize_url(response.final_url or current_url)
        if classify_host(final_url, self.approved_hosts) != "authoritative":
            raise UnapprovedRedirect(f"final response URL is not authoritative: {final_url}")
        all_hops = tuple(response.redirect_hops) + tuple(redirect_hops)
        if all_hops and all_hops[-1].to_url != final_url:
            all_hops = tuple(redirect_hops)
        observation = UrlObservation(
            observation_id=observation_id
            or "observation-"
            + hashlib.sha256(f"{normalized}\x1f{captured.isoformat()}".encode()).hexdigest()[:16],
            role=role,
            url=final_url,
            captured_at=captured,
            http_status=response.status,
            content_type=_content_type(response.headers),
            redirect_hops=all_hops,
        )
        receipt = RequestReceipt(
            requested_url=normalized,
            final_url=final_url,
            status=response.status,
            content_type=_content_type(response.headers),
            attempts=attempts,
            captured_at=captured,
            redirect_count=len(all_hops),
        )
        self.request_receipts.append(receipt)
        return FetchedHtml(
            observation=observation,
            body=response.body.decode("utf-8", errors="replace"),
            receipts=(receipt,),
        )
