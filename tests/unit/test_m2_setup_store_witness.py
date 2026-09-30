"""Installed resource and transferred-file boundaries, using disposable local stores."""

import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_m2_setup_deployment import installation_fixture

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.execution import setup_transport
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_authority import SetupGrantV2
from peru_conflicts.execution.setup_bridge import digest
from peru_conflicts.execution.setup_deployment import (
    Installation,
    _load_verified,  # pyright: ignore[reportPrivateUsage]
    store_pin,
)
from peru_conflicts.execution.setup_dropbox import OriginalCapture
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP
from peru_conflicts.hashing import canonical_json_bytes

CANARY = "SYNTHETIC-PRIVATE-READ-ERROR-DO-NOT-EXPOSE"


@pytest.fixture(autouse=True)
def no_provider_callbacks(
    monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, Any], None]
) -> Iterator[list[str]]:
    counts = {"resolver": 0, "factory": 0}

    def resolver(*args: Any, **kwargs: Any):
        counts["resolver"] += 1
        raise AssertionError("unexpected credential resolution")

    def factory(*args: Any, **kwargs: Any):
        counts["factory"] += 1
        raise AssertionError("unexpected connection creation")

    monkeypatch.setattr(setup_transport, "_read_credential", resolver)
    monkeypatch.setattr(setup_transport, "_connection", factory)
    reads: list[str] = []
    opened = DirectoryLease.open_child_read

    def read(lease: DirectoryLease, name: str):
        if lease.path.name == "witness":
            reads.append(name)
        return opened(lease, name)

    monkeypatch.setattr(DirectoryLease, "open_child_read", read)
    yield reads
    record_property("callback_counts", json.dumps(counts))
    record_property("witness_source_reads", json.dumps(reads))
    assert counts == {"resolver": 0, "factory": 0}
    assert all(re.fullmatch(r"[0-9a-f]{64}\.(json|capture)", name) for name in reads)


class Rig:
    def __init__(self, tmp_path: Path):
        self.root, self.grant, self.pin, self.bindings = installation_fixture(tmp_path)
        self.now = NOW

    def context(self):
        return _load_verified(
            self.grant,
            self.pin,
            sha256(self.pin),
            lambda: self.bindings,
            lambda: self.pin,
            clock=lambda: self.now,
        )

    def open(self, *, create: bool = True):
        return EvidenceJournal(
            self.root / "run", self.root / "checkpoint", self.context(), create=create
        )

    def transfer(self, journal: EvidenceJournal) -> bytes:
        order = journal.next()
        assert order.action == "root" and order.sequence == 1
        journal.consume(order)
        # Service response depends on independent account state, never expected check/result.
        service = FakeHTTP(None)
        exchange = service._respond(order.request, None)  # pyright: ignore[reportPrivateUsage]
        assert service.calls == [order.request]
        raw = (
            OriginalCapture(
                order_sha256=digest(order),
                actor_session_ref=order.actor.session_ref,
                namespace=json.loads(order.request.root_header)["namespace_id"],
                started=NOW,
                ended=NOW,
                exchanges=(exchange,),
                before_hex=(),
                after_hex=(),
            )
            .model_dump_json()
            .encode()
        )
        self.register(journal, raw)
        return raw

    def register(self, journal: EvidenceJournal, raw: bytes) -> None:
        assert journal.pending is not None
        witness = self.root / "witness"
        (witness / (digest(journal.pending) + ".json")).write_bytes(
            canonical_json_bytes({"order": digest(journal.pending), "capture": sha256(raw)})
        )
        (witness / (sha256(raw) + ".capture")).write_bytes(raw)


def files(root: Path) -> dict[str, bytes]:
    # Windows denies reading the held lock byte, including from this process.
    # Compare immutable evidence/claim/checkpoint bytes, not the kernel lock file.
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.name != "writer.lock"
    }


def import_file(journal: EvidenceJournal):
    return journal.import_capture_file()


def test_installed_transfer_control(tmp_path: Path):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        raw = rig.transfer(journal)
        assert import_file(journal).result == "PASS"
        capture = journal.records[-2]["payload"]
        assert bytes.fromhex(capture["original_hex"]) == raw
        assert capture["source"] == "independent_witness"
        assert capture["witness_sha256"] == sha256(raw)
        assert journal.pending is None
        with pytest.raises(ValueError):
            import_file(journal)
    finally:
        journal.close()
    reopened = rig.open(create=False)
    try:
        assert not reopened.stopped and reopened.pending is None
        assert [r["kind"] for r in reopened.records] == ["intent", "dispatch", "capture", "outcome"]
    finally:
        reopened.close()


def child_reopen(rig: Rig, expected: str) -> str:
    """Separate interpreter; parent supplies test trust, no offline globals/network."""
    for name, raw in (("grant", rig.grant), ("pin", rig.pin), ("bindings", rig.bindings)):
        (rig.root / (name + ".json")).write_bytes(raw)
    imports = [
        str(Path(sys.prefix) / "Lib/site-packages"),
        str(Path(__file__).resolve().parents[2] / "src"),
    ]
    code = f"""
import sys
def deny(event, args):
    if event.startswith('socket.') and event != 'socket.gethostname':
        raise AssertionError('NETWORK_FORBIDDEN')
sys.addaudithook(deny)
sys.prefix = sys.exec_prefix = {sys.prefix!r}
sys.path.extend({imports!r})
sys.modules['peru_conflicts.execution.setup_offline'] = None
from pathlib import Path
from datetime import datetime
from peru_conflicts.execution.setup_deployment import _load_verified
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution import setup_transport
calls = []
def forbidden(*args, **kwargs):
    calls.append('forbidden')
    raise AssertionError('PRIVATE_PROVIDER_BOUNDARY')
setup_transport._connection = setup_transport._read_credential = forbidden
root = Path({str(rig.root)!r})
raw = (root / 'pin.json').read_bytes()
context = _load_verified((root/'grant.json').read_bytes(), raw, {sha256(rig.pin)!r},
    lambda: (root/'bindings.json').read_bytes(), lambda: raw,
    clock=lambda: datetime.fromisoformat({NOW.isoformat()!r}))
try:
    journal = EvidenceJournal(root/'run', root/'checkpoint', context, create=False)
except (ValueError, RuntimeError):
    assert {expected!r} == 'reject'
    print('REJECT_NO_CALLBACKS')
else:
    try:
        assert {expected!r} != 'reject'
        if {expected!r} in ('import', 'invalid_import'):
            assert journal.pending is not None
            if {expected!r} == 'import':
                assert journal.import_capture_file().result == 'PASS'
                assert journal.records[-2]['payload']['source'] == 'independent_witness'
            else:
                before = journal.records
                try: journal.import_capture_file()
                except ValueError: pass
                else: raise AssertionError('unwitnessed bytes accepted')
                assert journal.records == before
                try: journal.consume(journal.pending)
                except ValueError: pass
                else: raise AssertionError('redispatched')
        elif {expected!r} == 'complete':
            assert journal.pending is None and not journal.stopped
        elif {expected!r} == 'stopped':
            assert journal.pending is None and journal.stopped
            try: journal.next()
            except ValueError: pass
            else: raise AssertionError('advanced')
        else:
            assert journal.pending is not None
            try: journal.consume(journal.pending)
            except ValueError: pass
            else: raise AssertionError('redispatched')
            try: setup_transport.capture_once(journal)
            except ValueError: pass
            else: raise AssertionError('provider dispatch')
        print('RECOVERED_' + {expected!r} + '_NO_CALLBACKS')
    finally: journal.close()
assert not calls
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("state", ["pending", "consumed", "complete", "stopped"])
def test_installed_fresh_process_history(tmp_path: Path, state: str):
    rig = Rig(tmp_path)
    journal = rig.open()
    if state == "pending":
        journal.next()
    elif state == "consumed":
        journal.consume(journal.next())
    else:
        rig.transfer(journal)
        if state == "stopped":
            rig.register(journal, b'{"unfinished":')
        assert import_file(journal).result == ("PASS" if state == "complete" else "INCONCLUSIVE")
    journal.close()
    before = {k: files(rig.root / k) for k in ("run", "checkpoint")}
    assert child_reopen(rig, state) == f"RECOVERED_{state}_NO_CALLBACKS"
    assert before == {k: files(rig.root / k) for k in before}


def test_installed_second_process_writer_exclusion(tmp_path: Path):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        journal.consume(journal.next())
        before = {k: files(rig.root / k) for k in ("run", "checkpoint")}
        assert child_reopen(rig, "reject") == "REJECT_NO_CALLBACKS"
        assert before == {k: files(rig.root / k) for k in before}
    finally:
        journal.close()


@pytest.mark.parametrize(
    "fault",
    [
        "run_missing",
        "run_truncated",
        "checkpoint_missing",
        "checkpoint_changed",
        "rollback",
        "other_run",
    ],
)
def test_installed_history_inconsistency(tmp_path: Path, fault: str):
    rig = Rig(tmp_path)
    journal = rig.open()
    journal.consume(journal.next())
    journal.close()
    run = rig.root / "run" / "000002.json"
    checkpoint = rig.root / "checkpoint" / "000002.json"
    if fault in ("run_missing", "rollback"):
        run.rename(rig.root / "preserved-dispatch.json")
    elif fault == "run_truncated":
        original = run.read_bytes()
        (rig.root / "preserved-dispatch.json").write_bytes(original)
        run.write_bytes(original[:40])
    elif fault == "checkpoint_missing":
        checkpoint.rename(rig.root / "preserved-checkpoint.json")
    elif fault == "checkpoint_changed":
        checkpoint.rename(rig.root / "preserved-checkpoint.json")
        checkpoint.write_bytes(b"0" * 64)
    else:
        grant = SetupGrantV2.model_validate_json(rig.grant).model_copy(
            update={"run_ref": "other-test-run", "grant_ref": "other-test-grant"}
        )
        rig.grant = grant.model_dump_json().encode()
        rig.pin = (
            Installation.model_validate_json(rig.pin)
            .model_copy(update={"grant_sha256": sha256(rig.grant)})
            .model_dump_json()
            .encode()
        )
    before = {k: files(rig.root / k) for k in ("run", "checkpoint")}
    with pytest.raises(ValueError):
        rig.open(create=False)
    assert before == {k: files(rig.root / k) for k in before}
    if fault == "rollback":
        assert child_reopen(rig, "reject") == "REJECT_NO_CALLBACKS"


@pytest.mark.parametrize(
    "fault", ["same", "nested", "forbidden", "access", "inode", "type", "copied"]
)
def test_installed_store_admission(tmp_path: Path, fault: str):
    rig = Rig(tmp_path)
    pin = Installation.model_validate_json(rig.pin)
    changes: dict[str, Any] = {}
    if fault == "same":
        changes["checkpoint"] = pin.store
    elif fault == "nested":
        nested = rig.root / "run" / "nested"
        nested.mkdir()
        changes["checkpoint"] = store_pin(nested)
    elif fault == "forbidden":
        changes["forbidden_roots"] = (*pin.forbidden_roots, str(rig.root))
    elif fault in ("access", "inode"):
        changes["store"] = pin.store.model_copy(
            update={"access_sha256": "0" * 64}
            if fault == "access"
            else {"inode": pin.store.inode + 1}
        )
    elif fault == "type":
        (rig.root / "run").rename(rig.root / "preserved-run")
        (rig.root / "run").write_bytes(b"not a directory")
    else:
        journal = rig.open()
        journal.consume(journal.next())
        journal.close()
        shutil.copytree(rig.root / "run", rig.root / "copied-run")
        before = files(rig.root / "copied-run")
        with pytest.raises(ValueError, match="store mismatch"):
            EvidenceJournal(
                rig.root / "copied-run", rig.root / "checkpoint", rig.context(), create=False
            )
        assert files(rig.root / "copied-run") == before
        return
    rig.pin = pin.model_copy(update=changes).model_dump_json().encode()
    before = files(rig.root)
    with pytest.raises((ValueError, DirectoryLeaseError, OSError)):
        rig.open()
    assert files(rig.root) == before


@pytest.mark.parametrize(
    "fault",
    [
        "unwitnessed",
        "wrong_order",
        "locator",
        "mismatch",
        "oversized",
        "credential",
        "hardlink",
        "directory",
        "read_error",
    ],
)
def test_installed_transfer_rejects_before_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    no_provider_callbacks: list[str],
):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        raw = rig.transfer(journal)
        assert journal.pending is not None
        source = rig.root / "witness" / (sha256(raw) + ".capture")
        index = rig.root / "witness" / (digest(journal.pending) + ".json")
        if fault == "unwitnessed":
            index.rename(rig.root / "withheld-witness.json")
        elif fault in ("wrong_order", "locator"):
            index.write_bytes(
                canonical_json_bytes(
                    {
                        "order": "0" * 64 if fault == "wrong_order" else digest(journal.pending),
                        "capture": str(rig.root / CANARY) if fault == "locator" else sha256(raw),
                    }
                )
            )
        elif fault == "mismatch":
            source.write_bytes(b"{}")
        elif fault == "oversized":
            rig.register(journal, b"x" * 8388609)
        elif fault == "credential":
            rig.register(journal, b'{"access_token":"' + CANARY.encode() + b'"}')
        elif fault == "hardlink":
            os.link(source, rig.root / "unrelated-original")
        elif fault == "directory":
            source.rename(rig.root / "preserved-original")
            source.mkdir()
        else:
            opened = DirectoryLease.open_child_read

            def fail(lease: DirectoryLease, name: str):
                if name.endswith(".capture"):
                    raise OSError(CANARY)
                return opened(lease, name)

            monkeypatch.setattr(DirectoryLease, "open_child_read", fail)
        before = {k: files(rig.root / k) for k in ("run", "checkpoint")}
        with pytest.raises(ValueError) as error:
            import_file(journal)
        assert CANARY not in "".join(traceback.format_exception(error.value))
        assert error.value.__context__ is None and error.value.__cause__ is None
        if fault in ("unwitnessed", "wrong_order", "locator"):
            assert not any(name.endswith(".capture") for name in no_provider_callbacks)
        assert before == {k: files(rig.root / k) for k in before}
        assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
        with pytest.raises(ValueError):
            journal.next()
        with pytest.raises(ValueError):
            journal.consume(journal.pending)
    finally:
        journal.close()


@pytest.mark.parametrize("fault", ["malformed", "duplicate", "session", "stale", "c1_extra"])
def test_installed_admissible_original_retained_before_classification(tmp_path: Path, fault: str):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        raw = rig.transfer(journal)
        capture = OriginalCapture.model_validate_json(raw)
        if fault == "malformed":
            raw = b'{"unfinished":'
        elif fault == "duplicate":
            raw = b'{"x":1,"x":2}'
        elif fault == "stale":
            grant = SetupGrantV2.model_validate_json(rig.grant)
            rig.now = NOW + timedelta(seconds=grant.freshness_seconds + 1)
            assert rig.now < grant.not_after
        else:
            changes = (
                {"actor_session_ref": "other-session"}
                if fault == "session"
                else {"exchanges": (*capture.exchanges, capture.exchanges[0])}
            )
            raw = capture.model_copy(update=changes).model_dump_json().encode()
        rig.register(journal, raw)
        result = import_file(journal)
        assert result.result == "INCONCLUSIVE"
        if fault == "stale":
            assert result.reason == "stale/future capture"
        assert bytes.fromhex(journal.records[-2]["payload"]["original_hex"]) == raw
        assert journal.stopped
        with pytest.raises(ValueError):
            journal.next()
    finally:
        journal.close()


def test_transfer_retention_after_read_admission_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        raw = rig.transfer(journal)
        opened = DirectoryLease.open_child_read

        def expire(lease: DirectoryLease, name: str):
            stream = opened(lease, name)
            if name.endswith(".capture"):
                rig.now = SetupGrantV2.model_validate_json(rig.grant).not_after
            return stream

        monkeypatch.setattr(DirectoryLease, "open_child_read", expire)
        assert import_file(journal).result == "INCONCLUSIVE"
        assert bytes.fromhex(journal.records[-2]["payload"]["original_hex"]) == raw
        with pytest.raises(ValueError):
            journal.next()
    finally:
        journal.close()


@pytest.mark.parametrize("target", ["run", "checkpoint"])
def test_store_replacement_during_acquire_has_no_claim_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
):
    rig = Rig(tmp_path)
    context = rig.context()
    acquire = DirectoryLease.acquire
    replaced = False

    def replace(path: Path):
        nonlocal replaced
        if path == rig.root / target and not replaced:
            replaced = True
            path.rename(rig.root / "original-store")
            path.mkdir()
        return acquire(path)

    monkeypatch.setattr(DirectoryLease, "acquire", replace)
    with pytest.raises((ValueError, DirectoryLeaseError)):
        EvidenceJournal(rig.root / "run", rig.root / "checkpoint", context, create=True)
    assert replaced
    assert files(rig.root / "run") == {}
    assert files(rig.root / "checkpoint") == {}
    assert files(rig.root / "original-store") == {}


def test_witness_replacement_at_acquisition_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        rig.transfer(journal)
        acquire = DirectoryLease.acquire
        replaced = False

        def replace(path: Path):
            nonlocal replaced
            if path == rig.root / "witness" and not replaced:
                replaced = True
                path.rename(rig.root / "original-witness")
                shutil.copytree(rig.root / "original-witness", path)
            return acquire(path)

        monkeypatch.setattr(DirectoryLease, "acquire", replace)
        before = files(rig.root / "run")
        with pytest.raises(ValueError, match="witness"):
            import_file(journal)
        assert replaced and files(rig.root / "run") == before
    finally:
        journal.close()


def test_installed_store_directory_alias_is_rejected(tmp_path: Path):
    rig = Rig(tmp_path)
    alias = rig.root / "alias"
    if os.name == "nt":
        process = subprocess.run(
            [
                r"C:\Windows\System32\cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(alias),
                str(rig.root / "run"),
            ],
            capture_output=True,
            check=False,
        )
        assert process.returncode == 0, process.stderr
    else:
        alias.symlink_to(rig.root / "run", target_is_directory=True)
    # Measurement itself rejects the reparse path; never authorize its resolved target.
    with pytest.raises(DirectoryLeaseError):
        store_pin(alias)
    with pytest.raises((ValueError, DirectoryLeaseError)):
        EvidenceJournal(alias, rig.root / "checkpoint", rig.context(), create=True)
    assert files(rig.root / "run") == {}


def test_acquired_store_path_replacement_stops_without_substitute_writes(tmp_path: Path):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        original = files(rig.root / "run")
        try:
            (rig.root / "run").rename(rig.root / "held-run")
        except PermissionError:
            # Some Windows filesystems disallow renaming a directory with held children.
            assert files(rig.root / "run") == original
            journal.next()
        else:
            (rig.root / "run").mkdir()
            with pytest.raises((ValueError, DirectoryLeaseError)):
                journal.next()
            assert files(rig.root / "run") == {}
            assert files(rig.root / "held-run") == original
    finally:
        journal.close()


def test_parent_alias_is_not_an_admitted_store_address(tmp_path: Path):
    rig = Rig(tmp_path)
    alias = tmp_path / "alias-parent"
    if os.name == "nt":
        process = subprocess.run(
            [r"C:\Windows\System32\cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(rig.root)],
            capture_output=True,
            check=False,
        )
        assert process.returncode == 0, process.stderr
    else:
        alias.symlink_to(rig.root, target_is_directory=True)
    context = rig.context()
    # A parent reparse point must not become an alternate caller-selected address.
    # The on-disk identity is the same; the separately admitted exact path is not.
    try:
        journal = EvidenceJournal(alias / "run", alias / "checkpoint", context, create=True)
    except (ValueError, DirectoryLeaseError):
        pass
    else:
        journal.close()
        pytest.fail("unadmitted parent alias accepted")
    assert files(rig.root / "run") == {}
    assert files(rig.root / "checkpoint") == {}


@pytest.mark.parametrize("valid", [True, False])
def test_fresh_process_transferred_ingress(tmp_path: Path, valid: bool):
    rig = Rig(tmp_path)
    journal = rig.open()
    raw = rig.transfer(journal)
    journal.close()
    if not valid:
        (rig.root / "witness" / (sha256(raw) + ".capture")).write_bytes(raw[:25])
    before = {k: files(rig.root / k) for k in ("run", "checkpoint")}
    expected = "import" if valid else "invalid_import"
    assert child_reopen(rig, expected) == f"RECOVERED_{expected}_NO_CALLBACKS"
    if valid:
        retained = json.loads((rig.root / "run" / "000003.json").read_bytes())
        assert bytes.fromhex(retained["payload"]["original_hex"]) == raw
        assert all(
            files(rig.root / k)[name] == value for k in before for name, value in before[k].items()
        )
    else:
        assert before == {k: files(rig.root / k) for k in before}


def test_rebound_copy_does_not_reuse_original_history(tmp_path: Path):
    rig = Rig(tmp_path)
    journal = rig.open()
    journal.consume(journal.next())
    journal.close()
    copy = rig.root / "copied-run"
    shutil.copytree(rig.root / "run", copy)
    pin = Installation.model_validate_json(rig.pin)
    rig.pin = pin.model_copy(update={"store": store_pin(copy)}).model_dump_json().encode()
    before = files(copy)
    with pytest.raises(ValueError, match="grant/use claim mismatch"):
        EvidenceJournal(copy, rig.root / "checkpoint", rig.context(), create=False)
    assert files(copy) == before


@pytest.mark.parametrize("fault", ["oversized_index", "duplicate_index"])
def test_witness_index_rejects_before_original_read(
    tmp_path: Path, no_provider_callbacks: list[str], fault: str
):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        raw = rig.transfer(journal)
        assert journal.pending is not None
        order = digest(journal.pending)
        index = rig.root / "witness" / (order + ".json")
        if fault == "oversized_index":
            index.write_bytes(b" " * 8193)
        else:
            index.write_bytes(
                (
                    '{"order":"'
                    + order
                    + '","capture":"'
                    + sha256(raw)
                    + '","capture":"'
                    + sha256(raw)
                    + '"}'
                ).encode()
            )
        before = files(rig.root / "run")
        with pytest.raises(ValueError, match="witness"):
            import_file(journal)
        assert not any(name.endswith(".capture") for name in no_provider_callbacks)
        assert files(rig.root / "run") == before
    finally:
        journal.close()


def test_interrupted_transfer_after_read_admission_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    rig = Rig(tmp_path)
    journal = rig.open()
    try:
        rig.transfer(journal)
        partial = b'{"interrupted":'
        rig.register(journal, partial)
        opened = DirectoryLease.open_child_read

        def expire(lease: DirectoryLease, name: str):
            stream = opened(lease, name)
            if name.endswith(".capture"):
                rig.now = SetupGrantV2.model_validate_json(rig.grant).not_after
            return stream

        monkeypatch.setattr(DirectoryLease, "open_child_read", expire)
        result = import_file(journal)
        assert result.result == "INCONCLUSIVE"
        assert result.reason == "retained malformed original"
        assert bytes.fromhex(journal.records[-2]["payload"]["original_hex"]) == partial
        with pytest.raises(ValueError):
            journal.next()
    finally:
        journal.close()
    assert child_reopen(rig, "stopped") == "RECOVERED_stopped_NO_CALLBACKS"
