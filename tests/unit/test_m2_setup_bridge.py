"""Synthetic setup bridge: no provider/account/research operations."""

import importlib
import importlib.util
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest


def bridge():
    name = "peru_conflicts.execution.setup_synthetic"
    assert importlib.util.find_spec(name) is not None, "setup bridge not implemented"
    return importlib.import_module(name)


def test_documented_module_command_uses_canonical_authority_registry() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "peru_conflicts.execution.setup_synthetic"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["success"]["label"] == "SYNTHETIC_ONLY"
    assert output["success"]["checks"] == {"PASS": 108}
    assert output["success"]["remaining_probes"] == 0
    assert output["stopped_collision"]["complete"] is False
    assert len(output["stopped_collision"]["not_run"]) == 108
    assert "no registered real grant" in output["production_rejection"]


def test_synthetic_end_to_end_has_exact_coverage_and_no_live_authority(tmp_path: Path) -> None:
    s = bridge()
    result = s.demonstrate(tmp_path / "m2-readiness-bridge")
    assert result["label"] == "SYNTHETIC_ONLY"
    assert result["checks"] == {"PASS": 108}
    assert result["application_controls"] == 2
    assert result["created_directories"] == 30
    assert result["remaining_probes"] == 0
    assert result["operational_approvals"] == 0


def test_production_rejects_synthetic_injection_before_dispatch(tmp_path: Path) -> None:
    s = bridge()
    with pytest.raises(ValueError, match="no registered real grant"):
        s.production_admission(s.fixture_bytes())
    assert s.REAL_GRANTS == ()


@pytest.mark.parametrize("change", ["scope", "namespace", "candidate", "approval", "extra"])
def test_self_authorized_changes_are_not_trusted(tmp_path: Path, change: str) -> None:
    s = bridge()
    grant = json.loads(s.fixture_bytes())
    key = {
        "scope": "operations",
        "namespace": "namespace",
        "candidate": "candidate_sha256",
        "approval": "approved",
        "extra": "unexpected",
    }[change]
    grant[key] = True if change == "approval" else "substituted"
    with pytest.raises(ValueError):
        s.create_demo(tmp_path / "m2-readiness-bridge", grant_raw=json.dumps(grant).encode())


def test_duplicate_authority_key_rejected(tmp_path: Path) -> None:
    s = bridge()
    raw = s.fixture_bytes().rstrip()[:-1] + b',"approved":true}'
    with pytest.raises(ValueError):
        s.create_demo(tmp_path / "m2-readiness-bridge", grant_raw=raw)


def test_interrupted_order_is_not_reissued_and_matching_evidence_can_resume(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    order = run.next(s.NOW)
    evidence = provider.execute(order)
    with pytest.raises(ValueError, match="pending"):
        run.next(s.NOW)
    resumed = s.resume_demo(run.root)
    with pytest.raises(ValueError, match="pending"):
        resumed.next(s.NOW)
    resumed.submit(evidence, s.NOW)
    with pytest.raises(ValueError):
        resumed.submit(evidence, s.NOW)
    assert resumed.next(s.NOW).sequence == 2


@pytest.mark.parametrize("fault", ["collision", "parent", "namespace", "session", "network"])
def test_deficient_evidence_stops_normal_work(tmp_path: Path, fault: str) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    run.submit(provider.execute(run.next(s.NOW)), s.NOW)
    order = run.next(s.NOW)
    evidence = provider.execute(order, fault=fault)
    run.submit(evidence, s.NOW)
    assert run.summary()["complete"] is False
    with pytest.raises(ValueError, match="stopped"):
        run.next(s.NOW)


def test_unexpected_allow_preserved_and_cannot_be_replaced(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "check" and order.expected == "DENY":
            break
        run.submit(provider.execute(order), s.NOW)
    evidence = provider.execute(order, fault="unexpected_allow")
    run.submit(evidence, s.NOW)
    assert run.summary()["checks"]["FAIL"] == 1
    with pytest.raises(ValueError):
        run.submit(provider.execute(order), s.NOW)
    assert s.resume_demo(run.root).summary()["checks"]["FAIL"] == 1


@pytest.mark.parametrize("fault", ["replacement", "no_conditional", "wrong_owner", "wrong_bytes"])
def test_cleanup_never_removes_unbound_or_unsafe_object(tmp_path: Path, fault: str) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "cleanup":
            break
        run.submit(provider.execute(order), s.NOW)
    evidence = provider.execute(order, fault=fault)
    run.submit(evidence, s.NOW)
    assert order.path in provider.objects
    assert run.summary()["complete"] is False


def test_stale_and_spent_authority_and_tampered_journal_rejected(tmp_path: Path) -> None:
    s = bridge()
    run, _ = s.create_demo(tmp_path / "m2-readiness-bridge")
    with pytest.raises(ValueError):
        run.next(s.NOW.replace(year=2100))
    assert not list(run.root.glob("*.json"))
    with pytest.raises(ValueError):
        s.create_demo(run.root)


def test_manual_done_statement_is_not_provider_evidence(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    ev = provider.execute(run.next(s.NOW))
    forged = ev.model_copy(update={"source_evidence": "done", "source_sha256": s.sha256(b"done")})
    with pytest.raises(ValueError):
        run.submit(forged, s.NOW)
    assert run.summary()["pending"] == "UNKNOWN"


def test_rehashed_out_of_scope_journal_intent_rejected(tmp_path: Path) -> None:
    s = bridge()
    run, _ = s.create_demo(tmp_path / "m2-readiness-bridge")
    run.next(s.NOW)
    first = run.root / "000001.json"
    record = json.loads(first.read_bytes())
    record["order"]["path"] = "/research"
    from peru_conflicts.hashing import canonical_json_bytes

    first.write_bytes(canonical_json_bytes(record) + b"\n")
    with pytest.raises(ValueError):
        s.resume_demo(run.root)


def test_two_application_controls_exercise_no_replace_and_preserved_bytes(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "control":
            break
        run.submit(provider.execute(order), s.NOW)
    ev = provider.execute(order)
    assert ev.application_before_sha256 == s.sha256(b"SYNTHETIC accepted bytes")
    assert ev.application_after_sha256 == ev.application_before_sha256
    assert ev.application_replacement == "conflict"
    assert run.submit(ev, s.NOW) == "PASS"


def test_grant_replay_into_another_evidence_store_rejected(tmp_path: Path) -> None:
    s = bridge()
    run, _ = s.create_demo(tmp_path / "m2-readiness-one")
    with pytest.raises(ValueError):
        s.create_demo(tmp_path / "m2-readiness-two", grant_raw=run.grant.model_dump_json().encode())


def test_revocation_is_checked_before_next_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = bridge()
    run, _ = s.create_demo(tmp_path / "m2-readiness-bridge")
    monkeypatch.setattr(s, "REVOKED_SYNTHETIC_GRANTS", frozenset({run.grant.grant_id}))
    with pytest.raises(ValueError, match="revoked"):
        run.next(s.NOW)


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "incomplete_controls"])
def test_incomplete_or_mutated_coverage_cannot_claim_complete(tmp_path: Path, case: str) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    evidence = None
    while (order := run.next(s.NOW)) is not None:
        evidence = provider.execute(order)
        run.submit(evidence, s.NOW)
    if case == "missing":
        del run.checks[next(iter(run.checks))]
    elif case == "extra":
        run.checks["not-authorized"] = "PASS"
    elif case == "duplicate":
        # A duplicate evidence record must not consume another check ID.
        assert evidence is not None
        with pytest.raises(ValueError):
            run.submit(evidence, s.NOW)
        return
    else:
        run.controls.clear()
    assert not run.summary()["complete"]


def test_stale_observation_and_missing_object_are_inconclusive(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    order = run.next(s.NOW)
    ev = provider.execute(order)
    assert run.submit(ev, s.NOW + timedelta(minutes=6)) == "INCONCLUSIVE"
    assert not run.summary()["complete"]


def test_list_never_creates_probe_and_write_conflict_never_overwrites(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "check" and order.probe_content is not None:
            break
        before = provider.counter
        ev = provider.execute(order)
        if order.action == "check" and order.probe_sha256 is None:
            assert provider.counter == before
        run.submit(ev, s.NOW)
    # Existing unrelated same-byte object is a collision, never an adopted task probe.
    obj = next(o for o in provider.objects.values() if o.kind == "file")
    provider.objects[order.path] = obj.model_copy(
        update={"path": order.path, "owner_run": "synthetic-other"}
    )
    before = provider.objects.copy()
    ev = provider.execute(order)
    assert ev.observation == "conflict"
    assert provider.objects == before
    assert run.submit(ev, s.NOW) != "PASS"


def test_schema_export_has_no_drift() -> None:
    s = bridge()
    from peru_conflicts.execution.setup_bridge import setup_schema_bytes

    assert s.__file__ is not None
    target = Path(s.__file__).resolve().parents[3] / "schemas/execution/setup_bridge_v1.json"
    assert target.read_bytes() == setup_schema_bytes()


def test_interruption_during_outcome_publication_keeps_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = bridge()
    from peru_conflicts.execution import setup_bridge as b

    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    order = run.next(s.NOW)
    ev = provider.execute(order)

    def fail(*args: object) -> None:
        raise OSError("synthetic interrupted capture")

    with monkeypatch.context() as patch:
        patch.setattr(b, "publish_new", fail)
        with pytest.raises(OSError):
            run.submit(ev, s.NOW)
    resumed = s.resume_demo(run.root)
    assert resumed.summary()["pending"] == "UNKNOWN"
    assert not resumed.summary()["complete"]
    resumed.submit(ev, s.NOW)
    assert resumed.next(s.NOW).sequence == 2


@pytest.mark.parametrize("fault", ["client", "missing", "not_found"])
def test_missing_or_error_is_not_denial_pass(tmp_path: Path, fault: str) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "check":
            break
        run.submit(provider.execute(order), s.NOW)
    ev = provider.execute(order, fault="network" if fault == "client" else "not_found")
    assert run.submit(ev, s.NOW) == "INCONCLUSIVE"


@pytest.mark.parametrize("path", ["../x", "/a/../x", "//x", "/a\\b", "/a:b", "/a//b"])
def test_unsafe_snapshot_paths_are_rejected(path: str) -> None:
    from peru_conflicts.execution.setup_bridge import Snapshot

    with pytest.raises(ValueError):
        Snapshot(
            path=path,
            resource_id="synthetic-id",
            version="synthetic-v1",
            namespace="synthetic-home",
            parent_id=None,
            kind="directory",
        )


def test_component_substitution_rejected_before_any_order(tmp_path: Path) -> None:
    s = bridge()
    from peru_conflicts.execution.setup_bridge import parse_authorization

    raw, parts = s.proposal()
    parts["topology.json"] += b" "
    with pytest.raises(ValueError):
        parse_authorization(s.fixture_bytes(), raw, parts)


def test_v3_request_byte_pin_and_real_decisions_preserved() -> None:
    s = bridge()
    raw, _ = s.proposal()
    assert s.sha256(raw) == "184ec60975b9ffe8c1e74b4b9f1bd431aa9738189e0ba093b3f3a76ab47ec0c0"
    req = json.loads(raw)
    assert req["private_bindings"] == dict.fromkeys(
        (
            "external_root_identity",
            "provider_namespace",
            "account_role_mapping",
            "group_memberships",
            "provider_denial_rule",
            "private_receipt_destination",
        )
    )
    assert req["current_authorization"] is False
    assert req["execution_eligible"] is False
    assert req["decision_14_eligible"] is False
    assert len(s.make_candidate().decisions) == 7
    assert all(
        d.status == "UNRESOLVED" and d.response is None for d in s.make_candidate().decisions
    )


def test_forbidden_successful_write_remains_accounted_after_stop_and_resume(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-bridge")
    while True:
        order = run.next(s.NOW)
        if order.action == "check" and order.expected == "DENY" and order.probe_content:
            break
        run.submit(provider.execute(order), s.NOW)
    outstanding = run.summary()["cleanup_outstanding"]
    ev = provider.execute(order, fault="unexpected_allow")
    assert run.submit(ev, s.NOW) == "FAIL"
    assert run.summary()["cleanup_outstanding"] == outstanding + 1
    assert run.owned[order.path] == ev.after
    resumed = s.resume_demo(run.root)
    assert resumed.owned[order.path] == ev.after
    assert resumed.summary()["checks"]["FAIL"] == 1
    with pytest.raises(ValueError, match="stopped"):
        resumed.next(s.NOW)


def test_denied_write_with_created_file_cannot_complete_or_authorize_cleanup(
    tmp_path: Path,
) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-contradictory")
    while True:
        order = run.next(s.NOW)
        if order.action == "check" and order.expected == "DENY" and order.probe_content:
            break
        run.submit(provider.execute(order), s.NOW)
    ev = provider.execute(order, fault="unexpected_allow")
    payload = ev.model_dump(mode="json", exclude={"source_evidence", "source_sha256"})
    payload["observation"] = "authorization_denied"
    source = json.dumps(payload)
    payload.update(source_evidence=source, source_sha256=s.sha256(source.encode()))
    contradictory = s.OperationEvidence.model_validate_json(json.dumps(payload))
    result = run.submit(contradictory, s.NOW)
    if result == "PASS":
        while (following := run.next(s.NOW)) is not None:
            run.submit(provider.execute(following), s.NOW)
    resumed = s.resume_demo(run.root)
    assert result == "FAIL", (run.summary(), resumed.summary(), provider.objects[order.path])
    for state in (run, resumed):
        assert not state.summary()["complete"]
        assert state.summary()["reconciliation_required"] == 1
        assert state.reconciliation[order.path] == ev.after
        assert order.path not in state.owned
        assert state.records[-1].evidence == contradictory
        with pytest.raises(ValueError, match="stopped"):
            state.next(s.NOW)
    assert provider.objects[order.path] == ev.after


def test_outward_work_order_mapping_cannot_change_durable_intent(tmp_path: Path) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-detached")
    order = run.next(s.NOW)
    original = order.model_copy(deep=True)
    first = run.root / "000001.json"
    raw = first.read_bytes()
    intent_hash = s.digest(run.records[0])
    order.capability_evidence.clear()
    ev = provider.execute(order)
    with pytest.raises(ValueError, match="substituted evidence"):
        run.submit(ev, s.NOW)
    assert s.digest(run.records[0]) == intent_hash
    assert first.read_bytes() == raw
    assert len(run.grant.capabilities) == 6
    resumed = s.resume_demo(run.root)
    assert resumed.summary()["pending"] == "UNKNOWN"
    with pytest.raises(ValueError, match="pending"):
        resumed.next(s.NOW)
    # Reconcile evidence for the original order; never redispatch an uncertain action.
    payload = ev.model_dump(mode="json", exclude={"source_evidence", "source_sha256"})
    payload["order_sha256"] = s.digest(original)
    source = json.dumps(payload)
    payload.update(source_evidence=source, source_sha256=s.sha256(source.encode()))
    original_evidence = s.OperationEvidence.model_validate_json(json.dumps(payload))
    assert resumed.submit(original_evidence, s.NOW) == "PASS"
    original_evidence.capability_evidence.clear()
    assert s.resume_demo(run.root).next(s.NOW).sequence == 2


@pytest.mark.parametrize("operation", ["read", "list"])
def test_denied_access_with_replaced_target_stops_for_reconciliation(
    tmp_path: Path, operation: str
) -> None:
    s = bridge()
    run, provider = s.create_demo(tmp_path / "m2-readiness-denied-replaced")
    while True:
        order = run.next(s.NOW)
        if (
            order.action == "check"
            and order.expected == "DENY"
            and order.probe_content is None
            and bool(order.probe_sha256) == (operation == "read")
        ):
            break
        run.submit(provider.execute(order), s.NOW)
    ev = provider.execute(order)
    assert ev.observation == "authorization_denied"
    payload = ev.model_dump(mode="json", exclude={"source_evidence", "source_sha256"})
    payload["after"]["resource_id"] = "synthetic-replacement"
    source = json.dumps(payload)
    payload.update(source_evidence=source, source_sha256=s.sha256(source.encode()))
    contradictory = s.OperationEvidence.model_validate_json(json.dumps(payload))
    assert run.submit(contradictory, s.NOW) == "FAIL"
    resumed = s.resume_demo(run.root)
    assert resumed.summary()["reconciliation_required"] == 1
    assert not resumed.summary()["complete"]
    with pytest.raises(ValueError, match="stopped"):
        resumed.next(s.NOW)
