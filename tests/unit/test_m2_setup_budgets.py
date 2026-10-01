"""Application-level accounting at the installed, independently fake HTTP boundary."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_m2_setup_deployment import installation_fixture
from test_m2_setup_native_procedure import connect_service, load_test_context
from test_m2_setup_transport_adversarial import Reply, advance_to, installed

from peru_conflicts.execution import setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.execution.setup_dropbox import Exchange
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP


def meter_requests(monkeypatch: pytest.MonkeyPatch, charge: Callable[[int], None]) -> None:
    connection = vars(setup_transport)["_connection"]

    def measured_connection(host: str, **kwargs: Any):
        conn = connection(host, **kwargs)
        request = conn.request

        def send(method: str, path: str, body: bytes, headers: dict[str, str]):
            fields = (
                f"{method} {path} HTTP/1.1\r\nHost: {host}\r\n"
                f"Content-Length: {len(body)}\r\nAccept-Encoding: identity\r\n\r\n"
            ).encode()
            charge(
                len(fields)
                + len(body)
                + sum(
                    len(k.encode("ascii")) + len(v.encode("latin-1")) + 4
                    for k, v in headers.items()
                )
            )
            request(method, path, body, headers)

        conn.request = send
        return conn

    monkeypatch.setattr(setup_transport, "_connection", measured_connection)


@pytest.mark.parametrize("bounded", [False, True])
def test_installed_cumulative_supplemental_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bounded: bool
) -> None:
    root, context = installed(tmp_path, complete=True)
    service = FakeHTTP(None)
    armed = False
    consumed = 0
    returned = 0
    reads: list[int] = []
    originals: list[bytes] = []
    response_chunks: list[list[bytes]] = []

    class MeasuredReply(Reply):
        def __init__(self, exchange: Exchange):
            nonlocal consumed
            if armed:
                obj = json.loads(bytes.fromhex(exchange.response_hex))
                obj["synthetic_padding"] = "x" * 1000
                exchange = exchange.model_copy(
                    update={"response_hex": json.dumps(obj).encode().hex()}
                )
            super().__init__(exchange)
            self.eof = False
            if armed:
                response_chunks.append([])
                consumed += sum(len(k.encode()) + len(v.encode()) + 4 for k, v in self.headers)

        def read1(self, size: int):
            nonlocal consumed, returned
            if armed:
                assert size > 0
                reads.append(size)
            chunk = super().read1(size)
            self.eof = not chunk
            if armed:
                consumed += len(chunk)
                returned += len(chunk)
                originals.append(chunk)
                response_chunks[-1].append(chunk)
            return chunk

        def isclosed(self):
            # No Content-Length is supplied: only a witnessed empty read proves EOF.
            return self.eof

    connect_service(monkeypatch, service, response_factory=MeasuredReply)

    def charge_request(size: int):
        nonlocal consumed
        if armed:
            consumed += size

    meter_requests(monkeypatch, charge_request)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        advance_to(journal, "create")
        first_call = len(service.calls)
        armed = True
        if bounded:
            monkeypatch.setattr(setup_transport, "_ACTION_BYTES", 2000)
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
            assert consumed <= 2000, (consumed, returned, reads)
            assert not any(r.route == "files/create_folder_v2" for r in service.calls[first_call:])
            interrupted = [r for r in journal.records if r["kind"] == "native_interruption"]
            assert len(interrupted) == 1
            assert not interrupted[0]["payload"]["complete"]
            assert bytes.fromhex(interrupted[0]["payload"]["exchange"]["response_hex"]) == b"".join(
                response_chunks[-1]
            )
            assert len(service.calls) - first_call >= 2
        else:
            assert setup_transport.capture_once(journal).result == "PASS"
            assert consumed > 4096
        assert reads and returned > 0
    finally:
        journal.close()
    if bounded:
        calls = len(service.calls)
        recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
        try:
            with pytest.raises(ValueError):
                recovered.next()
            with pytest.raises(ValueError):
                setup_transport.capture_once(recovered)
            assert len(service.calls) == calls
        finally:
            recovered.close()


@pytest.mark.parametrize(
    "counter", ["body", "unframed", "headers", "header_count", "reads", "requests"]
)
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_installed_exact_application_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, counter: str, delta: int
) -> None:
    root, context = installed(tmp_path)
    service = FakeHTTP(None)
    sizes: list[int] = []
    chunks: list[bytes] = []
    bodies: list[bytes] = []

    class BoundaryReply(Reply):
        def __init__(self, exchange: Exchange):
            super().__init__(exchange)
            self.eof = False
            self.framed = counter != "unframed"
            if self.framed:
                self.headers.append(("Content-Length", str(len(self.raw))))
            bodies.append(self.raw)
            if counter in ("body", "unframed"):
                monkeypatch.setattr(setup_transport, "_MAX_RESPONSE", len(self.raw) + delta)
            if counter == "headers":
                size = sum(len(k.encode()) + len(v.encode()) + 4 for k, v in self.headers)
                monkeypatch.setattr(setup_transport, "_MAX_HEADERS", size + delta)
            if counter == "header_count":
                monkeypatch.setattr(setup_transport, "_MAX_HEADER_COUNT", len(self.headers) + delta)
            if counter == "reads":
                monkeypatch.setattr(setup_transport, "_MAX_READS", len(self.raw) + delta)

        def read1(self, size: int):
            assert size > 0
            sizes.append(size)
            chunk = super().read1(min(size, 1) if counter == "reads" else size)
            chunks.append(chunk)
            self.eof = not chunk
            return chunk

        def isclosed(self):
            return self.eof or (self.framed and self.stream.tell() == len(self.raw))

    connect_service(monkeypatch, service, response_factory=BoundaryReply)
    if counter == "requests":
        monkeypatch.setattr(setup_transport, "_ACTION_REQUESTS", 1 + delta)
    stopped = delta < 0 or (counter == "unframed" and delta == 0)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        journal.next()
        if stopped:
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
            assert not any(r["kind"] == "capture" for r in journal.records)
            if counter in ("unframed", "reads"):
                retained = [r for r in journal.records if r["kind"] == "native_interruption"]
                assert len(retained) == 1
                assert not retained[0]["payload"]["complete"]
                assert bytes.fromhex(
                    retained[0]["payload"]["exchange"]["response_hex"]
                ) == b"".join(chunks)
            else:
                assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
        else:
            assert setup_transport.capture_once(journal).result == "PASS"
            retained = [r for r in journal.records if r["kind"] == "native_exchange"]
            assert bytes.fromhex(retained[0]["payload"]["response_hex"]) == bodies[0]
        assert len(service.calls) == (0 if counter == "requests" and delta < 0 else 1)
        if counter in ("body", "unframed"):
            assert sum(map(len, chunks)) <= len(bodies[0]) + delta
        if counter == "reads":
            assert len(sizes) <= len(bodies[0]) + delta
    finally:
        journal.close()
    if stopped:
        calls = len(service.calls)
        recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
        try:
            with pytest.raises(ValueError):
                recovered.next()
            with pytest.raises(ValueError):
                setup_transport.capture_once(recovered)
            assert len(service.calls) == calls
        finally:
            recovered.close()


@pytest.mark.parametrize("explicit", [False, True])
def test_installed_native_requirements_reject_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool
):
    root, grant, pin, bindings = installation_fixture(tmp_path)
    obj = json.loads(pin)
    # Absence of an explicitly isolated simulation profile requires native guarantees.
    obj.pop("transport_profile", None)
    if explicit:
        obj["transport_profile"] = "native_required_guarantees"
    obj["credential_refs"] = {s: s for s in obj["credential_refs"]}
    pin = Installation.model_validate_json(json.dumps(obj)).model_dump_json().encode()
    context = load_test_context(
        grant, pin, sha256(pin), lambda: bindings, lambda: pin, clock=lambda: NOW
    )
    service = FakeHTTP(None)
    connect_service(monkeypatch, service)
    resolved: list[str] = []
    factories: list[str] = []
    connection = vars(setup_transport)["_connection"]

    def factory(host: str, **kwargs: Any):
        factories.append(host)
        return connection(host, **kwargs)

    monkeypatch.setattr(setup_transport, "_connection", factory)

    def credential(reference: str):
        resolved.append(reference)
        return "SYNTHETIC-" + reference

    monkeypatch.setattr(setup_transport, "_read_credential", credential)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        journal.next()
        with pytest.raises(ValueError, match="required native hard-deadline") as error:
            setup_transport.capture_once(journal)
        assert error.value.__context__ is None
        assert not resolved
        assert not factories
        assert not service.calls
        assert [r["kind"] for r in journal.records] == ["intent"]
    finally:
        journal.close()
    recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        with pytest.raises(ValueError, match="required native hard-deadline"):
            setup_transport.capture_once(recovered)
        assert not resolved and not factories and not service.calls
        assert [r["kind"] for r in recovered.records] == ["intent"]
    finally:
        recovered.close()


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_installed_page_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int):
    root, context = installed(tmp_path, complete=True)
    service = FakeHTTP(None)
    service.page_size = 1
    connect_service(monkeypatch, service)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = advance_to(journal, "membership")
        start = len(service.calls)
        monkeypatch.setattr(setup_transport, "_MAX_PAGES", limit, raising=False)
        if limit < 2:
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
            assert service.calls[-1].route == "sharing/list_folder_members"
        else:
            assert setup_transport.capture_once(journal).result == "PASS"
        pages = [
            r for r in service.calls[start:] if r.route.startswith("sharing/list_folder_members")
        ]
        assert len(pages) == min(limit, 2)
        if limit < 2:
            originals = [
                r
                for r in journal.records
                if r["kind"] == "native_exchange" and r["order"] == order.model_dump(mode="json")
            ]
            assert len(originals) == 1
    finally:
        journal.close()
    if limit < 2:
        calls = len(service.calls)
        recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
        try:
            with pytest.raises(ValueError):
                recovered.next()
            with pytest.raises(ValueError):
                setup_transport.capture_once(recovered)
            assert len(service.calls) == calls
        finally:
            recovered.close()


def test_simulated_profile_cannot_claim_production_capability(tmp_path: Path):
    _, _, raw, _ = installation_fixture(tmp_path)
    obj = json.loads(raw)
    obj["kind"] = "production"
    with pytest.raises(ValueError, match="cannot establish native capabilities"):
        Installation.model_validate_json(json.dumps(obj))
    obj["kind"] = "synthetic_test"
    obj["transport_profile"] = "arbitrary-owner-approved-deadline"
    with pytest.raises(ValueError):
        Installation.model_validate_json(json.dumps(obj))


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_installed_exact_action_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: int
):
    def run(control: bool, expected: int = 0) -> int:
        child = tmp_path / ("control" if control else "bounded")
        child.mkdir()
        root, context = installed(child)
        service = FakeHTTP(None)
        used = 0
        chunks: list[bytes] = []

        def charge(size: int):
            nonlocal used
            used += size

        class Framed(Reply):
            def __init__(self, exchange: Exchange):
                super().__init__(exchange)
                self.headers.append(("Content-Length", str(len(self.raw))))
                charge(sum(len(k.encode()) + len(v.encode()) + 4 for k, v in self.headers))

            def read1(self, size: int):
                assert size > 0
                data = super().read1(size)
                chunks.append(data)
                charge(len(data))
                return data

            def isclosed(self):
                return self.stream.tell() == len(self.raw)

        connect_service(monkeypatch, service, response_factory=Framed)
        meter_requests(monkeypatch, charge)
        if not control:
            monkeypatch.setattr(setup_transport, "_ACTION_BYTES", expected + delta)
        journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
        try:
            journal.next()
            if not control and delta < 0:
                with pytest.raises(ValueError):
                    setup_transport.capture_once(journal)
                retained = [r for r in journal.records if r["kind"] == "native_interruption"]
                assert len(retained) == 1
                assert bytes.fromhex(
                    retained[0]["payload"]["exchange"]["response_hex"]
                ) == b"".join(chunks)
                assert not retained[0]["payload"]["complete"]
            else:
                assert setup_transport.capture_once(journal).result == "PASS"
            assert len(service.calls) == 1
            if control:
                expected = used
            else:
                assert used <= expected + delta
        finally:
            journal.close()
        if not control and delta < 0:
            recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
            try:
                with pytest.raises(ValueError):
                    recovered.next()
                with pytest.raises(ValueError):
                    setup_transport.capture_once(recovered)
                assert len(service.calls) == 1
            finally:
                recovered.close()
        return used

    run(False, run(True))


def test_request_cap_counts_supplemental_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, context = installed(tmp_path)
    service = FakeHTTP(None)
    connect_service(monkeypatch, service)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        advance_to(journal, "create")
        start = len(service.calls)
        monkeypatch.setattr(setup_transport, "_ACTION_REQUESTS", 2)
        with pytest.raises(ValueError):
            setup_transport.capture_once(journal)
        assert len(service.calls) == start + 2
        assert all(r.route != "files/create_folder_v2" for r in service.calls[start:])
    finally:
        journal.close()
    recovered = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        with pytest.raises(ValueError):
            recovered.next()
        with pytest.raises(ValueError):
            setup_transport.capture_once(recovered)
        assert len(service.calls) == start + 2
    finally:
        recovered.close()
