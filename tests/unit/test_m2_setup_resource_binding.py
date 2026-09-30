"""Residual installed resource handoffs using independent synthetic HTTP state."""

import json
from collections.abc import Callable
from contextlib import suppress
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from test_m2_setup_dispatch_persistence import stored_bytes
from test_m2_setup_native_cleanup import CleanupRun
from test_m2_setup_native_procedure import connect_service
from test_m2_setup_transport_adversarial import Reply, advance_to, installed

from peru_conflicts.execution import setup_transport
from peru_conflicts.execution.access_policy import ACCESS_POLICY_V2
from peru_conflicts.execution.setup_authority import SetupGrantV2
from peru_conflicts.execution.setup_dropbox import Exchange
from peru_conflicts.execution.setup_evidence import EvidenceJournal
from peru_conflicts.execution.setup_offline import FakeHTTP


def count_native(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"resolver": 0, "factory": 0}
    connection = vars(setup_transport)["_connection"]
    credential = vars(setup_transport)["_read_credential"]

    def factory(*args: Any, **kwargs: Any):
        counts["factory"] += 1
        return connection(*args, **kwargs)

    def resolve(reference: str):
        counts["resolver"] += 1
        return credential(reference)

    monkeypatch.setattr(setup_transport, "_connection", factory)
    monkeypatch.setattr(setup_transport, "_read_credential", resolve)
    return counts


@pytest.mark.parametrize("substituted", [False, True])
def test_installed_completed_share_remains_bound_at_invite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
    substituted: bool,
) -> None:
    root, context = installed(tmp_path, complete=True)
    service = FakeHTTP(None)
    originals: list[bytes] = []

    def response(exchange: Exchange):
        originals.append(bytes.fromhex(exchange.response_hex))
        return Reply(exchange)

    connect_service(monkeypatch, service, response_factory=response)
    counts = count_native(monkeypatch)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        order = advance_to(journal, "invite")
        assert order.shared_folder_id is not None
        share = service.shares[order.shared_folder_id]
        assert share["path"] == order.logical_path
        assert not share["pending"]
        if substituted:
            # The service changes independently after a correctly completed share.
            share["path"] = str(PurePosixPath(order.logical_path).parent)
        start = len(service.calls)
        record_start = len(journal.records)
        counts.update(resolver=0, factory=0)
        if substituted:
            with pytest.raises(ValueError):
                setup_transport.capture_once(journal)
        else:
            assert setup_transport.capture_once(journal).result == "PASS"
        calls = service.calls[start:]
        invitations = [r for r in calls if r.route == "sharing/add_folder_member"]
        assert len(invitations) == (0 if substituted else 1)
        assert bool(share["pending"]) is not substituted
        captured = [
            r
            for r in journal.records[record_start:]
            if r["kind"] in ("native_observation", "native_exchange")
        ]
        assert captured
        for retained in captured:
            payload = retained["payload"]
            assert bytes.fromhex((payload.get("exchange") or payload)["response_hex"]) in originals
        record_property(
            "resource_binding",
            json.dumps(
                {
                    "action": order.action,
                    **counts,
                    "substituted": substituted,
                    "routes": [r.route for r in calls],
                    "invites": len(invitations),
                    "applied_invites": len(share["pending"]),
                    "retained_originals": len(captured),
                },
                sort_keys=True,
            ),
        )
    finally:
        journal.close()
    if substituted:
        resumed = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
        try:
            before = len(service.calls)
            with pytest.raises(ValueError):
                resumed.next()
            assert len(service.calls) == before
        finally:
            resumed.close()


def test_installed_verified_mount_remains_bound_before_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    root, context = installed(tmp_path, complete=True)
    service = FakeHTTP(None)
    originals: list[bytes] = []

    def response(exchange: Exchange):
        originals.append(bytes.fromhex(exchange.response_hex))
        return Reply(exchange)

    connect_service(monkeypatch, service, response_factory=response)
    counts = count_native(monkeypatch)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        for _ in range(1200):
            order = journal.next()
            mounted_access = (
                order.action == "list"
                and order.actor.actor != "coordinator"
                and order.actor_locator != order.logical_path
            )
            if mounted_access:
                break
            outcome = (
                journal.run_component()
                if order.action == "control"
                else setup_transport.capture_once(journal)
            )
            assert outcome.result in ("PASS", "PENDING")
        else:
            pytest.fail("lawful schedule did not reach mounted access")
        assert order.expected == "ALLOW"
        share = next(
            s
            for s in service.shares.values()
            if order.expected_account_id in s["mounts"]
            and (order.logical_path == s["path"] or order.logical_path.startswith(s["path"] + "/"))
        )
        share["mounts"][order.expected_account_id] = "/synthetic-moved-mount"
        start = len(service.calls)
        record_start = len(journal.records)
        counts.update(resolver=0, factory=0)
        result = None
        with suppress(ValueError):
            result = setup_transport.capture_once(journal)
        calls = service.calls[start:]
        captured = [
            r
            for r in journal.records[record_start:]
            if r["kind"] in ("native_observation", "native_exchange")
        ]
        for retained in captured:
            payload = retained["payload"]
            assert bytes.fromhex((payload.get("exchange") or payload)["response_hex"]) in originals
        record_property(
            "mount_binding",
            json.dumps(
                {
                    "action": order.action,
                    **counts,
                    "retained_originals": len(captured),
                    "target_sends": sum(r == order.request for r in calls),
                    "route": order.request.route,
                    "routes": [r.route for r in calls],
                    "result": result.result if result else "UNKNOWN",
                },
                sort_keys=True,
            ),
        )
        assert not any(r.route == order.request.route for r in calls)
        assert result is None
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        before = len(service.calls)
        with pytest.raises(ValueError):
            resumed.next()
        assert len(service.calls) == before
    finally:
        resumed.close()


def test_installed_cleanup_prerequisite_deadline_under_valid_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    # One full lawful prefix also checks the changed share/mount preflights across
    # all 108 accesses. No journal state, ownership or accepted result is seeded.
    rig = CleanupRun(tmp_path, monkeypatch)
    try:
        checks = [
            r for r in rig.journal.records if r["kind"] == "outcome" and r["order"].get("check_id")
        ]
        assert {r["order"]["check_id"] for r in checks} == {
            r.check_id for r in ACCESS_POLICY_V2.acl_expectations
        }
        controls = [
            r
            for r in rig.journal.records
            if r["kind"] == "outcome" and r["order"]["action"] == "control"
        ]
        assert {r["order"]["control_id"] for r in controls} == {
            c.control_id for c in ACCESS_POLICY_V2.application_controls
        }
        assert all(r["payload"]["reason"] == "COMPONENT/OFFLINE only" for r in controls)
        # Metadata/read are newer than the applicable root prerequisite, and are
        # still fresh at rejection. This does not pretend to isolate an unreachable
        # metadata-only stale branch under the common freshness duration.
        rig.clock += timedelta(seconds=10)
        rig.advance("cleanup_read")
        metadata_at = rig.clock
        rig.clock += timedelta(seconds=10)
        rig.advance("cleanup")
        read_at = rig.clock
        rig.arm()
        order = rig.journal.next()
        grant = SetupGrantV2.model_validate_json(rig.grant_raw)
        rig.clock = order.dispatch_not_after + timedelta(seconds=1)
        assert grant.not_before <= rig.clock < grant.not_after
        assert 0 < (rig.clock - metadata_at).total_seconds() < grant.freshness_seconds
        assert 0 < (rig.clock - read_at).total_seconds() < grant.freshness_seconds
        assert rig.context.check(rig.root / "run", rig.root / "checkpoint") == grant
        stored = stored_bytes(rig.root)
        before_objects = dict(rig.service.objects)
        before_contents = dict(rig.service.contents)
        with pytest.raises(ValueError):
            setup_transport.capture_once(rig.journal)
        assert rig.counts == {
            "resolver": 0,
            "factory": 0,
            "send": 0,
            "observations": 0,
            "delete_send": 0,
        }
        assert rig.service.objects == before_objects
        assert rig.service.contents == before_contents
        assert [r["kind"] for r in rig.journal.records[rig.record_start :]] == ["intent"]
        assert stored_bytes(rig.root) == stored
        record_property(
            "cleanup_freshness",
            json.dumps(
                {
                    **rig.counts,
                    "action": order.action,
                    "deadline": order.dispatch_not_after.isoformat(),
                    "now": rig.clock.isoformat(),
                    "grant_end": grant.not_after.isoformat(),
                    "metadata_at": metadata_at.isoformat(),
                    "read_at": read_at.isoformat(),
                    "new_originals": 0,
                    "result": "UNKNOWN_UNMATCHED_INTENT",
                    "checks": len(checks),
                    "controls": len(controls),
                },
                sort_keys=True,
            ),
        )
    finally:
        rig.journal.close()
    resumed = EvidenceJournal(rig.root / "run", rig.root / "checkpoint", rig.context, create=False)
    try:
        before = dict(rig.counts)
        with pytest.raises(ValueError):
            resumed.next()
        with pytest.raises(ValueError):
            setup_transport.capture_once(resumed)
        assert rig.counts == before
        assert rig.service.objects == before_objects
        assert rig.service.contents == before_contents
        assert stored_bytes(rig.root) == stored
    finally:
        resumed.close()


def test_installed_create_post_observation_disagreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    root, context = installed(tmp_path, complete=True)
    service = FakeHTTP(None)
    armed = False
    originals: list[bytes] = []

    def response(exchange: Exchange):
        raw = bytes.fromhex(exchange.response_hex)
        originals.append(raw)
        if armed and exchange.request.route == "files/create_folder_v2":
            parent = str(PurePosixPath(json.loads(raw)["metadata"]["path_display"]).parent)
            obj = service.objects[parent]
            service.objects[parent] = obj.model_copy(update={"id": obj.id + "-replaced"})
        return Reply(exchange)

    connect_service(monkeypatch, service, response_factory=response)
    counts = count_native(monkeypatch)
    journal = EvidenceJournal(root / "run", root / "checkpoint", context, create=True)
    try:
        advance_to(journal, "create")
        assert setup_transport.capture_once(journal).result == "PASS"
        order = advance_to(journal, "create")
        assert order.before
        start = len(service.calls)
        record_start = len(journal.records)
        counts.update(resolver=0, factory=0)
        armed = True
        result = setup_transport.capture_once(journal)
        assert result.result == "FAIL" and result.reconciliation_required
        assert order.logical_path in service.objects  # already applied, not zero dispatch
        calls = service.calls[start:]
        assert sum(r == order.request for r in calls) == 1
        captured = [
            r
            for r in journal.records[record_start:]
            if r["kind"] in ("native_observation", "native_exchange")
        ]
        for retained in captured:
            payload = retained["payload"]
            assert bytes.fromhex((payload.get("exchange") or payload)["response_hex"]) in originals
        record_property(
            "post_observation",
            json.dumps(
                {
                    **counts,
                    "action": order.action,
                    "result": result.result,
                    "target_sends": 1,
                    "applied_creates": 1,
                    "retained_originals": len(captured),
                    "routes": [r.route for r in calls],
                },
                sort_keys=True,
            ),
        )
        with pytest.raises(ValueError):
            journal.next()
        assert len(service.calls) == start + len(calls)
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", context, create=False)
    try:
        before = len(service.calls)
        with pytest.raises(ValueError):
            resumed.next()
        assert len(service.calls) == before
    finally:
        resumed.close()
