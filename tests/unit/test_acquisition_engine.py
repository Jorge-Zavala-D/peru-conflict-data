from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import pytest

from peru_conflicts.acquisition.engine import (
    AcquisitionClient,
    DownloadByteBudget,
    StreamingTransport,
)
from peru_conflicts.acquisition.models import NetworkAuthorizationArtifact
from peru_conflicts.acquisition.plan import load_reviewed_pilot_plan
from peru_conflicts.acquisition.policy import require_network_authorization

V2_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml")
V2_SHA256 = "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"
PDF_URL = (
    "https://www.defensoria.gob.pe/wp-content/uploads/2025/11/"
    "Reporte-Mensual-de-Conflictos-Sociales-N°-260-Oct_2025.pdf"
)
PDF_URL_261 = "https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf"
LANDING_URL = (
    "https://www.defensoria.gob.pe/documentos/reporte-de-conflictos-sociales-n-o-260-octubre-2025/"
)


def _make_directory_alias(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    escaped_link = str(link).replace("'", "''")
    escaped_target = str(target).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop'; "
        f"New-Item -ItemType Junction -Path '{escaped_link}' "
        f"-Target '{escaped_target}' | Out-Null"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
    )


def _empty_float_list() -> list[float]:
    return []


@dataclass
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    chunks: tuple[bytes, ...] = ()
    body_iterated: bool = False
    closed: bool = False

    def iter_bytes(self) -> Iterable[bytes]:
        self.body_iterated = True
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeTime:
    seconds: float = 0.0
    sleeps: list[float] = field(default_factory=_empty_float_list)

    def clock(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.seconds += seconds

    def utc(self) -> datetime:
        return datetime(2026, 8, 28, tzinfo=UTC) + timedelta(seconds=self.seconds)


class FakeTransport:
    follows_redirects = False

    def __init__(self, responses: list[FakeResponse | BaseException], *, time: FakeTime) -> None:
        self.responses = responses
        self.time = time
        self.calls: list[tuple[str, int, Mapping[str, str], float]] = []

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: int,
    ) -> FakeResponse:
        self.calls.append((url, timeout_seconds, headers, self.time.seconds))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def robots(*, allow: bool = True) -> FakeResponse:
    rule = b"Allow: /" if allow else b"Disallow: /"
    return FakeResponse(
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
        (b"User-agent: *\n" + rule + b"\n",),
    )


def pdf_response(
    content: bytes,
    *,
    headers: Mapping[str, str] | None = None,
    chunks: tuple[bytes, ...] | None = None,
) -> FakeResponse:
    values = {
        "Content-Type": "application/pdf; charset=binary",
        "Content-Length": str(len(content)),
        **(headers or {}),
    }
    return FakeResponse(200, values, chunks or (content,))


def _client(
    tmp_path: Path,
    transport: FakeTransport,
    time: FakeTime,
    *,
    attempt_limit: int = 60,
    total_limit: int = 500_000_000,
    system_temp_root: Path | None = None,
) -> AcquisitionClient:

    loaded = load_reviewed_pilot_plan(V2_PATH, required_sha256=V2_SHA256)
    artifact = NetworkAuthorizationArtifact(
        schema_version="0.1.0",
        authorization_id="synthetic-owner-review",
        authorization_status="authorized",
        scope="m1_03b_reports_260_269_network",
        plan_id=loaded.plan.plan_id,
        plan_file_sha256=loaded.file_sha256,
        baseline_git_commit=loaded.plan.baseline_receipt_git_commit,
        approved_by="synthetic-test-owner",
        approved_at=datetime(2026, 8, 28, tzinfo=UTC),
    )

    def transport_factory() -> StreamingTransport:
        return transport

    grant = require_network_authorization(loaded, artifact, transport_factory)
    return AcquisitionClient(
        grant=grant,
        system_temp_root=system_temp_root or tmp_path / "system-temp",
        attempt_limit=attempt_limit,
        total_byte_limit=total_limit,
        monotonic_clock=time.clock,
        sleeper=time.sleep,
        utc_clock=time.utc,
    )


def test_transport_that_auto_follows_redirects_is_rejected_before_any_request(
    tmp_path: Path,
) -> None:
    class UnsafeTransport(FakeTransport):
        follows_redirects = True

    time = FakeTime()
    transport = UnsafeTransport([robots()], time=time)

    with pytest.raises(ValueError, match="must not automatically follow redirects"):
        _client(tmp_path, transport, time)

    assert transport.calls == []


def test_download_budget_cannot_be_widened_or_reset() -> None:
    budget = DownloadByteBudget(limit=500_000_000)

    with pytest.raises(FrozenInstanceError):
        budget.limit = 900_000_000  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        budget.used = 0  # type: ignore[misc]


def test_preexisting_run_directory_alias_is_rejected_before_body_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.engine as engine
    import peru_conflicts.acquisition.fs_safety as fs_safety

    content = b"%PDF-1.7\n" + b"x" * 1200
    response = pdf_response(content)
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), response], time=time), time)
    run_directory = tmp_path / "system-temp" / "synthetic-run"
    run_directory.mkdir(parents=True)
    real_reparse = fs_safety._is_reparse_point  # pyright: ignore[reportPrivateUsage]

    def is_reparse(path: Path) -> bool:
        return path == run_directory or real_reparse(path)

    monkeypatch.setattr(
        fs_safety,
        "_is_reparse_point",
        is_reparse,
    )

    with pytest.raises(engine.TemporaryPathBoundaryError, match="temporary directory"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert response.body_iterated is False
    assert not list(run_directory.glob("*.partial"))


def test_run_directory_alias_swap_before_partial_name_is_rejected_before_body_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.engine as engine
    import peru_conflicts.acquisition.fs_safety as fs_safety

    content = b"%PDF-1.7\n" + b"x" * 1200
    response = pdf_response(content)
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), response], time=time), time)
    run_directory = tmp_path / "system-temp" / "synthetic-run"
    alias_active = False
    real_uuid4 = engine.uuid.uuid4
    real_reparse = fs_safety._is_reparse_point  # pyright: ignore[reportPrivateUsage]

    def swap_before_name() -> object:
        nonlocal alias_active
        alias_active = True
        return real_uuid4()

    def is_reparse(path: Path) -> bool:
        return (alias_active and path == run_directory) or real_reparse(path)

    monkeypatch.setattr(engine.uuid, "uuid4", swap_before_name)
    monkeypatch.setattr(fs_safety, "_is_reparse_point", is_reparse)

    with pytest.raises(engine.TemporaryPathBoundaryError, match="temporary directory"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert response.body_iterated is False
    assert not list((tmp_path / "system-temp").rglob("*.partial"))


def test_transient_run_directory_swap_at_open_never_writes_outside_system_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.engine as engine
    import peru_conflicts.acquisition.fs_safety as fs_safety

    content = b"%PDF-1.7\n" + b"x" * 1200
    response = pdf_response(content)
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), response], time=time), time)
    run_directory = tmp_path / "system-temp" / "aba-run"
    saved_directory = tmp_path / "system-temp" / "aba-run-saved"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_open = fs_safety.DirectoryLease.open_child_exclusive
    fired = False
    swap_blocked = False

    def swap_at_open(lease: fs_safety.DirectoryLease, name: str) -> BinaryIO:
        nonlocal fired, swap_blocked
        if lease.path != run_directory:
            return real_open(lease, name)
        fired = True
        try:
            run_directory.rename(saved_directory)
        except OSError:
            swap_blocked = True
            return real_open(lease, name)
        try:
            try:
                run_directory.symlink_to(outside, target_is_directory=True)
            except OSError:
                pytest.skip("directory symlinks are unavailable on this host")
            return real_open(lease, name)
        finally:
            if run_directory.is_symlink():
                run_directory.unlink()
            saved_directory.rename(run_directory)

    monkeypatch.setattr(fs_safety.DirectoryLease, "open_child_exclusive", swap_at_open)

    try:
        downloaded = client.fetch_pdf(PDF_URL, run_id="aba-run", report_number=260)
    except engine.TemporaryPathBoundaryError:
        downloaded = None

    assert fired
    assert swap_blocked or downloaded is None
    assert not list(outside.iterdir())
    assert not list((tmp_path / "system-temp").rglob("*.partial"))


def test_transport_and_close_interruptions_are_receipted_before_reraise(tmp_path: Path) -> None:
    time = FakeTime()
    transport_interrupted = _client(
        tmp_path,
        FakeTransport([KeyboardInterrupt()], time=time),
        time,
    )
    with pytest.raises(KeyboardInterrupt):
        transport_interrupted.fetch_pdf(PDF_URL, run_id="transport-stop", report_number=260)
    assert transport_interrupted.receipts[-1].outcome.value == "interrupted"  # type: ignore[attr-defined]
    assert transport_interrupted.receipts[-1].error_code == "transport_interrupted"  # type: ignore[attr-defined]

    class CloseInterrupted(FakeResponse):
        def close(self) -> None:
            self.closed = True
            raise KeyboardInterrupt

    content = b"%PDF-1.7\n" + b"x" * 1200
    close_response = CloseInterrupted(
        200,
        {"Content-Type": "application/pdf", "Content-Length": str(len(content))},
        (content,),
    )
    close_time = FakeTime()
    close_interrupted = _client(
        tmp_path,
        FakeTransport([robots(), close_response], time=close_time),
        close_time,
    )
    with pytest.raises(KeyboardInterrupt):
        close_interrupted.fetch_pdf(PDF_URL, run_id="close-stop", report_number=260)
    assert close_interrupted.failure_receipts[-1].error_code == "response_close_interrupted"  # type: ignore[attr-defined]
    assert close_interrupted.failure_receipts[-1].related_attempt_id is not None  # type: ignore[attr-defined]
    assert not list((tmp_path / "system-temp" / "close-stop").glob("*.pdf"))


def test_redirect_receipt_redacts_credentials_queries_and_unknown_rate_headers(
    tmp_path: Path,
) -> None:
    from peru_conflicts.acquisition.policy import UnapprovedAcquisitionUrl

    redirect = FakeResponse(
        302,
        {
            "Location": ("https://user:secret@defensoria.gob.pe/second.pdf?token=SECRET123"),
            "X-RateLimit-Remaining": "59",
            "X-RateLimit-Secret": "DO_NOT_KEEP",
        },
    )
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), redirect], time=time), time)

    with pytest.raises(UnapprovedAcquisitionUrl):
        client.fetch_pdf(PDF_URL, run_id="safe-receipt", report_number=260)

    rendered = client.receipts[-1].model_dump_json()  # type: ignore[attr-defined]
    assert "secret" not in rendered.lower()
    assert "token" not in rendered.lower()
    assert "DO_NOT_KEEP" not in rendered
    assert "x-ratelimit-remaining" in rendered
    assert client.receipts[-1].response_headers.location_sha256 is not None  # type: ignore[attr-defined,union-attr]


def test_adversarial_allowlisted_headers_cannot_break_receipts_or_strand_pdf(
    tmp_path: Path,
) -> None:
    unsafe_value = "x" * 201 + "\r\nsecret"
    content = b"%PDF-1.7\n" + b"x" * 1200
    redirect_target = "https://www.defensoria.gob.pe/wp-content/uploads/redirected.pdf"
    responses: list[FakeResponse | BaseException] = [
        FakeResponse(
            200,
            {
                "Content-Type": "text/plain",
                "X-RateLimit-Remaining": unsafe_value,
            },
            (b"User-agent: *\nAllow: /\n",),
        ),
        FakeResponse(
            302,
            {
                "Location": redirect_target,
                "X-RateLimit-Remaining": unsafe_value,
            },
        ),
        FakeResponse(
            503,
            {
                "Content-Type": "text/plain",
                "X-RateLimit-Remaining": unsafe_value,
            },
        ),
        pdf_response(content, headers={"X-RateLimit-Remaining": unsafe_value}),
    ]
    time = FakeTime()
    client = _client(tmp_path, FakeTransport(responses, time=time), time)

    downloaded = client.fetch_pdf(PDF_URL, run_id="safe-headers", report_number=260)

    assert downloaded.path.read_bytes() == content
    assert len(client.receipts) == 4
    for receipt in client.receipts:
        assert receipt.response_headers is not None
        for header in receipt.response_headers.rate_limit_headers:
            assert header.name == "x-ratelimit-remaining"
            assert header.value.startswith("[redacted unsafe metadata sha256=")
            assert len(header.value) <= 200
            assert "\r" not in header.value and "\n" not in header.value
    assert not list((tmp_path / "system-temp").rglob("*.partial"))


def test_landing_html_uses_scoped_html_validation_without_file_writes(tmp_path: Path) -> None:
    body = b"<html lang='es'><title>Reporte 260</title></html>"
    html = FakeResponse(
        200,
        {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body))},
        (body,),
    )
    time = FakeTime()
    transport = FakeTransport([robots(), html], time=time)
    client = _client(tmp_path, transport, time)

    evidence = client.fetch_landing_html(
        LANDING_URL,
        run_id="landing-evidence",
        report_number=260,
    )

    assert evidence.body == body
    assert evidence.sha256 == hashlib.sha256(body).hexdigest()
    assert evidence.final_url == LANDING_URL
    assert transport.calls[-1][2]["Accept"] == "text/html, application/xhtml+xml"
    assert not (tmp_path / "system-temp").exists()


def test_landing_binary_mime_is_rejected_before_body_iteration(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    binary = FakeResponse(
        200,
        {"Content-Type": "application/octet-stream", "Content-Length": "100"},
        (b"do not read",),
    )
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), binary], time=time), time)

    with pytest.raises(ResponseRejected, match="HTML/XHTML"):
        client.fetch_landing_html(
            LANDING_URL,
            run_id="landing-binary",
            report_number=260,
        )

    assert binary.body_iterated is False


def test_initial_report_url_pair_must_match_reviewed_pilot_before_robots_or_transport(
    tmp_path: Path,
) -> None:
    from peru_conflicts.acquisition.engine import PilotScopeError

    time = FakeTime()
    transport = FakeTransport([robots()], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(PilotScopeError, match="reviewed report/URL target"):
        client.fetch_pdf(
            "https://defensoria.gob.pe/wp-content/uploads/unreviewed.pdf",
            run_id="synthetic-run",
            report_number=260,
        )

    assert transport.calls == []


def test_system_temporary_root_and_run_identity_fail_before_transport(
    tmp_path: Path,
) -> None:
    time = FakeTime()
    transport = FakeTransport([robots()], time=time)
    with pytest.raises(ValueError, match="operating-system temporary directory"):
        _client(
            tmp_path,
            transport,
            time,
            system_temp_root=Path.cwd() / ".cache" / "not-system-temp",
        )
    assert transport.calls == []

    client = _client(tmp_path, transport, time)
    with pytest.raises(ValueError, match="path-safe"):
        client.fetch_pdf(PDF_URL, run_id="../unsafe", report_number=260)
    assert transport.calls == []


def test_robots_denial_prevents_pdf_request_and_temp_creation(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import RobotsDenied

    time = FakeTime()
    transport = FakeTransport([robots(allow=False)], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(RobotsDenied):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert len(transport.calls) == 1
    assert transport.calls[0][0] == "https://www.defensoria.gob.pe/robots.txt"
    assert not (tmp_path / "system-temp").exists()
    assert client.failure_receipts[-1].error_code == "robots_policy_denied"  # type: ignore[attr-defined]
    assert client.failure_receipts[-1].report_number == 260  # type: ignore[attr-defined]


def test_oversized_robots_body_preserves_attempt_and_failure_receipts(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    oversized = FakeResponse(
        200,
        {"Content-Type": "text/plain"},
        (b"User-agent: *\n", b"x" * 500_000),
    )
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([oversized], time=time), time)

    with pytest.raises(ResponseRejected, match="byte ceiling"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert client.receipts[-1].error_code == "robots_body_too_large"  # type: ignore[attr-defined]
    assert client.receipts[-1].transferred_bytes > 500_000  # type: ignore[attr-defined]
    assert client.failure_receipts[-1].stage.value == "robots_body"  # type: ignore[attr-defined]


def test_robots_stream_failure_preserves_failure_receipt(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    class BrokenRobots(FakeResponse):
        def iter_bytes(self) -> Iterable[bytes]:
            self.body_iterated = True
            yield b"User-agent: *\n"
            raise OSError("synthetic robots interruption")

    broken = BrokenRobots(200, {"Content-Type": "text/plain"})
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([broken], time=time), time)

    with pytest.raises(ResponseRejected, match="stream failed"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert client.receipts[-1].error_code == "robots_body_stream_failure"  # type: ignore[attr-defined]
    assert client.failure_receipts[-1].error_code == "robots_body_stream_failure"  # type: ignore[attr-defined]


def test_unlisted_mime_is_rejected_before_body_iteration(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    binary = FakeResponse(
        200,
        {"Content-Type": "application/octet-stream", "Content-Length": "2048"},
        (b"not read",),
    )
    time = FakeTime()
    transport = FakeTransport([robots(), binary], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(ResponseRejected, match="Content-Type"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert binary.body_iterated is False
    assert not (tmp_path / "system-temp").exists()
    assert client.receipts[-1].error_code == "rejected_content_type"  # type: ignore[attr-defined]


def test_streams_synthetic_pdf_with_chunk_independent_magic_and_hash(tmp_path: Path) -> None:
    content = b"%PDF-1.7\n" + b"x" * 1200
    response = pdf_response(content, chunks=(b"%P", b"DF-", content[5:17], content[17:]))
    time = FakeTime()
    transport = FakeTransport([robots(), response], time=time)
    client = _client(tmp_path, transport, time)

    downloaded = client.fetch_pdf(  # type: ignore[attr-defined]
        PDF_URL,
        run_id="synthetic-run",
        report_number=260,
    )

    assert downloaded.path.read_bytes() == content
    assert downloaded.byte_count == len(content)
    assert downloaded.sha256 == hashlib.sha256(content).hexdigest()
    assert downloaded.path.is_relative_to((tmp_path / "system-temp").resolve())
    assert all(call[1] == 30 for call in transport.calls)
    assert all(
        "Authorization" not in call[2] and "Cookie" not in call[2] for call in transport.calls
    )
    assert len(client.receipts) == 2  # type: ignore[attr-defined]
    assert client.receipts[-1].complete_body_sha256 == downloaded.sha256  # type: ignore[attr-defined]


def test_response_close_failure_does_not_mask_validated_download(tmp_path: Path) -> None:
    class CloseFailureResponse(FakeResponse):
        def close(self) -> None:
            self.closed = True
            raise OSError("synthetic close failure")

    content = b"%PDF-1.7\n" + b"x" * 1200
    pdf = CloseFailureResponse(
        200,
        {"Content-Type": "application/pdf", "Content-Length": str(len(content))},
        (content,),
    )
    time = FakeTime()
    client = _client(tmp_path, FakeTransport([robots(), pdf], time=time), time)

    downloaded = client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert downloaded.sha256 == hashlib.sha256(content).hexdigest()
    assert client.receipts[-1].outcome.value == "success"  # type: ignore[attr-defined]
    assert client.failure_receipts[-1].error_code == "response_close_failure"  # type: ignore[attr-defined]
    assert client.failure_receipts[-1].cleanup_completed is False  # type: ignore[attr-defined]


def test_redirect_close_failure_keeps_the_response_url_as_provenance(tmp_path: Path) -> None:
    class RedirectCloseFailure(FakeResponse):
        def close(self) -> None:
            self.closed = True
            raise OSError("synthetic redirect close failure")

    content = b"%PDF-1.7\n" + b"x" * 1200
    redirect = RedirectCloseFailure(
        302,
        {"Location": "https://defensoria.gob.pe/second.pdf"},
    )
    time = FakeTime()
    transport = FakeTransport(
        [robots(), redirect, robots(), pdf_response(content)],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    close_failure = next(
        receipt
        for receipt in client.failure_receipts  # type: ignore[attr-defined]
        if receipt.error_code == "response_close_failure"
    )
    assert close_failure.url == PDF_URL


@pytest.mark.parametrize(
    ("content", "headers", "message"),
    (
        (b"NOT-PDF" + b"x" * 1200, {}, "magic"),
        (
            b"%PDF-1.7\n" + b"x" * 1200,
            {"Content-Length": "50000001"},
            "maximum",
        ),
        (
            b"%PDF-1.7\n" + b"x" * 100,
            {"Content-Length": "109"},
            "minimum",
        ),
        (
            b"%PDF-1.7\n" + b"x" * 1200,
            {"Content-Length": "9999"},
            "Content-Length",
        ),
        (
            b"%PDF-1.7\n" + b"x" * 1200,
            {"Content-Encoding": "gzip"},
            "Content-Encoding",
        ),
    ),
)
def test_rejected_or_truncated_pdf_cleans_owned_partial_and_preserves_receipt(
    tmp_path: Path,
    content: bytes,
    headers: Mapping[str, str],
    message: str,
) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    response = pdf_response(content, headers=headers)
    time = FakeTime()
    transport = FakeTransport([robots(), response], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(ResponseRejected, match=message):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert not list(tmp_path.rglob("*.partial"))
    assert client.receipts[-1].error_code is not None  # type: ignore[attr-defined]
    if message in {"maximum", "minimum", "Content-Encoding"}:
        assert response.body_iterated is False


def test_robots_transient_response_retries_with_receipts_and_spacing(tmp_path: Path) -> None:
    content = b"%PDF-1.7\n" + b"x" * 1200
    transient = FakeResponse(503, {"Content-Type": "text/plain", "Retry-After": "4"})
    time = FakeTime()
    transport = FakeTransport(
        [transient, robots(), pdf_response(content)],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert [call[3] for call in transport.calls] == [0.0, 4.0, 6.0]
    assert [receipt.outcome.value for receipt in client.receipts] == [
        "retryable_failure",
        "success",
        "success",
    ]


def test_robots_transport_retry_cap_stops_before_pdf(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import TransportFailure

    time = FakeTime()
    transport = FakeTransport(
        [OSError("one"), OSError("two"), OSError("three"), pdf_response(b"unused")],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    with pytest.raises(TransportFailure, match="robots transport failed after three attempts"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert len(transport.calls) == 3
    assert [receipt.request_kind.value for receipt in client.receipts] == [
        "robots",
        "robots",
        "robots",
    ]


def test_retry_cap_retry_after_spacing_and_attempt_receipts(tmp_path: Path) -> None:
    content = b"%PDF-1.7\n" + b"x" * 1200
    transient = FakeResponse(
        503,
        {"Content-Type": "text/plain", "Retry-After": "7"},
    )
    time = FakeTime()
    transport = FakeTransport(
        [robots(), transient, OSError("temporary disconnect"), pdf_response(content)],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    downloaded = client.fetch_pdf(  # type: ignore[attr-defined]
        PDF_URL,
        run_id="synthetic-run",
        report_number=260,
    )

    assert downloaded.sha256 == hashlib.sha256(content).hexdigest()
    assert [call[3] for call in transport.calls] == [0.0, 2.0, 9.0, 11.0]
    assert [receipt.outcome.value for receipt in client.receipts[-3:]] == [  # type: ignore[attr-defined]
        "retryable_failure",
        "retryable_failure",
        "success",
    ]
    assert len(transport.calls) == 4


def test_retry_cap_stops_after_three_pdf_attempts(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import TransportFailure

    time = FakeTime()
    transport = FakeTransport(
        [robots(), OSError("one"), OSError("two"), OSError("three"), pdf_response(b"unused")],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    with pytest.raises(TransportFailure, match="three attempts"):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert len(transport.calls) == 4
    assert len([item for item in client.receipts if item.request_kind.value == "pdf"]) == 3  # type: ignore[attr-defined]


def test_global_attempt_budget_stops_before_extra_transport_call(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.policy import AttemptBudgetExhausted

    redirect = FakeResponse(302, {"Location": "/second.pdf"})
    time = FakeTime()
    transport = FakeTransport([robots(), redirect, pdf_response(b"unused")], time=time)
    client = _client(tmp_path, transport, time, attempt_limit=2)

    with pytest.raises(AttemptBudgetExhausted):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert len(transport.calls) == 2


def test_off_host_redirect_is_rejected_without_requesting_destination(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.policy import UnapprovedAcquisitionUrl

    redirect = FakeResponse(302, {"Location": "https://example.org/report.pdf"})
    time = FakeTime()
    transport = FakeTransport([robots(), redirect], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(UnapprovedAcquisitionUrl):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert len(transport.calls) == 2
    assert redirect.body_iterated is False


def test_new_redirect_origin_requires_its_own_robots_check(tmp_path: Path) -> None:
    content = b"%PDF-1.7\n" + b"x" * 1200
    redirect = FakeResponse(
        302,
        {"Location": "https://defensoria.gob.pe/second.pdf"},
    )
    time = FakeTime()
    transport = FakeTransport(
        [robots(), redirect, robots(), pdf_response(content)],
        time=time,
    )
    client = _client(tmp_path, transport, time)

    client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert [call[0] for call in transport.calls] == [
        "https://www.defensoria.gob.pe/robots.txt",
        PDF_URL,
        "https://defensoria.gob.pe/robots.txt",
        "https://defensoria.gob.pe/second.pdf",
    ]


def test_interrupted_stream_removes_partial_but_preserves_failure_receipt(
    tmp_path: Path,
) -> None:
    class InterruptedResponse(FakeResponse):
        def iter_bytes(self) -> Iterable[bytes]:
            self.body_iterated = True
            yield b"%PDF-1.7\n" + b"x" * 1100
            raise KeyboardInterrupt

    response = InterruptedResponse(
        200,
        {"Content-Type": "application/pdf", "Content-Length": "2000"},
    )
    time = FakeTime()
    transport = FakeTransport([robots(), response], time=time)
    client = _client(tmp_path, transport, time)

    with pytest.raises(KeyboardInterrupt):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]

    assert not list(tmp_path.rglob("*.partial"))
    assert client.receipts[-1].outcome.value == "interrupted"  # type: ignore[attr-defined]
    assert client.receipts[-1].error_code == "stream_interrupted"  # type: ignore[attr-defined]


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_parent_swap_inside_child_open_cannot_escape_system_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety

    content = b"%PDF-1.7\n" + b"x" * 1200
    time = FakeTime()
    system_temp_root = tmp_path / "system-temp"
    client = _client(
        tmp_path,
        FakeTransport([robots(), pdf_response(content)], time=time),
        time,
        system_temp_root=system_temp_root,
    )
    run_directory = system_temp_root / "synthetic-run"
    saved_directory = system_temp_root / "synthetic-run-saved"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_open = fs_safety.os.open
    attacked = False

    def swap_only_inside_open(
        path: str | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal attacked
        candidate = Path(path)
        if not attacked and candidate.name.endswith(".pdf.partial"):
            attacked = True
            run_directory.rename(saved_directory)
            _make_directory_alias(run_directory, outside)
            try:
                return real_open(path, flags, mode, dir_fd=dir_fd)
            finally:
                run_directory.rmdir()
                saved_directory.rename(run_directory)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(fs_safety.os, "open", swap_only_inside_open)

    downloaded = client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert attacked is False
    assert downloaded.path.read_bytes() == content
    assert not list(outside.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction ABA regression")
def test_windows_native_relative_open_remains_bound_during_parent_swap(
    tmp_path: Path,
) -> None:
    import peru_conflicts.acquisition.fs_safety as fs_safety
    from peru_conflicts.acquisition.fs_safety import DirectoryLease

    content = b"%PDF-1.7\n" + b"x" * 1200
    system_temp_root = tmp_path / "system-temp"
    run_directory = system_temp_root / "synthetic-run"
    saved_directory = system_temp_root / "synthetic-run-saved"
    outside = tmp_path / "outside"
    run_directory.mkdir(parents=True)
    outside.mkdir()
    child_name = "report-260-synthetic.pdf.partial"

    with DirectoryLease.acquire(run_directory) as lease:
        run_directory.rename(saved_directory)
        _make_directory_alias(run_directory, outside)
        try:
            descriptor = fs_safety._windows_open_relative_file_descriptor(  # pyright: ignore[reportPrivateUsage]
                lease.windows_handle,
                child_name,
                write_exclusive=True,
            )
            try:
                os.write(descriptor, content)
            finally:
                os.close(descriptor)
            assert (saved_directory / child_name).read_bytes() == content
        finally:
            run_directory.rmdir()
            saved_directory.rename(run_directory)

    assert (run_directory / child_name).read_bytes() == content
    assert not list(outside.iterdir())


def test_interrupt_after_temp_rename_removes_complete_object_and_records_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.acquisition.fs_safety import DirectoryLease

    content = b"%PDF-1.7\n" + b"x" * 1200
    time = FakeTime()
    client = _client(
        tmp_path,
        FakeTransport([robots(), pdf_response(content)], time=time),
        time,
    )
    real_rename = DirectoryLease.rename_child_no_replace

    def rename_then_interrupt(
        directory: DirectoryLease, source_name: str, destination_name: str
    ) -> None:
        real_rename(directory, source_name, destination_name)
        raise KeyboardInterrupt

    monkeypatch.setattr(DirectoryLease, "rename_child_no_replace", rename_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)

    assert not list((tmp_path / "system-temp").rglob("*.partial"))
    assert not list((tmp_path / "system-temp").rglob("*.pdf"))
    assert client.receipts[-1].outcome.value == "interrupted"  # type: ignore[attr-defined]


def test_total_download_budget_rejects_second_object_and_cleans_partial(tmp_path: Path) -> None:
    from peru_conflicts.acquisition.engine import ResponseRejected

    first = b"%PDF-1.7\n" + b"a" * 1090
    second = b"%PDF-1.7\n" + b"b" * 1090
    time = FakeTime()
    transport = FakeTransport(
        [robots(), pdf_response(first), pdf_response(second)],
        time=time,
    )
    client = _client(tmp_path, transport, time, total_limit=len(first) + len(second) - 1)

    client.fetch_pdf(PDF_URL, run_id="synthetic-run", report_number=260)  # type: ignore[attr-defined]
    with pytest.raises(ResponseRejected, match="total byte ceiling"):
        client.fetch_pdf(
            PDF_URL_261,
            run_id="synthetic-run",
            report_number=261,
        )  # type: ignore[attr-defined]

    assert not list(tmp_path.rglob("*.partial"))
