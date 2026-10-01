"""Shared journal context and durable dispatch, before any production installation."""

import builtins
from pathlib import Path

import pytest

from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import FakeHTTP, admit_fixture


def fixture_run(tmp_path: Path):
    root = tmp_path / "m2-readiness-context"
    root.mkdir()
    for name in ("run", "checkpoint", "components"):
        (root / name).mkdir()
    return root, admit_fixture(root)


def test_journal_does_not_import_fixture_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, context = fixture_run(tmp_path)
    original = builtins.__import__

    def guarded(name: str, *args: object, **kwargs: object):
        if name.endswith("setup_offline"):
            raise AssertionError("journal still imports fixture authority")
        return original(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", guarded)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = journal.next()
        assert order.action == "root"
        raw = FakeHTTP(context).execute(order)
        assert journal.import_capture(raw).result == "PASS"
    finally:
        journal.close()


def test_consumption_is_durable_before_response_and_survives_reopen(tmp_path: Path):
    root, context = fixture_run(tmp_path)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    order = journal.next()
    try:
        with pytest.raises(TimeoutError):
            FakeHTTP(context).execute(order, fault="unknown")
        assert [r["kind"] for r in journal.records] == ["intent", "dispatch"]
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        assert resumed.pending == order
        with pytest.raises(ValueError, match=r"released|dispatched|UNKNOWN"):
            FakeHTTP(context).execute(order)
        assert [r["kind"] for r in resumed.records] == ["intent", "dispatch"]
    finally:
        resumed.close()
