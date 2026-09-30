"""Native cleanup against independent synthetic state; no sockets or real trust."""

import json
from collections import Counter
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from test_m2_setup_deployment import installation_fixture
from test_m2_setup_dispatch_persistence import clean_error, fresh_recovery
from test_m2_setup_native_procedure import connect_service, load_test_context
from test_m2_setup_transport_adversarial import Reply

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.execution import setup_evidence, setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_authority import SetupGrantV2
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.execution.setup_dropbox import (
    PROBE,
    Exchange,
    FileObservation,
    FolderObservation,
    PreparedRequest,
    cleanup_arguments,
)
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP

DELETE = "files/delete_v2"
CANARY = "SYNTHETIC-EXCEPTION-SECRET-NEVER-RETAIN"
SCOPES = (
    "account_info.read",
    "files.metadata.read",
    "files.content.read",
    "files.content.write",
    "sharing.read",
    "sharing.write",
)


class CleanupService(FakeHTTP):
    """Faults affect service execution/acknowledgement, never consult an expected result."""

    def __init__(self):
        super().__init__(None)
        self.fault = "none"
        self.responses: list[Exchange] = []
        self.effects: list[dict[str, Any]] = []

    def _respond(self, request: PreparedRequest, fault: str | None) -> Exchange:
        if request.route != DELETE:
            result = super()._respond(request, fault)
            self.responses.append(result)
            return result
        args = json.loads(bytes.fromhex(request.body_hex))
        path = self._path(args, request.actor_session_ref)
        before = self.objects.get(path)
        assert isinstance(before, FileObservation)
        if self.fault == "race":
            self.objects[path] = before.model_copy(update={"rev": "synthetic-raced-revision"})
        if self.fault == "lost_not_applied":
            self.calls.append(request)
            result = None
        else:
            result = super()._respond(request, fault)
        self.effects.append(
            {
                "request": args,
                "id_before": before.id,
                "rev_before": before.rev,
                "applied": path not in self.objects,
                "remaining_rev": getattr(self.objects.get(path), "rev", None),
            }
        )
        if self.fault in ("lost_applied", "lost_not_applied"):
            raise OSError(CANARY)
        assert result is not None
        self.responses.append(result)
        return result


class CleanupRun:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.root, self.grant_raw, raw, self.bindings = installation_fixture(tmp_path)
        pin = Installation.model_validate_json(raw)
        self.pin = (
            pin.model_copy(
                update={
                    "credential_refs": {s: s for s in pin.credential_refs},
                    "scopes": {s: SCOPES for s in pin.credential_refs},
                    "test_service_evidence": "complete_synthetic_service",
                }
            )
            .model_dump_json()
            .encode()
        )
        self.clock = NOW
        self.context = load_test_context(
            self.grant_raw,
            self.pin,
            sha256(self.pin),
            lambda: self.bindings,
            lambda: self.pin,
            clock=lambda: self.clock,
        )
        self.service = CleanupService()
        self.active = False
        self.counts = {"resolver": 0, "factory": 0, "send": 0, "observations": 0, "delete_send": 0}
        self.partial: list[bytes] = []
        rig = self

        class Response(Reply):
            def __init__(self, exchange: Exchange):
                super().__init__(exchange)
                self.interrupt = exchange.request.route == DELETE and rig.service.fault == "partial"

            def read1(self, size: int):
                if self.interrupt and rig.partial:
                    raise OSError(CANARY)
                chunk = super().read1(min(size, 7) if self.interrupt else size)
                if self.interrupt:
                    rig.partial.append(chunk)
                return chunk

        connect_service(monkeypatch, self.service, response_factory=Response)
        connection = vars(setup_transport)["_connection"]

        def factory(*args: Any, **kwargs: Any):
            if rig.active:
                rig.counts["factory"] += 1
            result = connection(*args, **kwargs)
            request = result.request

            def send(method: str, path: str, body: bytes, headers: dict[str, str]):
                if rig.active:
                    rig.counts["send"] += 1
                    rig.counts["delete_send"] += int(path == "/2/" + DELETE)
                    rig.counts["observations"] += int(path != "/2/" + DELETE)
                    if path == "/2/" + DELETE:
                        assert json.loads(body) == {
                            "path": rig.owned.id,
                            "parent_rev": rig.owned.rev,
                        }
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
            if rig.active:
                rig.counts["resolver"] += 1
            return "SYNTHETIC-" + reference

        monkeypatch.setattr(setup_transport, "_connection", factory)
        monkeypatch.setattr(setup_transport, "_read_credential", credential)
        self.journal = EvidenceJournal(
            self.root / "run", self.root / "checkpoint", self.context, create=True
        )
        for _ in range(1200):
            if self.journal.preview().action == "cleanup_metadata":
                break
            order = self.journal.next()
            outcome = (
                self.journal.run_component()
                if order.action == "control"
                else setup_transport.capture_once(self.journal)
            )
            assert outcome.result in ("PASS", "PENDING"), (order.action, outcome)
        else:
            pytest.fail("lawful native prefix did not reach cleanup")
        records = self.journal.records
        checks = [r for r in records if r["kind"] == "outcome" and r["order"].get("check_id")]
        assert len({r["order"]["check_id"] for r in checks}) == 108
        assert Counter(r["order"]["action"] for r in checks) == {
            "list": 36,
            "read": 36,
            "write": 36,
        }
        assert Counter(r["order"]["expected"] for r in checks) == {"ALLOW": 46, "DENY": 62}
        assert len(self.service.shares) == 4
        self.path = self.journal.preview().logical_path
        obj = self.service.objects[self.path]
        assert isinstance(obj, FileObservation)
        self.owned = obj
        assert self.service.contents[obj.id] == PROBE
        assert any(
            r["kind"] == "outcome"
            and r["order"]["action"] in ("prepare", "write")
            and r["order"]["logical_path"] == self.path
            and r["payload"]["result"] == "PASS"
            and r["payload"]["after"]["id"] == obj.id
            for r in records
        )

    def advance(self, action: str):
        while self.journal.preview().action != action:
            assert self.journal.next().action in ("cleanup_metadata", "cleanup_read")
            assert setup_transport.capture_once(self.journal).result == "PASS"

    def arm(self):
        self.order = self.journal.preview()
        self.record_start = len(self.journal.records)
        self.response_start = len(self.service.responses)
        self.calls_start = len(self.service.calls)
        self.active = True


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "id:replacement"),
        ("rev", "same-bytes-new-revision"),
        ("name", "replacement"),
        ("size", 999),
        ("content_hash", "changed"),
        ("path_display", "/moved/probe"),
        ("path_display", None),
    ],
)
def test_cleanup_comparison_never_adopts_drift(field: str, value: object):
    owned = FileObservation(
        id="id:receipt",
        rev="original",
        name="probe",
        size=len(PROBE),
        content_hash="receipt-hash",
        path_display="/owned/probe",
    )
    with pytest.raises(ValueError, match="drift"):
        cleanup_arguments(
            owned, owned.model_copy(update={field: value}), owned_logical_path="/owned/probe"
        )


def test_cleanup_comparison_rejects_folder():
    obj = FolderObservation(id="id:folder", name="probe", path_display="/owned/probe")
    with pytest.raises(ValueError, match="folder"):
        cleanup_arguments(obj, obj, owned_logical_path="/owned/probe")


@pytest.mark.parametrize(
    "fault",
    [
        "positive",
        "body",
        "late_revision",
        "race",
        "lost_applied",
        "lost_not_applied",
        "partial",
        "publication",
    ],
)
def test_installed_native_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_property: Callable[[str, object], None],
    fault: str,
):
    rig = CleanupRun(tmp_path, monkeypatch)
    recovery = "not_requested"
    result = "UNKNOWN"
    try:
        rig.advance("cleanup_read" if fault == "body" else "cleanup")
        rig.arm()
        others = {p: obj for p, obj in rig.service.objects.items() if p != rig.path}
        assert rig.journal.next() == rig.order
        rig.service.fault = fault
        if fault == "body":
            rig.service.contents[rig.owned.id] = PROBE[:-1] + b"?"
        elif fault == "late_revision":
            rig.service.objects[rig.path] = rig.owned.model_copy(
                update={"rev": "same-bytes-new-revision"}
            )

        publish = setup_evidence.publish
        open_file = DirectoryLease.open_child_exclusive
        active = False
        partial_record: list[str] = []

        def observe(directory: DirectoryLease, name: str, raw: bytes):
            nonlocal active
            active = (
                fault == "publication"
                and directory.resolved.name == "run"
                and json.loads(raw).get("kind") == "native_exchange"
            )
            try:
                publish(directory, name, raw)
            finally:
                active = False

        class Partial:
            def __init__(self, stream: Any):
                self.stream = stream

            def write(self, raw: bytes):
                self.stream.write(raw[:7])
                self.stream.flush()
                raise OSError(CANARY)

        @contextmanager
        def opening(directory: DirectoryLease, name: str) -> Generator[Any]:
            with open_file(directory, name) as stream:
                if active:
                    partial_record.append(name)
                    yield Partial(stream)
                else:
                    yield stream

        monkeypatch.setattr(setup_evidence, "publish", observe)
        monkeypatch.setattr(DirectoryLease, "open_child_exclusive", opening)
        if fault in ("positive", "body", "race"):
            outcome = setup_transport.capture_once(rig.journal)
            result = outcome.result
            assert (result == "PASS") is (fault == "positive")
        else:
            with pytest.raises(ValueError) as error:
                setup_transport.capture_once(rig.journal)
            clean_error(error.value)

        before_count = len(rig.order.before)
        delete_sent = fault not in ("body", "late_revision")
        applied = fault not in ("body", "late_revision", "race", "lost_not_applied")
        assert rig.counts["delete_send"] == int(delete_sent)
        assert sum(e["applied"] for e in rig.service.effects) == int(applied)
        assert (rig.path not in rig.service.objects) is applied
        assert {p: obj for p, obj in rig.service.objects.items() if p != rig.path} == others
        assert rig.counts["resolver"] == 1
        assert rig.counts["factory"] == rig.counts["send"]
        expected = (
            2 * before_count + 2
            if fault in ("positive", "body", "race")
            else before_count + 1 + int(delete_sent)
        )
        assert rig.counts["send"] == expected
        assert rig.counts["observations"] == expected - int(delete_sent)
        records = rig.journal.records[rig.record_start :]
        originals = [r for r in records if r["kind"] == "native_exchange"]
        if fault in ("positive", "body", "race"):
            response = next(
                e
                for e in rig.service.responses[rig.response_start :]
                if e.request == rig.order.request
            )
            assert len(originals) == 1 and originals[0]["payload"] == response.model_dump(
                mode="json"
            )
            if fault == "race":
                assert response.status == 409
                assert (
                    json.loads(bytes.fromhex(response.response_hex))["error"]["path"][".tag"]
                    == "conflict"
                )
                assert rig.service.contents[rig.owned.id] == PROBE
        else:
            assert not originals
        if fault == "partial":
            interrupted = next(r["payload"] for r in records if r["kind"] == "native_interruption")
            assert not interrupted["complete"]
            assert bytes.fromhex(interrupted["exchange"]["response_hex"]) == b"".join(rig.partial)
            assert len(b"".join(rig.partial)) == 7
        if fault == "publication":
            assert len(partial_record) == 1
            assert len((rig.root / "run" / partial_record[0]).read_bytes()) == 7
            assert not (rig.root / "checkpoint" / partial_record[0]).exists()

        counts = dict(rig.counts)
        if fault != "positive":
            with pytest.raises(ValueError):
                rig.journal.next()
            with pytest.raises(ValueError):
                setup_transport.capture_once(rig.journal)
            assert rig.counts == counts
        rig.journal.close()
        recovery = fresh_recovery(
            cast(Any, rig),
            {
                "publication": "CHECKPOINT_STOP",
                "positive": "COMPLETED_NO_REDISPATCH",
                "body": "STOPPED_NO_REDISPATCH",
                "race": "STOPPED_NO_REDISPATCH",
            }.get(fault, "UNKNOWN_NO_REDISPATCH"),
        )
        if fault == "positive":
            # A genuine receipt from this run cannot authorize another installed run.
            foreign_dir = tmp_path / "foreign"
            foreign_dir.mkdir()
            root, grant_raw, pin_raw, bindings = installation_fixture(foreign_dir)
            grant = SetupGrantV2.model_validate_json(grant_raw).model_copy(
                update={"run_ref": "synthetic-other-run"}
            )
            grant_raw = grant.model_dump_json().encode()
            pin_raw = (
                Installation.model_validate_json(pin_raw)
                .model_copy(update={"grant_sha256": sha256(grant_raw)})
                .model_dump_json()
                .encode()
            )
            context = load_test_context(
                grant_raw,
                pin_raw,
                sha256(pin_raw),
                lambda: bindings,
                lambda: pin_raw,
                clock=lambda: NOW,
            )
            other = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
            try:
                assert other.preview().action == "root"
                with pytest.raises(ValueError, match="admitted next order"):
                    other.release(rig.order)
                assert not other.records
            finally:
                other.close()
            assert rig.counts == counts
            # Continue only the successful run, without reconstructing its history.
            rig.journal = EvidenceJournal(
                rig.root / "run", rig.root / "checkpoint", rig.context, create=False
            )
            rig.advance("cleanup")
            stale_counts = dict(rig.counts)
            rig.clock += timedelta(hours=1)
            with pytest.raises(ValueError, match=r"stale|expired|validity"):
                rig.journal.next()
            assert rig.counts == stale_counts
        assert CANARY not in json.dumps(records)
        captured = capsys.readouterr()
        assert CANARY not in captured.out + captured.err
        record_property(
            "cleanup",
            json.dumps(
                {
                    "fault": fault,
                    "action": rig.order.action,
                    "before_objects": before_count,
                    **counts,
                    "effects": rig.service.effects,
                    "result": result,
                    "recovery": recovery,
                    "record_kinds": [r["kind"] for r in records],
                    "partial_record": partial_record,
                },
                sort_keys=True,
            ),
        )
    finally:
        rig.journal.close()


@pytest.mark.parametrize("drift", ["missing", "replacement", "moved", "folder"])
def test_installed_cleanup_target_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
    drift: str,
):
    """Independent target state changes after valid metadata/read and intent release."""
    rig = CleanupRun(tmp_path, monkeypatch)
    try:
        rig.advance("cleanup")
        rig.arm()
        assert rig.journal.next() == rig.order
        if drift == "missing":
            del rig.service.objects[rig.path]
        elif drift == "replacement":
            replacement = rig.owned.model_copy(update={"id": "id:synthetic-replacement"})
            rig.service.objects[rig.path] = replacement
            rig.service.contents[replacement.id] = PROBE
        elif drift == "moved":
            moved_path = "/outside/" + rig.owned.name
            del rig.service.objects[rig.path]
            rig.service.objects[moved_path] = rig.owned.model_copy(
                update={"path_display": moved_path, "path_lower": moved_path.lower()}
            )
        else:
            rig.service.objects[rig.path] = FolderObservation(
                id=rig.owned.id,
                name=rig.owned.name,
                path_display=rig.path,
                path_lower=rig.path.lower(),
            )
        objects = dict(rig.service.objects)
        contents = dict(rig.service.contents)
        with pytest.raises(ValueError) as error:
            setup_transport.capture_once(rig.journal)
        clean_error(error.value)
        expected = len(rig.order.before) + 1
        assert rig.counts == {
            "resolver": 1,
            "factory": expected,
            "send": expected,
            "observations": expected,
            "delete_send": 0,
        }
        assert not rig.service.effects
        assert rig.service.objects == objects and rig.service.contents == contents
        records = rig.journal.records[rig.record_start :]
        assert [r["kind"] for r in records] == ["intent", "dispatch"] + [
            "native_observation"
        ] * expected
        # Exact supplementary originals remain separate from an action exchange.
        responses = rig.service.responses[rig.response_start :]
        assert [r["payload"]["exchange"] for r in records[2:]] == [
            response.model_dump(mode="json") for response in responses
        ]
        assert rig.journal.pending == rig.order
        counts = dict(rig.counts)
        for operation in (rig.journal.next, lambda: setup_transport.capture_once(rig.journal)):
            with pytest.raises(ValueError):
                operation()
        assert rig.counts == counts
        rig.journal.close()
        recovery = fresh_recovery(cast(Any, rig), "UNKNOWN_NO_REDISPATCH")
        record_property(
            "cleanup_preflight",
            json.dumps(
                {
                    "drift": drift,
                    "action": rig.order.action,
                    **counts,
                    "applied_deletes": 0,
                    "result": "UNKNOWN",
                    "recovery": recovery,
                    "response_statuses": [r.status for r in responses],
                    "original_sha256": [sha256(bytes.fromhex(r.response_hex)) for r in responses],
                    "record_kinds": [r["kind"] for r in records],
                },
                sort_keys=True,
            ),
        )
    finally:
        rig.journal.close()
