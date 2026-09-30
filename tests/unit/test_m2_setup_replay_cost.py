"""Historical replay must not multiply live installation verification work."""

from pathlib import Path

import pytest
from test_m2_setup_deployment import installation_fixture
from test_m2_setup_native_procedure import connect_service, load_test_context

from peru_conflicts.execution import operational_plan
from peru_conflicts.execution.references import sha256
from peru_conflicts.execution.setup_deployment import (
    Installation,
    InstalledSource,
    installed_source,
)
from peru_conflicts.execution.setup_dropbox import _SCOPES  # pyright: ignore[reportPrivateUsage]
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import NOW, FakeHTTP
from peru_conflicts.execution.setup_operator import operate


def test_reopen_verification_work_does_not_grow_with_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, grant, raw, bindings = installation_fixture(tmp_path)
    pin = Installation.model_validate_json(raw)
    raw = (
        pin.model_copy(
            update={
                "credential_refs": {s: s for s in pin.credential_refs},
                "scopes": {s: tuple(sorted(set(_SCOPES.values()))) for s in pin.credential_refs},
                "test_service_evidence": "complete_synthetic_service",
            }
        )
        .model_dump_json()
        .encode()
    )
    context = load_test_context(
        grant, raw, sha256(raw), lambda: bindings, lambda: raw, clock=lambda: NOW
    )
    service = FakeHTTP(None)
    connect_service(monkeypatch, service)
    assert operate("admit", context)["exit_code"] == 0
    checks = 0
    original = InstalledSource.check

    def checked(self: InstalledSource, run: Path, checkpoint: Path):
        nonlocal checks
        checks += 1
        return original(self, run, checkpoint)

    monkeypatch.setattr(InstalledSource, "check", checked)
    costs: list[int] = []
    for _ in range(4):
        assert operate("capture", context)["result"] == "PASS"
        before = checks
        calls = len(service.calls)
        journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
        try:
            assert journal.pending is None
            assert not journal.stopped
        finally:
            journal.close()
        assert len(service.calls) == calls
        costs.append(checks - before)
    assert len(service.calls) == 4
    assert costs == [costs[0]] * 4, costs


def test_authority_change_during_replay_rejects_before_writer_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, grant, raw, bindings = installation_fixture(tmp_path)
    current = [raw]
    context = load_test_context(
        grant, raw, sha256(raw), lambda: bindings, lambda: current[0], clock=lambda: NOW
    )
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    order = journal.next()
    journal.close()
    records = {p: p.read_bytes() for p in root.rglob("*.json")}
    parse = operational_plan.evidence_json

    def change_during_read(value: bytes):
        result = parse(value)
        if result.get("kind") == "intent":
            current[0] = b"SYNTHETIC-REVOKED-INSTALLATION"
        return result

    monkeypatch.setattr(operational_plan, "evidence_json", change_during_read)
    with pytest.raises(ValueError, match="changed/revoked"):
        EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    with pytest.raises(ValueError, match="active writer"):
        context.consume(order)
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == records


def test_live_checks_reuse_parsed_pin_but_not_authority_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, grant, raw, bindings = installation_fixture(tmp_path)
    reads = 0
    current = [raw]

    def authority() -> bytes:
        nonlocal reads
        reads += 1
        return current[0]

    context = load_test_context(
        grant, raw, sha256(raw), lambda: bindings, authority, clock=lambda: NOW
    )
    source = installed_source(context)
    detached = source.installation
    detached.source_files.clear()
    parse = Installation.model_validate_json
    parses = 0

    def counted(cls: type[Installation], value: str | bytes | bytearray) -> Installation:
        nonlocal parses
        parses += 1
        return parse(value)

    monkeypatch.setattr(Installation, "model_validate_json", classmethod(counted))
    before = reads
    for _ in range(4):
        context.check(root / "run", root / "checkpoint")
    assert reads - before == 4
    assert parses == 0
    current[0] = b"SYNTHETIC-REVOKED-INSTALLATION"
    with pytest.raises(ValueError, match="changed/revoked"):
        context.check(root / "run", root / "checkpoint")
