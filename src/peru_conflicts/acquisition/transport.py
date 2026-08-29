"""Direct verified standard-library HTTPS transport for future live comparison."""

from __future__ import annotations

import http.client
import os
import re
import ssl
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, Self, cast
from urllib.parse import quote, unquote_to_bytes, urlsplit

PROJECT_USER_AGENT = (
    "peru-conflict-data/0.1 "
    "(+https://github.com/Jorge-Zavala-D/peru-conflict-data; M1-03B compare-only)"
)
PROXY_OR_TLS_OVERRIDE_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_ENGINES",
    "OPENSSL_MODULES",
    "SSLKEYLOGFILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)
PROHIBITED_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "host",
        "connection",
        "proxy-connection",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "accept-encoding",
        "user-agent",
    }
)
SAFETY_CRITICAL_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "content-type",
        "content-encoding",
        "location",
        "transfer-encoding",
        "retry-after",
    }
)
SAFE_EXPOSED_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "content-type",
        "content-encoding",
        "location",
        "transfer-encoding",
        "retry-after",
        "etag",
        "last-modified",
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
_INVALID_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def _contains_header_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


class TransportConfigurationError(RuntimeError):
    """A caller attempted to widen the sealed transport behavior."""


class EnvironmentNetworkPolicyError(TransportConfigurationError):
    """Unreviewed proxy or TLS environment state is active."""


class UnapprovedCanonicalUrl(TransportConfigurationError):
    """A URL is outside the exact acquisition authority or path grammar."""


class MalformedResponseHeaders(RuntimeError):
    """Response headers are ambiguous or unsafe before body interpretation."""


class StandardLibraryTransportError(RuntimeError):
    """Sanitized transport failure containing only the exception class."""


@dataclass(frozen=True, slots=True)
class CanonicalAcquisitionUrl:
    """Separate source, normalized identity, and wire representations."""

    source_original: str
    normalized_url: str
    host: str
    wire_target: str


def _decode_path_segment(segment: str) -> str:
    if _INVALID_PERCENT.search(segment):
        raise UnapprovedCanonicalUrl("URL path contains an invalid percent escape")
    try:
        decoded = unquote_to_bytes(segment).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise UnapprovedCanonicalUrl("URL path is not valid UTF-8") from error
    if decoded in {".", ".."}:
        raise UnapprovedCanonicalUrl("URL path contains a dot segment")
    if any(
        character in {"/", "\\"} or ord(character) < 32 or ord(character) == 127
        for character in decoded
    ):
        raise UnapprovedCanonicalUrl("URL path contains an encoded separator or control")
    return decoded


def canonicalize_acquisition_url(
    url: str,
    approved_hosts: frozenset[str],
) -> CanonicalAcquisitionUrl:
    """Validate exact input before canonicalizing its UTF-8 wire path."""

    if not url or any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise UnapprovedCanonicalUrl("URL contains an empty value or control character")
    if "\\" in url:
        raise UnapprovedCanonicalUrl("URL contains a backslash")
    if "?" in url or "#" in url:
        raise UnapprovedCanonicalUrl("URL query and fragment delimiters are prohibited")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise UnapprovedCanonicalUrl("URL authority is malformed") from error
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in approved_hosts
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise UnapprovedCanonicalUrl("URL is outside the exact HTTPS acquisition authority")
    raw_path = parsed.path or "/"
    if not raw_path.startswith("/") or raw_path.startswith("//"):
        raise UnapprovedCanonicalUrl("URL path is not an absolute origin-form path")
    decoded_segments = tuple(_decode_path_segment(segment) for segment in raw_path.split("/"))
    decoded_path = "/".join(decoded_segments)
    wire_target = quote(decoded_path, safe="/-._~!$&'()*+,;=:@")
    normalized_url = f"https://{host}{wire_target}"
    return CanonicalAcquisitionUrl(
        source_original=url,
        normalized_url=normalized_url,
        host=host,
        wire_target=wire_target,
    )


def validate_strict_redirect(
    reviewed: CanonicalAcquisitionUrl,
    target_url: str,
    *,
    approved_hosts: frozenset[str],
) -> CanonicalAcquisitionUrl:
    """Allow only approved host aliases with the exact reviewed canonical path."""

    target = canonicalize_acquisition_url(target_url, approved_hosts)
    if target.wire_target != reviewed.wire_target:
        raise UnapprovedCanonicalUrl("redirect changes the exact reviewed canonical path")
    return target


class _RawResponse(Protocol):
    status: int

    def getheaders(self) -> list[tuple[str, str]]: ...

    def read(self, amount: int) -> bytes: ...

    def close(self) -> None: ...


class _Connection(Protocol):
    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> _RawResponse: ...

    def close(self) -> None: ...


ConnectionFactory = Callable[[str, int, int, ssl.SSLContext], _Connection]


def _default_connection_factory(
    host: str,
    port: int,
    timeout: int,
    context: ssl.SSLContext,
) -> _Connection:
    return cast(
        _Connection,
        http.client.HTTPSConnection(host, port=port, timeout=timeout, context=context),
    )


def validate_network_environment() -> None:
    """Reject ambient proxy, TLS, or OpenSSL overrides before transport use."""

    prohibited = {name.casefold() for name in PROXY_OR_TLS_OVERRIDE_NAMES}
    if any(
        name.casefold() in prohibited or name.casefold().startswith("openssl_")
        for name in os.environ
    ):
        raise EnvironmentNetworkPolicyError(
            "proxy, TLS, or OpenSSL override environment is not approved for live comparison"
        )


def _validate_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    observed_names: set[str] = set()
    for name, value in headers.items():
        lowered = name.casefold()
        if (
            not name
            or _HEADER_NAME.fullmatch(name) is None
            or lowered in PROHIBITED_REQUEST_HEADERS
            or lowered in observed_names
            or _contains_header_control(value)
        ):
            raise TransportConfigurationError("caller headers violate the sealed request policy")
        observed_names.add(lowered)
        rendered[name] = value
    rendered["Accept-Encoding"] = "identity"
    rendered["User-Agent"] = PROJECT_USER_AGENT
    return rendered


def _validated_response_headers(
    pairs: list[tuple[str, str]],
) -> Mapping[str, str]:
    by_name: dict[str, list[str]] = {}
    for name, value in pairs:
        lowered = name.casefold()
        if not name or _HEADER_NAME.fullmatch(name) is None or _contains_header_control(value):
            raise MalformedResponseHeaders("response header contains a control character")
        by_name.setdefault(lowered, []).append(value)
    if any(len(by_name.get(name, ())) > 1 for name in SAFETY_CRITICAL_RESPONSE_HEADERS):
        raise MalformedResponseHeaders("response repeats a safety-critical header")
    if "content-length" in by_name and "transfer-encoding" in by_name:
        raise MalformedResponseHeaders("response has ambiguous body framing")
    length_values = by_name.get("content-length")
    if length_values is not None:
        try:
            length = int(length_values[0])
        except ValueError as error:
            raise MalformedResponseHeaders("Content-Length is not a nonnegative integer") from error
        if length < 0:
            raise MalformedResponseHeaders("Content-Length is not a nonnegative integer")
    exposed = {
        name: values[0] for name, values in by_name.items() if name in SAFE_EXPOSED_RESPONSE_HEADERS
    }
    return MappingProxyType(exposed)


@dataclass(slots=True)
class _StreamingResponse:
    status_code: int
    headers: Mapping[str, str]
    _response: _RawResponse
    _connection: _Connection
    _read_chunk_size: int
    _closed: bool = False

    def iter_bytes(self) -> Iterator[bytes]:
        while True:
            chunk = self._response.read(self._read_chunk_size)
            if not chunk:
                return
            if len(chunk) > self._read_chunk_size:
                raise StandardLibraryTransportError("OversizedTransportChunk")
            yield chunk

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        finally:
            self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *unused: object) -> None:
        del unused
        self.close()


class StandardLibraryStreamingTransport:
    """Direct, verified, non-redirecting HTTPS transport with bounded reads."""

    automatic_redirects = False
    follows_redirects = False

    def __init__(
        self,
        *,
        approved_hosts: frozenset[str],
        connection_factory: ConnectionFactory = _default_connection_factory,
        read_chunk_size: int = 64 * 1024,
    ) -> None:
        if not approved_hosts or read_chunk_size < 1 or read_chunk_size > 1024 * 1024:
            raise TransportConfigurationError("transport authority or chunk size is invalid")
        self._approved_hosts = approved_hosts
        self._connection_factory = connection_factory
        self._read_chunk_size = read_chunk_size

    def open(self, url: str, headers: Mapping[str, str]) -> _StreamingResponse:
        """Open a header-first direct HTTPS response without following redirects."""

        canonical = canonicalize_acquisition_url(url, self._approved_hosts)
        request_headers = _validate_request_headers(headers)
        validate_network_environment()
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        connection: _Connection | None = None
        raw: _RawResponse | None = None
        try:
            connection = self._connection_factory(canonical.host, 443, 30, context)
            connection.request("GET", canonical.wire_target, headers=request_headers)
            raw = connection.getresponse()
            response_headers = _validated_response_headers(raw.getheaders())
            return _StreamingResponse(
                status_code=int(raw.status),
                headers=response_headers,
                _response=raw,
                _connection=connection,
                _read_chunk_size=self._read_chunk_size,
            )
        except (TransportConfigurationError, MalformedResponseHeaders):
            if raw is not None:
                raw.close()
            if connection is not None:
                connection.close()
            raise
        except BaseException as error:
            if raw is not None:
                raw.close()
            if connection is not None:
                connection.close()
            raise StandardLibraryTransportError(type(error).__name__) from None

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> _StreamingResponse:
        """Satisfy the sealed engine protocol without accepting timeout widening."""

        if timeout_seconds != 30:
            raise TransportConfigurationError("transport timeout must remain exactly 30 seconds")
        return self.open(url, headers)
