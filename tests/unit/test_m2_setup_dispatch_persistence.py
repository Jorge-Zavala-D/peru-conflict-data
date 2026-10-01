"""Installed first-mutation timing and low-level publication faults; no sockets."""

import json
import subprocess
import sys
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from test_m2_setup_deployment import installation_fixture
from test_m2_setup_native_procedure import connect_service, load_test_context
from test_m2_setup_transport_adversarial import Reply

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.execution import setup_evidence, setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_authority import SetupGrantV2
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.execution.setup_dropbox import Exchange
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP

CANARY = "SYNTHETIC-EXCEPTION-SECRET-NEVER-RETAIN"
MUTATION = "files/create_folder_v2"


class InstalledRun:
    """Test-owned trust and HTTP instrumentation, not a journal/transport substitute."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.root, self.grant_raw, raw, self.bindings = installation_fixture(tmp_path)
        pin = Installation.model_validate_json(raw)
        self.pin = (
            pin.model_copy(
                update={
                    "credential_refs": {s: s for s in pin.credential_refs},
                    "scopes": {
                        s: ("account_info.read", "files.metadata.read", "files.content.write")
                        for s in pin.credential_refs
                    },
                }
            )
            .model_dump_json()
            .encode()
        )
        self.current_pin = self.pin
        self.clock = NOW
        self.revalidation_error = False
        self.context = load_test_context(
            self.grant_raw,
            self.pin,
            sha256(self.pin),
            lambda: self.bindings,
            self.revalidate,
            clock=lambda: self.clock,
        )
        self.service = FakeHTTP(None)
        self.counts = {"resolver": 0, "factory": 0, "send": 0, "target_send": 0}
        self.events: list[str] = []
        self.active = False
        self.hook: Callable[[str], None] = lambda _: None
        self.token_override: str | None = None
        self.target_chunks: list[bytes] = []
        self.target_raw: bytes | None = None
        self.partial_error = False
        rig = self

        class Response(Reply):
            def __init__(self, exchange: Exchange):
                super().__init__(exchange)
                self.target = exchange.request.route == MUTATION
                self.reads = 0
                if self.target:
                    rig.target_raw = self.raw

            def read1(self, size: int):
                if self.target and rig.partial_error and self.reads:
                    raise OSError(CANARY)
                chunk = super().read1(min(size, 7) if self.target and rig.partial_error else size)
                self.reads += 1
                if self.target:
                    rig.target_chunks.append(chunk)
                    if chunk:
                        rig.fire("target_response")
                return chunk

        connect_service(monkeypatch, self.service, response_factory=Response)
        connection = vars(setup_transport)["_connection"]

        def factory(*args: Any, **kwargs: Any):
            if self.active:
                self.counts["factory"] += 1
                self.fire(
                    "target_factory" if self.counts["factory"] == 3 else "preliminary_factory"
                )
            result = connection(*args, **kwargs)
            request = result.request

            def send(method: str, path: str, body: bytes, headers: dict[str, str]):
                if self.active:
                    self.counts["send"] += 1
                    self.counts["target_send"] += int(path == "/2/" + MUTATION)
                    self.events.append(
                        "target_send" if path == "/2/" + MUTATION else "preliminary_send"
                    )
                    if path == "/2/" + MUTATION:
                        records = rig.journal.records[rig.record_start :]
                        assert [r["kind"] for r in records[:2]] == ["intent", "dispatch"]
                        for offset in (1, 2):
                            name = f"{rig.record_start + offset:06d}.json"
                            raw = (rig.root / "run" / name).read_bytes()
                            assert (rig.root / "checkpoint" / name).read_bytes() == sha256(
                                raw
                            ).encode()
                request(method, path, body, headers)

            result.request = send
            return result

        def credential(reference: str):
            if self.active:
                self.counts["resolver"] += 1
                self.fire("resolver")
            return "SYNTHETIC-" + (self.token_override or reference)

        monkeypatch.setattr(setup_transport, "_connection", factory)
        monkeypatch.setattr(setup_transport, "_read_credential", credential)
        self.journal = EvidenceJournal(
            self.root / "run", self.root / "checkpoint", self.context, create=True
        )
        while self.journal.preview().action != "create":
            assert self.journal.next().action == "root"
            assert setup_transport.capture_once(self.journal).result == "PASS"
        self.order = self.journal.preview()
        assert self.order.action == "create"
        assert self.order.logical_path not in self.service.objects
        self.start = len(self.service.calls)
        self.record_start = len(self.journal.records)
        self.active = True

    def revalidate(self) -> bytes:
        if self.revalidation_error:
            raise OSError(CANARY)
        return self.current_pin

    def fire(self, stage: str) -> None:
        self.events.append(stage)
        self.hook(stage)

    def revoke(self) -> None:
        self.current_pin = (
            Installation.model_validate_json(self.pin)
            .model_copy(update={"revoked": True})
            .model_dump_json()
            .encode()
        )

    def expire(self) -> None:
        self.clock = SetupGrantV2.model_validate_json(self.grant_raw).not_after

    def evidence(self) -> dict[str, Any]:
        records = self.journal.records[self.record_start :]
        return {
            "action": self.order.action,
            "events": self.events,
            **self.counts,
            "provider_routes": [r.route for r in self.service.calls[self.start :]],
            "provider_effect": self.order.logical_path in self.service.objects,
            "records": [r["kind"] for r in records],
        }


def clean_error(error: BaseException) -> None:
    if CANARY in "".join(traceback.format_exception(error)):
        pytest.fail("public diagnostic leaked synthetic canary", pytrace=False)
    assert error.__context__ is None


@pytest.mark.parametrize(
    "fault,stage,sends,target",
    [
        ("none", "none", 4, 1),
        ("revoke", "before_release", 0, 0),
        ("expire", "before_release", 0, 0),
        ("reader_error", "before_release", 0, 0),
        ("revoke", "released", 0, 0),
        ("expire", "released", 0, 0),
        ("rebind", "resolver", 0, 0),
        ("revoke", "resolver", 0, 0),
        ("expire", "resolver", 0, 0),
        ("wrong_account", "resolver", 1, 0),
        ("wrong_namespace", "resolver", 1, 0),
        ("wrong_token", "resolver", 1, 0),
        ("resolver_error", "resolver", 0, 0),
        ("revoke", "target_factory", 2, 0),
        ("expire", "target_factory", 2, 0),
        ("stale", "target_factory", 2, 0),
        ("rebind", "target_factory", 2, 0),
        ("connection_error", "target_factory", 2, 0),
        ("revoke", "target_response", 3, 1),
        ("expire", "target_response", 3, 1),
        ("partial", "target_response", 3, 1),
    ],
)
def test_installed_dispatch_timing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Callable[[str, object], None],
    fault: str,
    stage: str,
    sends: int,
    target: int,
):
    rig = InstalledRun(tmp_path, monkeypatch)
    fired: list[str] = []

    def inject(at: str):
        if at != stage or fired:
            return
        fired.append(at)
        if fault == "revoke":
            rig.revoke()
        elif fault == "expire":
            rig.expire()
        elif fault == "stale":
            rig.clock = rig.order.dispatch_not_after
        elif fault == "reader_error":
            rig.revalidation_error = True
        elif fault == "rebind":
            obj = json.loads(rig.pin)
            obj["credential_refs"][rig.order.actor.session_ref] = "SYNTHETIC-REBOUND"
            rig.current_pin = (
                Installation.model_validate_json(json.dumps(obj)).model_dump_json().encode()
            )
        elif fault in ("wrong_account", "wrong_namespace"):
            account, namespace = rig.service.accounts[rig.order.actor.session_ref]
            rig.service.accounts[rig.order.actor.session_ref] = (
                "dbid:unapproved-synthetic" if fault == "wrong_account" else account,
                "unapproved-synthetic-namespace" if fault == "wrong_namespace" else namespace,
            )
        elif fault == "wrong_token":
            alternate = "fixture-session-annotator-a"
            rig.token_override = alternate
            account, _ = rig.service.accounts[alternate]
            rig.service.accounts[alternate] = (account, rig.order.namespace)
        elif fault in ("resolver_error", "connection_error"):
            raise OSError(CANARY)
        elif fault == "partial":
            rig.partial_error = True

    rig.hook = inject
    rig.partial_error = fault == "partial"
    raised: BaseException | None = None
    try:
        if stage == "before_release":
            rig.fire(stage)
            with pytest.raises(Exception) as error:
                rig.journal.next()
            raised = error.value
        else:
            assert rig.journal.next() == rig.order
            if stage == "released":
                rig.fire(stage)
            if fault == "none":
                assert setup_transport.capture_once(rig.journal).result == "PASS"
                assert not fired
            else:
                with pytest.raises(ValueError) as error:
                    setup_transport.capture_once(rig.journal)
                raised = error.value
        if fault != "none":
            assert fired == [stage], "fault must reach the intended installed stage"
            assert raised is not None
            clean_error(raised)
            counts = dict(rig.counts)
            with pytest.raises(ValueError):
                rig.journal.next()
            with pytest.raises(ValueError) as repeated:
                setup_transport.capture_once(rig.journal)
            clean_error(repeated.value)
            assert rig.counts == counts
        assert rig.counts["send"] == sends
        assert rig.counts["target_send"] == target
        assert rig.counts["resolver"] == int(stage not in ("before_release", "released"))
        assert rig.counts["factory"] == sends + int(stage == "target_factory")
        assert (rig.order.logical_path in rig.service.objects) is bool(target)
        if stage == "target_factory":
            assert rig.counts["resolver"] == 1 and rig.counts["factory"] == 3
        if stage == "target_response":
            assert rig.target_raw is not None
            records = rig.journal.records[rig.record_start :]
            retained = next(
                r for r in records if r["kind"] in ("native_exchange", "native_interruption")
            )
            original = retained["payload"]
            if fault == "partial":
                assert not original["complete"]
                original = original["exchange"]
            assert bytes.fromhex(original["response_hex"]) == b"".join(rig.target_chunks)
            assert not any(r["kind"] == "capture" for r in records)
        assert CANARY not in json.dumps(rig.journal.records)
        captured = capsys.readouterr()
        assert CANARY not in captured.out + captured.err
        if fault == "partial":
            rig.journal.close()
            record_property("recovery", fresh_recovery(rig, "UNKNOWN_NO_REDISPATCH"))
    finally:
        record_property("installed_boundary", json.dumps(rig.evidence(), sort_keys=True))
        rig.journal.close()


def stored_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for side in ("run", "checkpoint")
        for p in (root / side).glob("*.json")
    }


def fresh_recovery(rig: InstalledRun, expected: str) -> str:
    """Same source/runtime/store pins; child cannot resolve credentials or connect."""
    for name, raw in (
        ("grant", rig.grant_raw),
        ("installation", rig.pin),
        ("bindings", rig.bindings),
    ):
        (rig.root / (name + ".json")).write_bytes(raw)
    before = stored_bytes(rig.root)
    code = """
import sys
from pathlib import Path
from datetime import datetime
sys.modules['peru_conflicts.execution.setup_offline'] = None
from peru_conflicts.execution import setup_deployment, setup_transport
from peru_conflicts.execution.setup_evidence import EvidenceJournal
calls = []
def prohibited(*args, **kwargs):
    calls.append('prohibited')
    raise AssertionError('recovery reached resolver or provider')
setup_transport._read_credential = prohibited
setup_transport._connection = prohibited
root = Path(sys.argv[1])
pin = (root / 'installation.json').read_bytes()
context = vars(setup_deployment)['_load_verified'](
    (root / 'grant.json').read_bytes(), pin, sys.argv[2],
    lambda: (root / 'bindings.json').read_bytes(), lambda: pin,
    clock=lambda: datetime.fromisoformat('2026-09-23T12:00:00+00:00'))
try:
    journal = EvidenceJournal(root / 'run', root / 'checkpoint', context, create=False)
except ValueError as error:
    assert str(error) in (
        'checkpoint mismatch: interrupted publication/rollback', 'checkpoint head mismatch')
    result = 'CHECKPOINT_STOP'
else:
    try:
        expected = sys.argv[3]
        if expected == 'COMPLETED_NO_REDISPATCH':
            assert journal.pending is None
            last = journal.records[-1]
            assert last['kind'] == 'outcome' and last['order']['action'] == 'cleanup'
            assert last['payload']['result'] == 'PASS'
            assert journal.preview().logical_path != last['order']['logical_path']
        elif expected == 'STOPPED_NO_REDISPATCH':
            assert journal.pending is None
            assert journal.records[-1]['payload']['result'] not in ('PASS', 'PENDING')
        else:
            assert journal.pending is not None
        operations = [lambda: setup_transport.capture_once(journal)]
        if expected != 'COMPLETED_NO_REDISPATCH':
            operations.append(journal.next)
        for operation in operations:
            try:
                operation()
            except ValueError:
                pass
            else:
                raise AssertionError('recovery permitted follow-on work')
        result = expected
    finally:
        journal.close()
assert not calls
assert result == sys.argv[3]
print(result)
"""
    child = subprocess.run(
        [sys.executable, "-c", code, str(rig.root), sha256(rig.pin), expected],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert child.returncode == 0, "fresh recovery failed (output intentionally withheld)"
    assert child.stdout.strip() == expected
    assert not child.stderr
    assert stored_bytes(rig.root) == before
    return expected


@pytest.mark.parametrize(
    "kind,side,phase,sends,recovery",
    [
        ("intent", "run", "partial", 0, "CHECKPOINT_STOP"),
        ("intent", "run", "fsync", 0, "CHECKPOINT_STOP"),
        ("intent", "checkpoint", "open", 0, "CHECKPOINT_STOP"),
        ("intent", "checkpoint", "fsync", 0, "UNKNOWN_NO_REDISPATCH"),
        ("intent", "checkpoint", "directory_sync", 0, "UNKNOWN_NO_REDISPATCH"),
        ("dispatch", "run", "open", 0, "UNKNOWN_NO_REDISPATCH"),
        ("dispatch", "run", "partial", 0, "CHECKPOINT_STOP"),
        ("dispatch", "checkpoint", "partial", 0, "CHECKPOINT_STOP"),
        ("dispatch", "checkpoint", "fsync", 0, "UNKNOWN_NO_REDISPATCH"),
        ("native_exchange", "run", "partial", 3, "CHECKPOINT_STOP"),
        ("native_exchange", "checkpoint", "open", 3, "CHECKPOINT_STOP"),
        ("native_exchange", "checkpoint", "fsync", 3, "UNKNOWN_NO_REDISPATCH"),
        ("native_exchange", "checkpoint", "readback", 3, "UNKNOWN_NO_REDISPATCH"),
        ("capture", "run", "partial", 4, "CHECKPOINT_STOP"),
        ("capture", "checkpoint", "open", 4, "CHECKPOINT_STOP"),
        ("outcome", "run", "partial", 4, "CHECKPOINT_STOP"),
        ("outcome", "checkpoint", "open", 4, "CHECKPOINT_STOP"),
    ],
)
def test_installed_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Callable[[str, object], None],
    kind: str,
    side: str,
    phase: str,
    sends: int,
    recovery: str,
):
    rig = InstalledRun(tmp_path, monkeypatch)
    original_publish = setup_evidence.publish
    original_open = DirectoryLease.open_child_exclusive
    original_fsync = setup_evidence.os.fsync
    original_sync = DirectoryLease.sync_directory
    original_read = DirectoryLease.open_child_read
    active: tuple[str, str, str] | None = None
    kinds: dict[str, str] = {}
    fired: list[str] = []
    failed_name = ""

    def observe(directory: DirectoryLease, name: str, raw: bytes):
        nonlocal active
        current_side = directory.resolved.name
        if current_side == "run":
            kinds[name] = json.loads(raw)["kind"]
        active = (kinds[name], current_side, name)
        try:
            original_publish(directory, name, raw)
        finally:
            active = None

    def selected(point: str) -> bool:
        nonlocal failed_name
        if active and active[:2] == (kind, side) and phase == point and not fired:
            fired.append(point)
            failed_name = active[2]
            return True
        return False

    class PartialWriter:
        def __init__(self, stream: Any):
            self.stream = stream

        def write(self, raw: bytes):
            self.stream.write(raw[:7])
            self.stream.flush()
            raise OSError(CANARY)

    @contextmanager
    def open_file(directory: DirectoryLease, name: str) -> Generator[Any]:
        if selected("open"):
            raise OSError(CANARY)
        with original_open(directory, name) as stream:
            yield PartialWriter(stream) if selected("partial") else stream

    def fsync(fd: int):
        if selected("fsync"):
            raise OSError(CANARY)
        original_fsync(fd)

    def sync(directory: DirectoryLease):
        if selected("directory_sync"):
            raise OSError(CANARY)
        original_sync(directory)

    def read(directory: DirectoryLease, name: str):
        if selected("readback"):
            raise OSError(CANARY)
        return original_read(directory, name)

    monkeypatch.setattr(setup_evidence, "publish", observe)
    monkeypatch.setattr(DirectoryLease, "open_child_exclusive", open_file)
    monkeypatch.setattr(setup_evidence.os, "fsync", fsync)
    monkeypatch.setattr(DirectoryLease, "sync_directory", sync)
    monkeypatch.setattr(DirectoryLease, "open_child_read", read)
    try:
        with pytest.raises(Exception) as error:
            rig.journal.next()
            setup_transport.capture_once(rig.journal)
        assert fired == [phase]
        assert rig.counts["send"] == sends
        assert rig.counts["target_send"] == int(sends > 0)
        assert rig.counts["resolver"] == int(sends > 0)
        assert rig.counts["factory"] == sends
        assert (rig.order.logical_path in rig.service.objects) is (sends > 0)
        disk = stored_bytes(rig.root)
        record_property(
            "publication_fault",
            json.dumps(
                {
                    "kind": kind,
                    "side": side,
                    "phase": phase,
                    "name": failed_name,
                    "files": {
                        s: (
                            {"bytes": len(raw), "sha256": sha256(raw)}
                            if (raw := disk.get(f"{s}/{failed_name}")) is not None
                            else None
                        )
                        for s in ("run", "checkpoint")
                    },
                },
                sort_keys=True,
            ),
        )
        if phase == "partial":
            assert len(disk[f"{side}/{failed_name}"]) == 7
        elif phase == "open":
            assert f"{side}/{failed_name}" not in disk
        # Exact originals are asserted only when the actual record write completed.
        retained: list[bytes] = []
        for name, raw in disk.items():
            if not name.startswith("run/"):
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if record.get("kind") == "native_exchange" and record["order"]["action"] == "create":
                retained.append(bytes.fromhex(record["payload"]["response_hex"]))
        assert retained == (
            [rig.target_raw] if sends and not (kind == "native_exchange" and side == "run") else []
        )
        assert not any(r["kind"] == "outcome" for r in rig.journal.records[rig.record_start :])
        counts = dict(rig.counts)
        with pytest.raises(ValueError):
            rig.journal.next()
        with pytest.raises(ValueError):
            setup_transport.capture_once(rig.journal)
        assert rig.counts == counts
        assert stored_bytes(rig.root) == disk
        rig.journal.close()
        result = fresh_recovery(rig, recovery)
        record_property("recovery", result)
        record_property("retention", "complete_original" if retained else "no_complete_original")
        clean_error(error.value)
        assert all(CANARY.encode() not in raw for raw in disk.values())
        captured = capsys.readouterr()
        assert CANARY not in captured.out + captured.err
    finally:
        record_property("installed_boundary", json.dumps(rig.evidence(), sort_keys=True))
        rig.journal.close()
