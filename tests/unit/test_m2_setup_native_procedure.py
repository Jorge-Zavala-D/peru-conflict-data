"""Installed execution against HTTP-shaped independent service state, never sockets."""

import io
import json
import ssl
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_m2_setup_deployment import installation_fixture

from peru_conflicts.execution import setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_deployment import (
    Installation,
    _load_verified,  # pyright: ignore[reportPrivateUsage]
)
from peru_conflicts.execution.setup_dropbox import (
    _SCOPES,  # pyright: ignore[reportPrivateUsage]
    PROBE,
    Exchange,
    PreparedRequest,
    encode_request,
)
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP

# Reuse this explicitly test-owned installation seam; no production trust selector.
load_test_context = _load_verified


def test_native_canonical_upload_preserves_exact_probe_bytes() -> None:
    request = encode_request(
        "files/upload",
        {
            "path": "/synthetic/probe",
            "mode": {".tag": "add"},
            "autorename": False,
            "strict_conflict": True,
        },
        "synthetic-root",
        "synthetic-session",
        upload=PROBE,
    )
    setup_transport._canonical(request)  # pyright: ignore[reportPrivateUsage]


def connect_service(
    monkeypatch: pytest.MonkeyPatch,
    service: FakeHTTP,
    after_read: Callable[[bytes], None] | None = None,
    *,
    response_factory: Callable[[Exchange], Any] | None = None,
    before_request: Callable[[PreparedRequest], None] | None = None,
    on_close: Callable[[], None] | None = None,
) -> None:
    """Only replace HTTP connections and credential retrieval, not the collector."""

    class Connection:
        def __init__(self, host: str, *, timeout: float, context: ssl.SSLContext):
            assert host in ("api.dropboxapi.com", "content.dropboxapi.com")
            assert 0 < timeout <= 15
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED

        def request(self, method: str, path: str, body: bytes, headers: dict[str, str]):
            assert method == "POST" and path.startswith("/2/")
            token = headers["Authorization"].removeprefix("Bearer SYNTHETIC-")
            assert token in service.accounts
            route = path.removeprefix("/2/")
            args = json.loads(headers.get("Dropbox-API-Arg", body or b"{}"))
            request = encode_request(
                route,
                args,
                json.loads(headers["Dropbox-API-Path-Root"])["namespace_id"],
                token,
                upload=body if route == "files/upload" else None,
            )
            service.dispatches += 1
            if before_request is not None:
                before_request(request)
            self.exchange = service._respond(request, None)  # pyright: ignore[reportPrivateUsage]

        def getresponse(self):
            exchange = self.exchange
            if response_factory is not None:
                return response_factory(exchange)

            class Response:
                status = exchange.status
                stream = io.BytesIO(bytes.fromhex(exchange.response_hex))

                def getheader(self, name: str, default: str | None = None):
                    return {
                        "x-dropbox-request-id": exchange.provider_request_id,
                        "dropbox-api-result": exchange.result_header,
                    }.get(name.lower(), default)

                def read(self, size: int):
                    chunk = self.stream.read(size)
                    if after_read is not None:
                        after_read(chunk)
                    return chunk

                read1 = read

                def getheaders(self):
                    return [
                        (k, v)
                        for k, v in (
                            ("x-dropbox-request-id", exchange.provider_request_id),
                            ("dropbox-api-result", exchange.result_header),
                        )
                        if v is not None
                    ]

            return Response()

        def close(self):
            if on_close is not None:
                on_close()

    monkeypatch.setattr(setup_transport, "_connection", Connection)

    def credential(reference: str) -> str:
        return "SYNTHETIC-" + reference

    monkeypatch.setattr(setup_transport, "_read_credential", credential)


@pytest.mark.parametrize("action", ["root", "create"])
def test_expired_inflight_capture_retains_original_without_further_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    root, grant, installation, bindings = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(installation)
    installation = (
        pin.model_copy(
            update={
                "credential_refs": {s: s for s in pin.credential_refs},
                "scopes": {s: tuple(sorted(set(_SCOPES.values()))) for s in pin.credential_refs},
            }
        )
        .model_dump_json()
        .encode()
    )
    clock = [NOW]
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: clock[0],
    )
    service = FakeHTTP(None)
    returned: list[bytes] = []
    expire = [False]

    def after_read(raw: bytes) -> None:
        if expire[0]:
            returned.append(raw)
            clock[0] += timedelta(days=2)

    connect_service(monkeypatch, service, after_read)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        if action == "create":
            for _ in range(10):
                if journal.preview().action == "create":
                    break
                assert journal.next().action == "root"
                assert setup_transport.capture_once(journal).result == "PASS"
        order = journal.next()
        assert order.action == action
        initial = len(journal.records)
        calls = len(service.calls)
        expire[0] = True
        with pytest.raises(ValueError):
            setup_transport.capture_once(journal)
        records = journal.records[initial:]
        kind = "native_exchange" if action == "root" else "native_observation"
        assert [r["kind"] for r in records] == ["dispatch", kind]
        exchange = records[-1]["payload"]
        if action != "root":
            exchange = exchange["exchange"]
        assert returned and bytes.fromhex(exchange["response_hex"]) == returned[0]
        assert journal.pending == order
        with pytest.raises(ValueError):
            setup_transport.capture_once(journal)
        assert len(service.calls) == calls + 1
    finally:
        journal.close()


def test_installed_component_store_is_independently_selected(tmp_path: Path) -> None:
    root, grant, installation, bindings = installation_fixture(tmp_path)
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    assert context.component_store() == root / "components-pinned"


def test_synthetic_service_evidence_is_rejected_for_production(tmp_path: Path) -> None:
    _, _, installation, _ = installation_fixture(tmp_path)
    value = json.loads(installation)
    value.update(kind="production", test_service_evidence="complete_synthetic_service")
    with pytest.raises(ValueError, match="not production evidence"):
        Installation.model_validate_json(json.dumps(value))


def test_acknowledged_share_job_resumes_in_fresh_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, grant, installation, bindings = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(installation)
    installation = (
        pin.model_copy(
            update={
                "credential_refs": {s: s for s in pin.credential_refs},
                "scopes": {s: tuple(sorted(set(_SCOPES.values()))) for s in pin.credential_refs},
            }
        )
        .model_dump_json()
        .encode()
    )
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    service = FakeHTTP(None)
    service.async_sharing = True
    service.pending_polls = 1
    connect_service(monkeypatch, service)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        for _ in range(100):
            order = journal.next()
            result = setup_transport.capture_once(journal)
            if order.action == "share":
                assert result.result == "PENDING" and result.async_job_id
                break
            assert result.result == "PASS"
        else:
            pytest.fail("existing schedule did not reach share")
    finally:
        journal.close()
    assert sum(r.route == "sharing/share_folder" for r in service.calls) == 1
    # Transfer independent simulated provider state, never expected outcomes/orders.
    state = {
        "objects": {p: o.model_dump(mode="json") for p, o in service.objects.items()},
        "shares": service.shares,
        "jobs": service.jobs,
        "job_polls": service.job_polls,
        "dispatches": service.dispatches,
    }
    for name, raw in (
        ("grant.json", grant),
        ("installation.json", installation),
        ("bindings.json", bindings),
        ("service.json", json.dumps(state).encode()),
    ):
        (root / name).write_bytes(raw)
    code = r"""
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, sys.argv[3])
from test_m2_setup_native_procedure import connect_service
from peru_conflicts.execution import setup_transport, setup_offline
from peru_conflicts.execution.setup_deployment import _load_verified
from peru_conflicts.execution.setup_dropbox import FolderObservation
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import FakeHTTP, NOW
assert not setup_offline._ADMISSIONS and not setup_offline._CLOCKS and not setup_offline._WITNESSES
root = Path(sys.argv[1])
installation = (root / 'installation.json').read_bytes()
context = _load_verified((root / 'grant.json').read_bytes(), installation, sys.argv[2],
    lambda: (root / 'bindings.json').read_bytes(),
    lambda: (root / 'installation.json').read_bytes(), clock=lambda: NOW)
state = json.loads((root / 'service.json').read_bytes())
service = FakeHTTP(None)
service.objects = {p: FolderObservation.model_validate(o) for p, o in state['objects'].items()}
service.shares = state['shares']
service.jobs = state['jobs']
service.job_polls = state['job_polls']
service.dispatches = state['dispatches']
with pytest.MonkeyPatch.context() as patch:
    connect_service(patch, service)
    journal = EvidenceJournal(root / 'run', root / 'checkpoint', context, create=False)
    try:
        for expected in ('PENDING', 'PASS'):
            order = journal.next()
            assert order.action == 'share_status'
            assert json.loads(bytes.fromhex(order.request.body_hex))['async_job_id'] in service.jobs
            result = setup_transport.capture_once(journal)
            assert result.result == expected
        dependent = journal.preview()
        assert dependent.action == 'invite'
        arguments = json.loads(bytes.fromhex(dependent.request.body_hex))
        assert arguments['shared_folder_id'] == result.shared_folder_id
        assert sum(r.route == 'sharing/check_share_job_status' for r in service.calls) == 2
        assert not any(r.route == 'sharing/share_folder' for r in service.calls)
    finally:
        journal.close()
print('TEST_PENDING_REOPEN_NO_SHARE_REDISPATCH')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root), sha256(installation), str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "TEST_PENDING_REOPEN_NO_SHARE_REDISPATCH"


def test_installed_schedule_uses_independent_http_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, grant, installation, bindings = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(installation)
    sessions = tuple(pin.credential_refs)
    installation = (
        pin.model_copy(
            update={
                "credential_refs": {s: s for s in sessions},
                "scopes": {s: tuple(sorted(set(_SCOPES.values()))) for s in sessions},
            }
        )
        .model_dump_json()
        .encode()
    )
    configured = json.loads(installation)
    configured["test_service_evidence"] = "complete_synthetic_service"
    installation = json.dumps(configured, separators=(",", ":"), ensure_ascii=False).encode()
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    service = FakeHTTP(None)
    service.async_sharing = True
    service.pending_polls = 1
    service.page_size = 1
    connect_service(monkeypatch, service)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        for _ in range(1200):
            try:
                order = journal.next()
            except StopIteration:
                break
            result = (
                journal.run_component()
                if order.action == "control"
                else setup_transport.capture_once(journal)
            )
            assert result.result in ("PASS", "PENDING"), (order.action, result)
        else:
            pytest.fail("installed schedule did not terminate")
        checks = [
            r["order"] for r in journal.records if r["kind"] == "outcome" and r["order"]["check_id"]
        ]
        assert len({o["check_id"] for o in checks}) == 108
        assert Counter(o["action"] for o in checks) == {"list": 36, "read": 36, "write": 36}
        assert Counter(o["expected"] for o in checks) == {"ALLOW": 46, "DENY": 62}
        assert len(service.shares) == 4
        assert all(len(s["mounts"]) == 1 and not s["pending"] for s in service.shares.values())
        assert sum(r.route == "sharing/share_folder" for r in service.calls) == 4
        assert not service.contents
        assert not any(o.kind == "file" for o in service.objects.values())
        assert not any(r["payload"].get("reconciliation_required") for r in journal.records)
        controls = [
            r["order"]["control_id"]
            for r in journal.records
            if r["kind"] == "outcome" and r["order"]["action"] == "control"
        ]
        assert controls == ["APP-ACCEPTED-BYTES-A", "APP-ACCEPTED-BYTES-B"]
    finally:
        journal.close()
