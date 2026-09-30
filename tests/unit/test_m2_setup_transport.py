"""Native request assembly/capture against an in-memory HTTP connection, no sockets."""

import importlib
import io
import json
import ssl
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_m2_setup_deployment import installation_fixture


def test_native_capture_boundary_is_implemented() -> None:
    # Executable boundary is absent on the accepted baseline; module is not an SDK.
    module = importlib.import_module("peru_conflicts.execution.setup_transport")
    with pytest.raises(ValueError, match="admission"):
        module.capture_once(None)


def test_empty_registry_never_loads_native_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    from peru_conflicts.execution.setup_authority import admit

    monkeypatch.setitem(sys.modules, "peru_conflicts.execution.setup_transport", None)
    with pytest.raises(ValueError, match="no registered real grant"):
        admit(b"{}", lambda: pytest.fail("private lookup"))


def test_authority_rechecked_after_connection_preparation(monkeypatch: pytest.MonkeyPatch):
    from peru_conflicts.execution import setup_transport
    from peru_conflicts.execution.setup_dropbox import encode_request

    valid = [True]
    sent: list[str] = []

    class Connection:
        def __init__(self, *args: object, **kwargs: object):
            valid[0] = False

        def request(self, *args: object, **kwargs: object):
            sent.append("unauthorized")

        def getresponse(self):
            raise OSError("synthetic")

        def close(self):
            pass

    def check() -> None:
        if not valid[0]:
            raise ValueError("authority expired")

    def credential(_: str) -> str:
        return "SYNTHETIC-NOT-A-CREDENTIAL"

    monkeypatch.setattr(setup_transport, "_connection", Connection)
    monkeypatch.setattr(setup_transport, "_read_credential", credential)
    request = encode_request("users/get_current_account", {}, "synthetic", "synthetic")
    with pytest.raises(ValueError):
        setup_transport._exchange(request, "synthetic", check, {})  # pyright: ignore[reportPrivateUsage]
    assert not sent


def test_expiry_during_credential_resolution_prevents_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from peru_conflicts.execution import setup_transport
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import (
        _load_verified,  # pyright: ignore[reportPrivateUsage]
    )
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import NOW

    root, grant, installation, bindings = installation_fixture(tmp_path)
    clock = [NOW]
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: clock[0],
    )
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    calls: list[str] = []

    def credential(_: str) -> str:
        clock[0] += timedelta(hours=2)
        return "SYNTHETIC-CREDENTIAL-NOT-VALID"

    def connection(*args: object, **kwargs: object) -> object:
        calls.append("connection")
        raise OSError("synthetic connection failure")

    monkeypatch.setattr(setup_transport, "_read_credential", credential)
    monkeypatch.setattr(setup_transport, "_connection", connection)
    try:
        order = journal.next()
        with pytest.raises(ValueError):
            setup_transport.capture_once(journal)
        assert not calls
        assert journal.pending == order
        assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
    finally:
        journal.close()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong_account",
        "redirect",
        "secret_echo",
        "timeout",
        "credential_error",
        "malformed",
        "duplicate_keys",
        "oversized",
    ],
)
def test_installed_native_capture_uses_bounded_http_and_never_persists_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    from peru_conflicts.execution import setup_transport
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_deployment import (
        _load_verified,  # pyright: ignore[reportPrivateUsage]
    )
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import NOW

    root, grant, installation, bindings = installation_fixture(tmp_path)
    context = _load_verified(
        grant,
        installation,
        sha256(installation),
        lambda: bindings,
        lambda: installation,
        clock=lambda: NOW,
    )
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    calls: list[tuple[str, str, bytes, dict[str, str]]] = []
    secret = "SYNTHETIC-CREDENTIAL-NOT-VALID"

    class Connection:
        def __init__(self, host: str, *, timeout: float, context: ssl.SSLContext):
            assert host == "api.dropboxapi.com"
            assert 0 < timeout <= 15
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED

        def request(self, method: str, path: str, body: bytes, headers: dict[str, str]):
            calls.append((method, path, body, headers.copy()))
            if fault == "timeout":
                raise TimeoutError(secret)

        def getresponse(self):
            account = "dbid:wrong" if fault == "wrong_account" else "dbid:offline-coordinator"
            raw = json.dumps(
                {
                    "account_id": account,
                    "root_info": {
                        ".tag": "user",
                        "root_namespace_id": "offline-coordinator-home",
                        "home_namespace_id": "offline-coordinator-home",
                    },
                }
            ).encode()
            if fault == "secret_echo":
                raw = secret.encode()
            elif fault == "malformed":
                raw = b'{"account_id":'
            elif fault == "duplicate_keys":
                raw = b'{"account_id":"first","account_id":"second"}'
            elif fault == "oversized":
                raw = b"x" * 1048577

            class Response:
                status = 302 if fault == "redirect" else 200
                stream = io.BytesIO(raw)

                def getheader(self, name: str, default: str | None = None):
                    return (
                        "synthetic-request-id"
                        if name.lower() == "x-dropbox-request-id"
                        else default
                    )

                def read(self, size: int):
                    return self.stream.read(size)

                read1 = read

                def getheaders(self):
                    return [("x-dropbox-request-id", "synthetic-request-id")]

            return Response()

        def close(self):
            pass

    monkeypatch.setattr(setup_transport, "_connection", Connection)

    def credential(_: str) -> str:
        if fault == "credential_error":
            raise ValueError(secret)
        return secret

    monkeypatch.setattr(setup_transport, "_read_credential", credential)
    try:
        order = journal.next()
        if fault in ("timeout", "secret_echo", "credential_error", "oversized"):
            with pytest.raises(ValueError) as error:
                setup_transport.capture_once(journal)
            assert secret not in str(error.value)
            assert journal.pending == order
        else:
            result = setup_transport.capture_once(journal)
            assert result.result == ("PASS" if fault is None else "INCONCLUSIVE")
            assert journal.stopped is (fault is not None)
            retained = next(r["payload"] for r in journal.records if r["kind"] == "capture")
            assert retained["source"] == "native_collector"
            assert "witness_sha256" not in retained
            assert retained["original_sha256"] == sha256(bytes.fromhex(retained["original_hex"]))
        count = 0 if fault == "credential_error" else 1
        assert len(calls) == count
        if calls:
            assert calls[0][:3] == ("POST", "/2/users/get_current_account", b"{}")
        assert secret not in json.dumps(journal.records)
        assert any(r["kind"] == "dispatch" for r in journal.records)
        if fault:
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
            assert len(calls) == count
        if fault in ("malformed", "duplicate_keys"):
            originals = [r["payload"] for r in journal.records if r["kind"] == "native_exchange"]
            assert len(originals) == 1
            expected = (
                b'{"account_id":'
                if fault == "malformed"
                else b'{"account_id":"first","account_id":"second"}'
            )
            assert bytes.fromhex(originals[0]["response_hex"]) == expected
    finally:
        journal.close()
    recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        assert recovered.stopped is (
            fault in ("wrong_account", "redirect", "malformed", "duplicate_keys")
        )
        if fault:
            with pytest.raises(ValueError):
                recovered.next()
    finally:
        recovered.close()
