"""Production standard-library HTTPS transport without external network access."""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from typing import Any

import pytest

from peru_conflicts.acquisition.transport import (
    EnvironmentNetworkPolicyError,
    MalformedResponseHeaders,
    StandardLibraryStreamingTransport,
    TransportConfigurationError,
    UnapprovedCanonicalUrl,
    canonicalize_acquisition_url,
    validate_strict_redirect,
)

HOSTS = frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe"))


@dataclass
class FakeHttpResponse:
    status: int = 200
    header_pairs: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("Content-Type", "application/pdf"),
            ("Content-Length", "6"),
            ("Set-Cookie", "secret=never-expose"),
        ]
    )
    chunks: list[bytes] = field(default_factory=lambda: [b"%PDF", b"-x", b""])
    read_sizes: list[int] = field(default_factory=lambda: list[int]())
    closed: bool = False

    def getheaders(self) -> list[tuple[str, str]]:
        return self.header_pairs

    def read(self, amount: int) -> bytes:
        self.read_sizes.append(amount)
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeConnection:
    response: FakeHttpResponse
    requests: list[tuple[str, str, dict[str, str]]] = field(
        default_factory=lambda: list[tuple[str, str, dict[str, str]]]()
    )
    closed: bool = False

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, target, headers))

    def getresponse(self) -> FakeHttpResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_canonical_url_rejects_query_credentials_unsafe_escapes_and_dot_segments() -> None:
    for url in (
        "http://www.defensoria.gob.pe/file.pdf",
        "https://user@www.defensoria.gob.pe/file.pdf",
        "https://www.defensoria.gob.pe:444/file.pdf",
        "https://www.defensoria.gob.pe/file.pdf?utm_source=x",
        "https://www.defensoria.gob.pe/file.pdf?",
        "https://www.defensoria.gob.pe/file.pdf#fragment",
        "https://www.defensoria.gob.pe/file.pdf#",
        "https://www.defensoria.gob.pe/a\\b.pdf",
        "https://www.defensoria.gob.pe/a/%2f/b.pdf",
        "https://www.defensoria.gob.pe/a/%5C/b.pdf",
        "https://www.defensoria.gob.pe/a/%00/b.pdf",
        "https://www.defensoria.gob.pe/a/%2e%2e/b.pdf",
        "https://www.defensoria.gob.pe/a/%GG/b.pdf",
    ):
        with pytest.raises(UnapprovedCanonicalUrl):
            canonicalize_acquisition_url(url, HOSTS)


def test_unicode_and_existing_percent_triplets_have_one_canonical_wire_target() -> None:
    source = (
        "https://www.defensoria.gob.pe/wp-content/uploads/2025/11/"
        "Reporte-Mensual-N°-260\N{EN DASH}Acción.pdf"
    )
    encoded = (
        "https://www.defensoria.gob.pe/wp-content/uploads/2025/11/"
        "Reporte-Mensual-N%C2%B0-260%E2%80%93Acci%C3%B3n.pdf"
    )
    first = canonicalize_acquisition_url(source, HOSTS)
    second = canonicalize_acquisition_url(encoded, HOSTS)

    assert first.source_original == source
    assert first.wire_target.endswith("Reporte-Mensual-N%C2%B0-260%E2%80%93Acci%C3%B3n.pdf")
    assert first.normalized_url == second.normalized_url
    assert first.wire_target == second.wire_target


def test_strict_redirect_allows_host_alias_only_for_identical_canonical_path() -> None:
    reviewed = canonicalize_acquisition_url(
        "https://www.defensoria.gob.pe/wp-content/uploads/file.pdf", HOSTS
    )
    accepted = validate_strict_redirect(
        reviewed,
        "https://defensoria.gob.pe/wp-content/uploads/file.pdf",
        approved_hosts=HOSTS,
    )
    assert accepted.host == "defensoria.gob.pe"

    for target in (
        "https://www.defensoria.gob.pe/wp-content/uploads/other.pdf",
        "https://mirror.example/wp-content/uploads/file.pdf",
        "https://www.defensoria.gob.pe/wp-content/uploads/file.pdf?token=x",
    ):
        with pytest.raises(UnapprovedCanonicalUrl):
            validate_strict_redirect(reviewed, target, approved_hosts=HOSTS)


def test_transport_uses_verified_tls_exact_timeout_identity_encoding_and_bounded_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
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
    ):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)

    response = FakeHttpResponse()
    connection = FakeConnection(response)
    calls: list[tuple[str, int, int, ssl.SSLContext]] = []

    def factory(host: str, port: int, timeout: int, context: ssl.SSLContext) -> FakeConnection:
        calls.append((host, port, timeout, context))
        return connection

    transport = StandardLibraryStreamingTransport(
        approved_hosts=HOSTS,
        connection_factory=factory,
        read_chunk_size=4,
    )
    stream = transport.open(
        "https://www.defensoria.gob.pe/path/Reporte-N°-260.pdf",
        {"Accept": "application/pdf"},
    )

    assert transport.automatic_redirects is False
    assert calls[0][:3] == ("www.defensoria.gob.pe", 443, 30)
    context = calls[0][3]
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.keylog_filename is None
    method, target, headers = connection.requests[0]
    assert method == "GET"
    assert "%C2%B0" in target
    assert headers["Accept-Encoding"] == "identity"
    assert headers["User-Agent"].startswith("peru-conflict-data/")
    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert stream.status_code == 200
    assert "set-cookie" not in stream.headers
    assert b"".join(stream.iter_bytes()) == b"%PDF-x"
    assert response.read_sizes == [4, 4, 4]
    stream.close()
    assert response.closed is True
    assert connection.closed is True


@pytest.mark.parametrize(
    "header",
    (
        "Authorization",
        "Cookie",
        "Proxy-Authorization",
        "Host",
        "Connection",
        "Transfer-Encoding",
        "Content-Length",
        "Accept-Encoding",
        "User-Agent",
    ),
)
def test_transport_rejects_dangerous_caller_headers_before_factory(
    monkeypatch: pytest.MonkeyPatch, header: str
) -> None:
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    calls = 0

    def factory(*args: Any, **kwargs: Any) -> FakeConnection:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    transport = StandardLibraryStreamingTransport(approved_hosts=HOSTS, connection_factory=factory)
    with pytest.raises(TransportConfigurationError):
        transport.open("https://www.defensoria.gob.pe/file.pdf", {header: "value"})
    assert calls == 0


def test_proxy_or_tls_override_environment_stops_before_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    calls = 0

    def factory(*args: Any, **kwargs: Any) -> FakeConnection:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    transport = StandardLibraryStreamingTransport(approved_hosts=HOSTS, connection_factory=factory)
    with pytest.raises(EnvironmentNetworkPolicyError):
        transport.open("https://www.defensoria.gob.pe/file.pdf", {})
    assert calls == 0


@pytest.mark.parametrize(
    "pairs",
    (
        [("Content-Type", "application/pdf"), ("content-type", "text/html")],
        [("Content-Length", "5"), ("Content-Length", "5")],
        [("Location", "/a"), ("location", "/a")],
        [("Transfer-Encoding", "chunked"), ("Content-Length", "5")],
        [("ETag", "safe\x00unsafe")],
        [("Bad Header", "value")],
    ),
)
def test_duplicate_or_ambiguous_safety_headers_reject_before_body(
    monkeypatch: pytest.MonkeyPatch, pairs: list[tuple[str, str]]
) -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    response = FakeHttpResponse(header_pairs=pairs)
    connection = FakeConnection(response)

    def factory(host: str, port: int, timeout: int, context: ssl.SSLContext) -> FakeConnection:
        del host, port, timeout, context
        return connection

    transport = StandardLibraryStreamingTransport(
        approved_hosts=HOSTS,
        connection_factory=factory,
    )

    with pytest.raises(MalformedResponseHeaders):
        transport.open("https://www.defensoria.gob.pe/file.pdf", {})
    assert response.read_sizes == []
    assert response.closed is True
    assert connection.closed is True
