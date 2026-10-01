"""Installed native ingress under independent low-level wire/provider faults."""

import io
import json
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from test_m2_setup_deployment import installation_fixture
from test_m2_setup_native_procedure import connect_service, load_test_context

from peru_conflicts.execution import setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.execution.setup_dropbox import Exchange
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP

CANARY = "SYNTHETIC-fixture-session-coordinator"


class Reply:
    """Low-level reply from independently simulated provider bytes."""

    def __init__(self, exchange: Exchange):
        self.status = exchange.status
        self.raw = bytes.fromhex(exchange.response_hex)
        self.stream = io.BytesIO(self.raw)
        self.headers = [("x-dropbox-request-id", exchange.provider_request_id or "")]
        if exchange.result_header is not None:
            self.headers.append(("dropbox-api-result", exchange.result_header))

    def getheaders(self):
        return self.headers

    def read1(self, size: int):
        return self.stream.read(size)


def advance_to(journal: EvidenceJournal, action: str):
    for _ in range(1200):
        order = journal.next()
        if order.action == action:
            return order
        result = (
            journal.run_component()
            if order.action == "control"
            else setup_transport.capture_once(journal)
        )
        assert result.result in ("PASS", "PENDING"), (order.action, result)
    pytest.fail("protected schedule did not reach requested test boundary")


@pytest.mark.parametrize(
    "fault,action",
    [
        ("wrong_account", "create"),
        ("unexpected_editor", "membership"),
        ("pending_invitation", "membership"),
        ("unresolved_group", "membership"),
        ("inherited_member", "membership"),
        ("repeat_cursor", "membership"),
        ("wrong_cursor", "membership"),
        ("direct_link", "links"),
        ("ancestor_link", "links"),
        ("visibility", "links"),
        ("lost_mount", "mount_verify"),
        ("failed_job", "share_status"),
        ("unknown_job_variant", "share_status"),
        ("conflicting_job", "share_status"),
        ("wrong_share_id", "share_status"),
        ("pending_exhaustion", "share_status"),
    ],
)
def test_installed_provider_state_cannot_release_dependent_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    action: str,
) -> None:
    root, context = installed(tmp_path, complete=fault != "visibility")
    service = FakeHTTP(None)
    service.async_sharing = True
    service.pending_polls = 0
    service.page_size = 1
    armed = [False]
    cursor: list[str] = []
    originals: list[bytes] = []

    def response(exchange: Exchange):
        raw = bytes.fromhex(exchange.response_hex)
        route = exchange.request.route
        if armed[0] and exchange.status == 200:
            obj: dict[str, Any] = json.loads(raw) if route != "files/download" else {}
            if route == "sharing/check_share_job_status":
                if fault == "unknown_job_variant":
                    obj[".tag"] = "future_unknown_variant"
                elif fault == "conflicting_job":
                    obj.update({".tag": "failed", "failed": {".tag": "other"}})
                elif fault == "wrong_share_id":
                    obj["complete"]["shared_folder_id"] = "unrelated-share"
            if route in ("sharing/list_folder_members", "sharing/list_folder_members/continue"):
                if fault == "unresolved_group":
                    obj["groups"] = [{"group": {"group_id": "synthetic-unresolved"}}]
                elif fault == "inherited_member":
                    obj["users"][0]["is_inherited"] = True
                elif fault == "wrong_cursor" and "cursor" in obj:
                    obj["cursor"] = "unknown-provider-cursor"
                elif fault == "repeat_cursor":
                    if not cursor:
                        cursor.append(obj["cursor"])
                    else:
                        obj["cursor"] = cursor[0]
            raw = json.dumps(obj).encode()
            exchange = exchange.model_copy(update={"response_hex": raw.hex()})
        originals.append(raw)
        return Reply(exchange)

    connect_service(monkeypatch, service, response_factory=response)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = advance_to(journal, action)
        if fault == "wrong_account":
            account, namespace = service.accounts[order.actor.session_ref]
            service.accounts[order.actor.session_ref] = (account + "-wrong", namespace)
        if service.shares:
            share = next(iter(service.shares.values()))
            if fault == "unexpected_editor":
                share["members"]["dbid:unexpected-synthetic-editor"] = "editor"
            if fault == "pending_invitation":
                share["pending"]["dbid:pending-synthetic"] = "viewer"
            if fault == "lost_mount":
                share["mounts"]["dbid:offline-annotator-a"] = "/unrelated-mount"
            if fault == "direct_link":
                service.links[share["path"]] = [{"url": "https://synthetic.invalid/direct"}]
            if fault == "ancestor_link":
                service.links[str(PurePosixPath(share["path"]).parent)] = [
                    {"url": "https://synthetic.invalid/ancestor"}
                ]
        if fault == "failed_job":
            service.failed_jobs.update(service.jobs)
        if fault == "pending_exhaustion":
            service.job_polls.update({j: 100 for j in service.jobs})
        start = len(service.calls)
        record_start = len(journal.records)
        armed[0] = True
        if fault in ("wrong_account", "wrong_share_id"):
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
            if fault == "wrong_account":
                assert len(service.calls) == start + 1
        elif fault == "pending_exhaustion":
            for i in range(3):
                if i:
                    assert journal.next().action == "share_status"
                assert setup_transport.capture_once(journal).result == "PENDING"
            with pytest.raises(ValueError):
                journal.next()
        else:
            result = setup_transport.capture_once(journal)
            assert result.result not in ("PASS", "PENDING"), (fault, result)
            if fault in ("direct_link", "ancestor_link", "unexpected_editor"):
                assert result.result == "FAIL"
            if fault == "inherited_member":
                assert result.result == "INCONCLUSIVE"
            assert journal.stopped
        captured = [
            r
            for r in journal.records[record_start:]
            if r["kind"] in ("native_exchange", "native_observation")
        ]
        assert captured
        assert all(
            bytes.fromhex((r["payload"].get("exchange") or r["payload"])["response_hex"])
            in originals
            for r in captured
        )
        assert not any(
            r.route
            in (
                "files/create_folder_v2",
                "files/upload",
                "files/delete_v2",
                "sharing/add_folder_member",
                "sharing/mount_folder",
                "sharing/share_folder",
            )
            for r in service.calls[start:]
        )
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        with pytest.raises(ValueError):
            resumed.next()
    finally:
        resumed.close()


def installed(tmp_path: Path, *, complete: bool = False):
    root, grant, raw, bindings = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(raw)
    raw = (
        pin.model_copy(
            update={
                "credential_refs": {s: s for s in pin.credential_refs},
                "scopes": {
                    s: (
                        "account_info.read",
                        "files.metadata.read",
                        "files.content.read",
                        "files.content.write",
                        "sharing.read",
                        "sharing.write",
                    )
                    for s in pin.credential_refs
                },
                "test_service_evidence": "complete_synthetic_service" if complete else None,
            }
        )
        .model_dump_json()
        .encode()
    )
    context = load_test_context(
        grant, raw, sha256(raw), lambda: bindings, lambda: raw, clock=lambda: NOW
    )
    return root, context


@pytest.mark.parametrize(
    "fault",
    [
        "short_body",
        "partial_disconnect",
        "slow_chunks",
        "close_error",
        "duplicate_length",
        "header_budget",
        "header_error",
        "length_and_chunked",
        "long_body",
        "body_limit",
        "secret_body",
        "secret_header",
        "small_chunks",
    ],
)
def test_installed_wire_faults_retain_only_admissible_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    root, context = installed(tmp_path)
    service = FakeHTTP(None)
    now = [0.0]
    originals: list[bytes] = []
    returned: list[bytes] = []
    monkeypatch.setattr(setup_transport.time, "monotonic", lambda: now[0])

    class Response:
        status = 200

        def __init__(self, exchange: Exchange):
            raw = bytes.fromhex(exchange.response_hex)
            originals.append(raw)
            self.headers = [
                ("x-dropbox-request-id", "synthetic-request"),
                ("Content-Length", str(len(raw))),
            ]
            if fault == "short_body":
                self.headers[-1] = ("Content-Length", str(len(raw) + 10))
            if fault == "long_body":
                self.headers[-1] = ("Content-Length", str(len(raw) - 1))
            if fault == "duplicate_length":
                self.headers.append(("Content-Length", "1"))
            if fault == "header_budget":
                self.headers.extend((f"X-Filler-{i}", "x" * 1000) for i in range(40))
            if fault == "length_and_chunked":
                self.headers.append(("Transfer-Encoding", "chunked"))
            if fault == "body_limit":
                raw = b"x" * 1048577
                self.headers[-1] = ("Content-Length", str(len(raw)))
            if fault == "secret_body":
                raw = CANARY.encode()
                self.headers[-1] = ("Content-Length", str(len(raw)))
            if fault == "secret_header":
                self.headers[0] = ("x-dropbox-request-id", CANARY)
            self.stream = io.BytesIO(raw)
            self.reads = 0

        def getheaders(self):
            if fault == "header_error":
                raise OSError(CANARY)
            return self.headers

        def getheader(self, name: str, default: str | None = None):
            return next((v for k, v in self.headers if k.lower() == name.lower()), default)

        def read(self, size: int):
            if fault == "partial_disconnect" and self.reads:
                raise OSError(CANARY)
            self.reads += 1
            if fault == "slow_chunks":
                now[0] += 8
            chunk = self.stream.read(
                min(size, 7)
                if fault in ("small_chunks", "partial_disconnect", "slow_chunks")
                else size
            )
            returned.append(chunk)
            return chunk

        read1 = read

    def close() -> None:
        if fault == "close_error":
            raise OSError(CANARY)

    connect_service(monkeypatch, service, response_factory=Response, on_close=close)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = journal.next()
        if fault == "small_chunks":
            assert setup_transport.capture_once(journal).result == "PASS"
            original = next(r["payload"] for r in journal.records if r["kind"] == "native_exchange")
            assert bytes.fromhex(original["response_hex"]) == originals[0]
        else:
            with pytest.raises(ValueError) as raised:
                setup_transport.capture_once(journal)
            assert raised.value.__context__ is None
            assert CANARY not in str(raised.value)
            assert journal.pending == order
            interruptions = [r for r in journal.records if r["kind"] == "native_interruption"]
            if fault in (
                "short_body",
                "long_body",
                "partial_disconnect",
                "slow_chunks",
                "close_error",
            ):
                assert len(interruptions) == 1
                payload = interruptions[0]["payload"]
                assert payload["complete"] is (fault == "close_error")
                assert bytes.fromhex(payload["exchange"]["response_hex"]) == b"".join(returned)
            else:
                assert not interruptions
                assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
            assert not any(r["kind"] == "capture" for r in journal.records)
        assert len(service.calls) == 1
        assert CANARY not in json.dumps(journal.records)
    finally:
        journal.close()
    reopened = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        if fault != "small_chunks":
            with pytest.raises(ValueError):
                reopened.next()
            with pytest.raises(ValueError):
                setup_transport.capture_once(reopened)
        assert len(service.calls) == 1
    finally:
        reopened.close()
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err
