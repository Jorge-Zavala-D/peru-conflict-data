from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path

import pytest

from peru_conflicts.discovery.client import (
    HtmlClient,
    HttpRequestError,
    HttpResponse,
    PdfBodyRejected,
    ResponseBodyTooLarge,
    RobotsDenied,
    UnapprovedRedirect,
    UrllibTransport,
)
from peru_conflicts.discovery.models import RedirectHop, UrlRole
from peru_conflicts.discovery.receipts import RequestOutcome
from peru_conflicts.discovery.reconnaissance import (
    OutputPathError,
    run_reconnaissance,
    validate_output_dir,
)

CAPTURED_AT = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
BASE = "https://www.defensoria.gob.pe"
CATALOGUE = f"{BASE}/categorias_de_documentos/reportes/"
ROBOTS = f"{BASE}/robots.txt"


class FakeTransport:
    def __init__(self, responses: dict[str, list[HttpResponse]]) -> None:
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        allowed_content_types: frozenset[str],
        max_body_bytes: int,
    ) -> HttpResponse:
        del headers, allowed_content_types, max_body_bytes
        self.calls.append((method, url))
        queued = self.responses.get(url)
        if not queued:
            raise AssertionError(f"unexpected request: {method} {url}")
        return queued.pop(0)


def _response(
    url: str,
    body: str,
    *,
    content_type: str = "text/html",
    status: int = 200,
    headers: dict[str, str] | None = None,
    body_read: bool = True,
) -> HttpResponse:
    response_headers = {"Content-Type": content_type}
    if headers:
        response_headers.update(headers)
    return HttpResponse(
        requested_url=url,
        final_url=url,
        status=status,
        headers=response_headers,
        body=body.encode("utf-8"),
        redirect_hops=(),
        body_read=body_read,
    )


def _utc_clock(*values: datetime) -> Callable[[], datetime]:
    iterator = iter(values)
    return lambda: next(iterator)


class _NoReadResponse:
    def __init__(self, content_type: str, *, content_length: int | None = None) -> None:
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.read_calls = 0

    def __enter__(self) -> _NoReadResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return CATALOGUE

    def read(self, _amount: int = -1) -> bytes:
        self.read_calls += 1
        return b"unapproved bytes"


class _SingleResponseOpener:
    def __init__(self, response: _NoReadResponse) -> None:
        self.response = response

    def open(self, *_args: object, **_kwargs: object) -> _NoReadResponse:
        return self.response


def test_transport_rejects_unlisted_mime_without_reading_response_body() -> None:
    response = _NoReadResponse("application/x-unfamiliar-binary")
    transport = UrllibTransport()
    transport._opener = _SingleResponseOpener(response)  # type: ignore[reportPrivateUsage]

    observed = transport.request(
        CATALOGUE,
        allowed_content_types=frozenset({"text/html", "application/xhtml+xml"}),
        max_body_bytes=1000,
    )

    assert observed.body == b""
    assert observed.body_read is False
    assert response.read_calls == 0


def test_transport_rejects_declared_oversize_body_before_reading() -> None:
    response = _NoReadResponse("text/html", content_length=1001)
    transport = UrllibTransport()
    transport._opener = _SingleResponseOpener(response)  # type: ignore[reportPrivateUsage]

    observed = transport.request(
        CATALOGUE,
        allowed_content_types=frozenset({"text/html", "application/xhtml+xml"}),
        max_body_bytes=1000,
    )

    assert observed.body_too_large is True
    assert observed.body_read is False
    assert response.read_calls == 0


def test_client_honors_robots_and_never_gets_a_pdf_body() -> None:
    transport = FakeTransport(
        {
            ROBOTS: [
                _response(ROBOTS, "User-agent: *\nDisallow: /private\n", content_type="text/plain")
            ],
            f"{BASE}/private/": [_response(f"{BASE}/private/", "forbidden")],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(RobotsDenied):
        client.fetch_html(f"{BASE}/private/", role=UrlRole.LANDING_PAGE)
    with pytest.raises(PdfBodyRejected):
        client.fetch_html(f"{BASE}/wp-content/uploads/report.pdf", role=UrlRole.DIRECT_DOWNLOAD)

    assert ("GET", f"{BASE}/private/") not in transport.calls
    assert all(not url.lower().endswith(".pdf") for _, url in transport.calls)


def test_client_rejects_pdf_content_type_before_decoding_body() -> None:
    binary_url = f"{BASE}/download?id=269"
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            binary_url: [
                _response(
                    binary_url,
                    "%PDF-1.7",
                    content_type="application/pdf",
                    body_read=False,
                )
            ],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(PdfBodyRejected):
        client.fetch_html(binary_url, role=UrlRole.LANDING_PAGE)

    assert transport.calls[-1] == ("GET", binary_url)


def test_client_retries_transient_response_and_honors_retry_after() -> None:
    sleeps: list[float] = []
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [
                _response(CATALOGUE, "busy", status=503, headers={"Retry-After": "4"}),
                _response(CATALOGUE, "<html><body>ok</body></html>"),
            ],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=2.0,
        retry_cap=2,
        sleep=sleeps.append,
    )

    fetched = client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    assert fetched.body == "<html><body>ok</body></html>"
    assert (
        len([url for method, url in transport.calls if method == "GET" and url == CATALOGUE]) == 2
    )
    assert sleeps == [2.0, 4.0]
    attempts = [item for item in client.request_receipts if item.requested_url == CATALOGUE]
    assert [item.outcome for item in attempts] == [
        RequestOutcome.TRANSIENT_HTTP,
        RequestOutcome.SUCCESS,
    ]
    assert [item.attempt_number for item in attempts] == [1, 2]
    assert attempts[0].retry_scheduled is True
    assert attempts[0].retry_delay_seconds == 4.0


def test_oversize_http_response_is_not_misreported_or_retried_as_transport_error() -> None:
    oversized = HttpResponse(
        requested_url=CATALOGUE,
        final_url=CATALOGUE,
        status=200,
        headers={"Content-Type": "text/html", "Content-Length": "5000001"},
        body=b"",
        body_read=False,
        body_complete=False,
        body_too_large=True,
    )
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [oversized],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(ResponseBodyTooLarge):
        client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    attempts = [item for item in client.request_receipts if item.requested_url == CATALOGUE]
    assert len(attempts) == 1
    assert attempts[0].outcome is RequestOutcome.REJECTED_BODY_SIZE
    assert attempts[0].status_code == 200
    assert attempts[0].selected_headers.content_length_original == "5000001"


def test_attempt_receipts_preserve_timestamps_selected_headers_and_body_hash() -> None:
    body = "<html><body>fuente oficial</body></html>"
    transport = FakeTransport(
        {
            ROBOTS: [
                _response(
                    ROBOTS,
                    "User-agent: *\nAllow: /\n",
                    content_type="text/plain; charset=UTF-8",
                )
            ],
            CATALOGUE: [
                _response(
                    CATALOGUE,
                    body,
                    headers={
                        "Content-Length": str(len(body.encode("utf-8"))),
                        "ETag": '"official-page"',
                        "Last-Modified": "Thu, 27 Aug 2026 18:00:00 GMT",
                        "X-RateLimit-Remaining": "17",
                        "X-RateLimit-Reset": "",
                        "Set-Cookie": "must-not-be-retained=secret",
                    },
                )
            ],
        }
    )
    times = tuple(datetime(2026, 8, 27, 18, 0, second, tzinfo=UTC) for second in range(4))
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
        utc_clock=_utc_clock(*times),
    )

    client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    assert len(client.request_receipts) == 2
    page_receipt = client.request_receipts[1]
    assert page_receipt.requested_at == times[2]
    assert page_receipt.completed_at == times[3]
    assert page_receipt.selected_headers.etag_original == '"official-page"'
    assert page_receipt.selected_headers.last_modified_original is not None
    assert page_receipt.selected_headers.rate_limit_headers[0].value == "17"
    assert page_receipt.selected_headers.rate_limit_headers[1].value == ""
    assert "cookie" not in page_receipt.model_dump_json().lower()
    assert page_receipt.body_byte_count == len(body.encode("utf-8"))
    assert page_receipt.body_sha256 == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_client_preserves_redirect_observation_without_following_pdf() -> None:
    redirected = f"{BASE}/redirected/"
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [
                HttpResponse(
                    requested_url=CATALOGUE,
                    final_url=redirected,
                    status=200,
                    headers={"Content-Type": "text/html"},
                    body=b"<html><body>ok</body></html>",
                    redirect_hops=(
                        RedirectHop(
                            from_url=CATALOGUE,
                            to_url=redirected,
                            status_code=302,
                            captured_at=CAPTURED_AT,
                        ),
                    ),
                )
            ],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    fetched = client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE, captured_at=CAPTURED_AT)

    assert fetched.observation.redirect_hops[0].to_url == redirected
    assert fetched.observation.url == redirected


def test_redirect_attempt_preserves_target_even_when_destination_fails() -> None:
    failed = f"{BASE}/failed-destination/"
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [
                _response(
                    CATALOGUE,
                    "",
                    status=302,
                    headers={"Location": "/failed-destination/"},
                    body_read=False,
                )
            ],
            failed: [_response(failed, "not found", status=404, body_read=False)],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(HttpRequestError, match="unexpected HTTP status 404"):
        client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    redirect = next(
        item for item in client.request_receipts if item.outcome is RequestOutcome.REDIRECT
    )
    assert redirect.selected_headers.location_original == "/failed-destination/"
    assert redirect.redirect_target_url == failed


@pytest.mark.parametrize(
    ("headers", "location_original"),
    [({}, None), ({"Location": "https://"}, "https://")],
)
def test_malformed_redirect_is_receipted_before_terminal_failure(
    headers: dict[str, str],
    location_original: str | None,
) -> None:
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [_response(CATALOGUE, "", status=302, headers=headers, body_read=False)],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(HttpRequestError, match="redirect"):
        client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    attempts = [item for item in client.request_receipts if item.requested_url == CATALOGUE]
    assert len(attempts) == 1
    assert attempts[0].outcome is RequestOutcome.REJECTED_REDIRECT
    assert attempts[0].status_code == 302
    assert attempts[0].selected_headers.location_original == location_original
    assert attempts[0].redirect_target_url is None


def test_redirect_cannot_downgrade_https_or_reuse_https_robots_for_http() -> None:
    insecure = "http://www.defensoria.gob.pe/page/2/"
    transport = FakeTransport(
        {
            ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
            CATALOGUE: [
                _response(
                    CATALOGUE,
                    "",
                    status=302,
                    headers={"Location": insecure},
                    body_read=False,
                )
            ],
            insecure: [_response(insecure, "<html><body>inseguro</body></html>")],
        }
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(UnapprovedRedirect, match="HTTPS"):
        client.fetch_html(CATALOGUE, role=UrlRole.CATALOGUE_PAGE)

    assert ("GET", insecure) not in transport.calls


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://www.defensoria.gob.pe/reportes/",
        "https://www.defensoria.gob.pe:444/reportes/",
    ],
)
def test_initial_url_requires_https_and_default_port_before_network(unsafe_url: str) -> None:
    transport = FakeTransport({})
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=transport,
        delay_seconds=0.0,
    )

    with pytest.raises(UnapprovedRedirect, match=r"HTTPS.*default port"):
        client.fetch_html(unsafe_url, role=UrlRole.CATALOGUE_PAGE)

    assert transport.calls == []


def test_runner_requires_explicit_repository_cache_boundary_before_writing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "Dropbox" / "unapproved"
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=FakeTransport({}),
        delay_seconds=0.0,
    )

    with pytest.raises(OutputPathError, match="repo_root"):
        run_reconnaissance((CATALOGUE,), output_dir=output, client=client)
    assert not output.exists()


def test_output_path_refuses_data_root_and_runner_is_idempotent(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    with pytest.raises(OutputPathError):
        validate_output_dir(data_root / "01_raw", data_root=data_root)

    output = tmp_path / ".cache" / "idempotent"
    body = "<html><body><h1>Reporte de conflictos sociales N.° 269 - julio 2026</h1></body></html>"
    responses = {
        ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
        CATALOGUE: [_response(CATALOGUE, body)],
    }
    first_transport = FakeTransport(responses)
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=first_transport,
        delay_seconds=0.0,
        utc_clock=lambda: CAPTURED_AT,
    )
    run_reconnaissance(
        (CATALOGUE,),
        output_dir=output,
        client=client,
        surface_roles={CATALOGUE: UrlRole.CATALOGUE_PAGE},
        page_cap=2,
        max_landing_pages=0,
        captured_at=CAPTURED_AT,
        utc_clock=lambda: CAPTURED_AT,
        repo_root=tmp_path,
    )
    first = {path.name: path.read_bytes() for path in output.iterdir()}

    second_transport = FakeTransport(responses)
    second_client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=second_transport,
        delay_seconds=0.0,
        utc_clock=lambda: CAPTURED_AT,
    )
    run_reconnaissance(
        (CATALOGUE,),
        output_dir=output,
        client=second_client,
        surface_roles={CATALOGUE: UrlRole.CATALOGUE_PAGE},
        page_cap=2,
        max_landing_pages=0,
        captured_at=CAPTURED_AT,
        utc_clock=lambda: CAPTURED_AT,
        repo_root=tmp_path,
    )
    second = {path.name: path.read_bytes() for path in output.iterdir()}

    assert first == second
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["surface_traversals"]
    assert summary["corpus_completeness_status"] == "not_assessed"
    assert "complete" not in summary
    request_rows = [
        json.loads(line)
        for line in (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(row["schema_version"] == "0.3.0" for row in request_rows)


def test_runner_never_queues_page_chrome_landing_links(tmp_path: Path) -> None:
    candidate = f"{BASE}/documentos/reporte-269/"
    navigation = f"{BASE}/documentos/navigation-report/"
    body = (
        "<html><body><nav><a href='/documentos/navigation-report/'>"
        "Reporte de conflictos sociales N.° 999 - enero 2020</a></nav>"
        "<article><a href='/documentos/reporte-269/'>"
        "Reporte de conflictos sociales N.° 269 - julio 2026</a></article>"
        "</body></html>"
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=FakeTransport(
            {
                ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
                CATALOGUE: [_response(CATALOGUE, body)],
            }
        ),
        delay_seconds=0.0,
        utc_clock=lambda: CAPTURED_AT,
    )

    summary = run_reconnaissance(
        (CATALOGUE,),
        output_dir=tmp_path / ".cache" / "page-chrome",
        client=client,
        surface_roles={CATALOGUE: UrlRole.CATALOGUE_PAGE},
        page_cap=1,
        max_landing_pages=0,
        captured_at=CAPTURED_AT,
        utc_clock=lambda: CAPTURED_AT,
        repo_root=tmp_path,
    )

    assert summary.landing_pages.discovered == 1
    assert candidate != navigation


def test_single_page_surface_does_not_follow_a_visible_next_link(tmp_path: Path) -> None:
    body = (
        "<html><body><h1>Paz social y prevención de conflictos</h1>"
        "<a rel='next' href='/page/2/'>Siguiente</a></body></html>"
    )
    client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=FakeTransport(
            {
                ROBOTS: [_response(ROBOTS, "User-agent: *\nAllow: /\n", content_type="text/plain")],
                CATALOGUE: [_response(CATALOGUE, body)],
            }
        ),
        delay_seconds=0.0,
        utc_clock=lambda: CAPTURED_AT,
    )

    summary = run_reconnaissance(
        (CATALOGUE,),
        output_dir=tmp_path / ".cache" / "single",
        client=client,
        surface_roles={CATALOGUE: UrlRole.THEMATIC_PAGE},
        surface_pagination_modes={CATALOGUE: "single_page"},
        pagination_contract_verified={CATALOGUE: True},
        page_cap=5,
        captured_at=CAPTURED_AT,
        utc_clock=lambda: CAPTURED_AT,
        repo_root=tmp_path,
    )

    traversal = summary.surface_traversals[0]
    assert traversal.pages_visited == 1
    assert traversal.stop_reason.value == "single_page"
    assert traversal.reached_local_terminal is True
    assert traversal.pagination_exhausted is False
