"""Pure URL, authority, coverage, and pagination policy for M1 discovery."""

from __future__ import annotations

from enum import StrEnum
from typing import Final
from urllib.parse import urljoin, urlsplit, urlunsplit

from peru_conflicts.discovery.models import CoverageExpectation

_TRACKING_PREFIX: Final[str] = "utm_"
_HTTP_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


def _absolute_url_parts(url: str) -> tuple[str, str, str, str]:
    """Return normalized transport parts after validating an absolute URL."""

    if not url.strip():
        raise ValueError("URL must be a non-empty string")
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in _HTTP_SCHEMES:
        raise ValueError("URL scheme must be HTTP or HTTPS")
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must have a host and no credentials")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL port is invalid") from error
    hostname = parsed.hostname
    if hostname is None or any(character.isspace() for character in hostname):
        raise ValueError("URL host is invalid")
    host = hostname.lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"

    path = parsed.path or "/"
    query_parts: list[str] = []
    for part in parsed.query.split("&") if parsed.query else []:
        key = part.split("=", maxsplit=1)[0].lower()
        if not key.startswith(_TRACKING_PREFIX):
            query_parts.append(part)
    query = "&".join(query_parts)
    return scheme, netloc, path, query


def normalize_url(url: str, *, base_url: str | None = None) -> str:
    """Normalize a loss-minimizing HTTP(S) URL for stable comparison.

    Meaningful query parameters and path spelling are retained. Only fragments,
    default ports, and parameters whose raw key begins with ``utm_`` are removed.
    """

    candidate = url
    if base_url is not None:
        base_scheme, base_netloc, base_path, base_query = _absolute_url_parts(base_url)
        base = urlunsplit((base_scheme, base_netloc, base_path, base_query, ""))
        candidate = urljoin(base, url)
    elif url.startswith("//"):
        raise ValueError("protocol-relative URLs require an HTTP(S) base URL")

    scheme, netloc, path, query = _absolute_url_parts(candidate)
    return urlunsplit((scheme, netloc, path, query, ""))


def classify_host(url: str, approved_hosts: frozenset[str]) -> str:
    """Classify a URL without promoting arbitrary subdomains or mirrors."""

    try:
        normalized = normalize_url(url)
    except ValueError:
        return "unsupported"
    host = urlsplit(normalized).hostname
    if host is None:
        return "unsupported"
    approved = {item.lower().rstrip(".") for item in approved_hosts}
    return "authoritative" if host.rstrip(".") in approved else "pending_review"


def _period_parts(period: str) -> tuple[int, int]:
    if len(period) != 7 or period[4] != "-":
        raise ValueError("reference period must be a real YYYY-MM calendar month")
    try:
        year = int(period[:4])
        month = int(period[5:])
    except ValueError as error:
        raise ValueError("reference period must be a real YYYY-MM calendar month") from error
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        raise ValueError("reference period must be a real YYYY-MM calendar month")
    return year, month


def build_coverage_grid(start_period: str, end_period: str) -> tuple[CoverageExpectation, ...]:
    """Build monthly research hypotheses, never observations or publication claims."""

    start_year, start_month = _period_parts(start_period)
    end_year, end_month = _period_parts(end_period)
    start_index = start_year * 12 + start_month
    end_index = end_year * 12 + end_month
    if start_index > end_index:
        raise ValueError("coverage-grid start period must not follow end period")

    result: list[CoverageExpectation] = []
    for index in range(start_index, end_index + 1):
        year, month_zero_based = divmod(index - 1, 12)
        result.append(
            CoverageExpectation(
                reference_period=f"{year:04d}-{month_zero_based + 1:02d}",
                rationale="Research coverage-grid hypothesis; observed source not asserted.",
            )
        )
    return tuple(result)


class PaginationStopReason(StrEnum):
    """Explicit reasons for ending a pagination traversal."""

    NO_NEXT_LINK = "no_next_link"
    REPEATED_URL = "repeated_url"
    NON_AUTHORITATIVE_NEXT = "non_authoritative_next"
    PAGE_CAP = "page_cap"
    ERROR = "error"


class PaginationTracker:
    """Track deterministic page traversal and distinguish safe from incomplete stops."""

    def __init__(
        self,
        start_url: str,
        approved_hosts: frozenset[str],
        *,
        page_cap: int = 120,
    ) -> None:
        if page_cap < 1:
            raise ValueError("page_cap must be at least one")
        self._approved_hosts = approved_hosts
        self._page_cap = page_cap
        self._seen_urls: list[str] = []
        self._current_url = normalize_url(start_url)
        self._stop_reason: PaginationStopReason | None = None
        self._complete = False

    @property
    def current_url(self) -> str:
        return self._current_url

    @property
    def seen_urls(self) -> tuple[str, ...]:
        return tuple(self._seen_urls)

    @property
    def stop_reason(self) -> PaginationStopReason | None:
        return self._stop_reason

    @property
    def complete(self) -> bool:
        return self._complete

    def _stop(self, reason: PaginationStopReason, *, complete: bool) -> None:
        self._stop_reason = reason
        self._complete = complete

    def visit(self, url: str | None = None, *, base_url: str | None = None) -> bool:
        """Record one page if it is new, authoritative, and within the safety cap."""

        if self._stop_reason is not None:
            return False
        try:
            candidate = normalize_url(
                self._current_url if url is None else url,
                base_url=base_url,
            )
        except ValueError:
            self._stop(PaginationStopReason.ERROR, complete=False)
            return False
        if classify_host(candidate, self._approved_hosts) != "authoritative":
            self._stop(PaginationStopReason.NON_AUTHORITATIVE_NEXT, complete=False)
            return False
        if candidate in self._seen_urls:
            self._stop(PaginationStopReason.REPEATED_URL, complete=True)
            return False
        if len(self._seen_urls) >= self._page_cap:
            self._stop(PaginationStopReason.PAGE_CAP, complete=False)
            return False
        self._seen_urls.append(candidate)
        self._current_url = candidate
        return True

    def propose_next(self, next_url: str | None, *, base_url: str | None = None) -> str | None:
        """Validate a visible next link and return it for the caller to visit."""

        if self._stop_reason is not None:
            return None
        if next_url is None:
            self._stop(PaginationStopReason.NO_NEXT_LINK, complete=True)
            return None
        try:
            candidate = normalize_url(next_url, base_url=base_url or self._current_url)
        except ValueError:
            self._stop(PaginationStopReason.ERROR, complete=False)
            return None
        if classify_host(candidate, self._approved_hosts) != "authoritative":
            self._stop(PaginationStopReason.NON_AUTHORITATIVE_NEXT, complete=False)
            return None
        if candidate in self._seen_urls:
            self._stop(PaginationStopReason.REPEATED_URL, complete=True)
            return None
        if len(self._seen_urls) >= self._page_cap:
            self._stop(PaginationStopReason.PAGE_CAP, complete=False)
            return None
        return candidate

    def stop_error(self) -> None:
        """Stop on an unclassified request/parse failure; this is never complete."""

        self._stop(PaginationStopReason.ERROR, complete=False)
