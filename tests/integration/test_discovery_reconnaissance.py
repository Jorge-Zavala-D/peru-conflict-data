from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.discovery.client import (
    HtmlClient,
    HttpResponse,
    PdfBodyRejected,
    RobotsDenied,
)
from peru_conflicts.discovery.models import RedirectHop, UrlRole
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
        self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None
    ) -> HttpResponse:
        del headers
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
    )


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
            binary_url: [_response(binary_url, "%PDF-1.7", content_type="application/pdf")],
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


def test_output_path_refuses_data_root_and_runner_is_idempotent(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    with pytest.raises(OutputPathError):
        validate_output_dir(data_root / "01_raw", data_root=data_root)

    output = tmp_path / "cache"
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
    )
    run_reconnaissance(
        (CATALOGUE,),
        output_dir=output,
        client=client,
        surface_roles={CATALOGUE: UrlRole.CATALOGUE_PAGE},
        page_cap=2,
        max_landing_pages=0,
        captured_at=CAPTURED_AT,
    )
    first = {path.name: path.read_bytes() for path in output.iterdir()}

    second_transport = FakeTransport(responses)
    second_client = HtmlClient(
        frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
        transport=second_transport,
        delay_seconds=0.0,
    )
    run_reconnaissance(
        (CATALOGUE,),
        output_dir=output,
        client=second_client,
        surface_roles={CATALOGUE: UrlRole.CATALOGUE_PAGE},
        page_cap=2,
        max_landing_pages=0,
        captured_at=CAPTURED_AT,
    )
    second = {path.name: path.read_bytes() for path in output.iterdir()}

    assert first == second
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["stop_reasons"]
