"""Offline collector uses real codecs/capture/checkpoint and publication primitives."""

from pathlib import Path, PurePosixPath

import pytest

from peru_conflicts.execution.setup_dropbox import RealWorkOrder
from peru_conflicts.execution.setup_evidence import EvidenceJournal, application_control
from peru_conflicts.execution.setup_offline import FakeHTTP


def drive_until(journal: EvidenceJournal, provider: FakeHTTP, action: str) -> RealWorkOrder:
    for _ in range(600):
        order = journal.next()
        if order.action == action:
            return order
        result = (
            journal.run_component()
            if order.action == "control"
            else journal.import_capture(provider.execute(order))
        )
        assert result.result in ("PASS", "PENDING")
    raise AssertionError("bounded fixture did not reach the requested operation")


def test_component_publication_is_not_live_lock_authority(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-components"
    root.mkdir()
    for actor in ("A", "B"):
        receipt = application_control(root, f"APP-ACCEPTED-BYTES-{actor}")
        assert receipt.level == "COMPONENT"
        assert receipt.original_sha256 == receipt.preserved_sha256
        assert receipt.replacement == "FileExistsError"
        assert receipt.live_path_coverage == "NOT_ESTABLISHED"


def test_offline_path_uses_checkpoint_and_exact_coverage(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import demonstrate

    result = demonstrate(tmp_path / "m2-readiness-success")
    assert result["label"] == "OFFLINE_SYNTHETIC"
    assert result["complete"] is True
    assert result["checks"] == 108
    assert result["controls"] == 2
    assert result["live_path_coverage"] == "NOT_ESTABLISHED"
    assert result["cleanup_outstanding"] == 0
    assert result["reconciliation_required"] == 0
    assert result["recovered_pending_share"] is True
    assert result["share_mutations"] == 4
    assert result["fake_directory_count"] == 30
    assert result["fake_leaf_share_count"] == 4


@pytest.mark.parametrize("fault", ["contradiction", "wrong_session", "revision_drift", "unknown"])
def test_offline_stopping_cases(tmp_path: Path, fault: str) -> None:
    from peru_conflicts.execution.setup_offline import demonstrate

    result = demonstrate(tmp_path / "m2-readiness-stopping", fault=fault)
    assert result["complete"] is False
    assert result["fault_applied"] is True


def test_raw_authority_digest_cannot_open_a_journal(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal

    root = tmp_path / "m2-readiness-injection"
    root.mkdir()
    (root / "run").mkdir()
    (root / "checkpoint").mkdir()
    with pytest.raises(ValueError, match="admission"):
        EvidenceJournal(root / "run", root / "checkpoint", "0" * 64, create=True)
    assert list((root / "run").iterdir()) == []
    assert list((root / "checkpoint").iterdir()) == []


def admitted_journal(tmp_path: Path):
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import admit_fixture

    root = tmp_path / "m2-readiness-admitted"
    root.mkdir()
    for name in ("run", "checkpoint", "components"):
        (root / name).mkdir()
    permit = admit_fixture(root)
    return root, permit, EvidenceJournal(root / "run", root / "checkpoint", permit, create=True)


@pytest.mark.parametrize("forged", [None, {}, "0" * 64, object()])
def test_unregistered_admission_has_zero_store_effects(tmp_path: Path, forged: object) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal

    root = tmp_path / "m2-readiness-no-admission"
    root.mkdir()
    for name in ("run", "checkpoint"):
        (root / name).mkdir()
    with pytest.raises(ValueError, match="admission"):
        EvidenceJournal(root / "run", root / "checkpoint", forged, create=True)
    assert not list((root / "run").iterdir())
    assert not list((root / "checkpoint").iterdir())


def test_admission_owns_next_order_and_pending_recovery(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import NOW

    root, permit, journal = admitted_journal(tmp_path)
    try:
        order = journal.next()
        assert order.action == "root"
        assert order.issued_at == NOW
        assert journal.pending == order
        before = (root / "run" / "000001.json").read_bytes()
        exposed = journal.records
        exposed[0]["order"]["actor"]["session_ref"] = "substitute"
        assert journal.pending == order
        with pytest.raises(ValueError, match="UNKNOWN"):
            journal.next()
        assert (root / "run" / "000001.json").read_bytes() == before
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
    try:
        assert resumed.pending == order
        with pytest.raises(ValueError, match="UNKNOWN"):
            resumed.next()
    finally:
        resumed.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_ref", "another-run"),
        ("sequence", 2),
        ("logical_path", "/unapproved"),
        ("namespace", "another-namespace"),
        ("action", "cleanup"),
    ],
)
def test_substituted_order_cannot_release(tmp_path: Path, field: str, value: object) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal

    root, permit, journal = admitted_journal(tmp_path)
    try:
        proposed = journal.preview()
        with pytest.raises(ValueError, match="admitted next order"):
            journal.release(proposed.model_copy(update={field: value}))
        assert journal.records == []
        assert journal.next() == proposed
    finally:
        journal.close()
    # The rejected substitution did not corrupt the durable chain.
    EvidenceJournal(root / "run", root / "checkpoint", permit, create=False).close()


def test_admission_cannot_move_to_another_store(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal

    root, permit, journal = admitted_journal(tmp_path)
    journal.close()
    other = root / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="admission"):
        EvidenceJournal(other, root / "checkpoint", permit, create=True)
    assert not list(other.iterdir())


def test_revocation_and_expiry_checked_after_open(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import END, advance_fixture_clock, revoke_fixture

    _, permit, journal = admitted_journal(tmp_path)
    try:
        advance_fixture_clock(permit, END)
        with pytest.raises(ValueError, match="validity"):
            journal.next()
        assert journal.records == []
        revoke_fixture(permit)
        with pytest.raises(ValueError, match="admission"):
            journal.next()
    finally:
        journal.close()


def test_only_released_request_can_dispatch_once(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import FakeHTTP

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        preview = journal.preview()
        with pytest.raises(ValueError, match="not released"):
            provider.execute(preview)
        assert provider.dispatches == 0
        released = journal.next()
        raw = provider.execute(released)
        with pytest.raises(ValueError, match="already dispatched"):
            provider.execute(released)
        assert provider.dispatches == 1
        assert journal.import_capture(raw).result == "PASS"
        second = journal.next()
        assert second.action == "root" and second.sequence == 2
        assert second.actor.actor == "annotator-a"
    finally:
        journal.close()


def test_actor_request_and_authority_substitution_rejected(tmp_path: Path) -> None:
    _, _, journal = admitted_journal(tmp_path)
    try:
        original = journal.preview()
        for changed in (
            original.model_copy(
                update={"actor": original.actor.model_copy(update={"session_ref": "another"})}
            ),
            original.model_copy(
                update={"request": original.request.model_copy(update={"route": "files/delete_v2"})}
            ),
            original.model_copy(update={"authority_sha256": "0" * 64}),
        ):
            with pytest.raises(ValueError, match="admitted next order"):
                journal.release(changed)
        assert journal.records == []
    finally:
        journal.close()


@pytest.mark.parametrize("fault", ["malformed_capture", "duplicate_keys"])
def test_witnessed_malformed_original_is_retained_before_parsing(
    tmp_path: Path, fault: str
) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import FakeHTTP

    root, permit, journal = admitted_journal(tmp_path)
    try:
        raw = FakeHTTP(permit).execute(journal.next(), fault=fault)
        result = journal.import_capture(raw)
        assert result.result == "INCONCLUSIVE"
        assert bytes.fromhex(journal.records[1]["payload"]["original_hex"]) == raw
        assert journal.stopped
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
    try:
        assert resumed.stopped
        assert bytes.fromhex(resumed.records[1]["payload"]["original_hex"]) == raw
        with pytest.raises(ValueError, match="stopped"):
            resumed.next()
    finally:
        resumed.close()


def test_unwitnessed_or_substituted_original_cannot_write(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import FakeHTTP

    _, permit, journal = admitted_journal(tmp_path)
    try:
        order = journal.next()
        with pytest.raises(ValueError, match="witness"):
            journal.import_capture(b"{}")
        raw = FakeHTTP(permit).execute(order)
        with pytest.raises(ValueError, match="witness"):
            journal.import_capture(raw + b" ")
        assert len(journal.records) == 1
        assert journal.pending == order
    finally:
        journal.close()


def test_interruption_after_retention_preserves_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.execution import setup_evidence
    from peru_conflicts.execution.setup_offline import FakeHTTP

    root, permit, journal = admitted_journal(tmp_path)

    def crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic crash after retention")

    try:
        raw = FakeHTTP(permit).execute(journal.next())
        monkeypatch.setattr(setup_evidence, "classify_capture", crash)
        with pytest.raises(RuntimeError, match="after retention"):
            journal.import_capture(raw)
        assert bytes.fromhex(journal.records[-1]["payload"]["original_hex"]) == raw
    finally:
        journal.close()
    resumed = setup_evidence.EvidenceJournal(
        root / "run", root / "checkpoint", permit, create=False
    )
    try:
        assert resumed.pending is not None
        with pytest.raises(ValueError, match="UNKNOWN"):
            resumed.next()
        with pytest.raises(ValueError, match="replayed"):
            resumed.import_capture(raw)
    finally:
        resumed.close()


@pytest.mark.parametrize(
    "action,body",
    [
        (
            "root",
            {
                "account_id": "dbid:unrelated",
                "root_info": {
                    "root_namespace_id": "offline-home",
                    "home_namespace_id": "offline-home",
                },
            },
        ),
        (
            "membership",
            {
                "users": [
                    {
                        "user": {"account_id": "dbid:intruder"},
                        "access_type": {".tag": "editor"},
                        "is_inherited": False,
                    }
                ],
                "groups": [],
                "invitees": [],
            },
        ),
        ("links", {"links": [{"url": "https://example.invalid/SYNTHETIC"}], "has_more": False}),
        ("mount", {}),
    ],
)
def test_reported_false_passes_are_rejected(
    tmp_path: Path, action: str, body: dict[str, object]
) -> None:
    from peru_conflicts.execution.setup_bridge import digest
    from peru_conflicts.execution.setup_dropbox import Exchange, OriginalCapture, classify_capture
    from peru_conflicts.execution.setup_offline import NOW
    from peru_conflicts.hashing import canonical_json_bytes

    _, _, journal = admitted_journal(tmp_path)
    try:
        # Pure classifier reproduction: no arbitrary order is released or dispatched.
        order = journal.preview().model_copy(
            update={
                "action": action,
                "expected_account_id": "dbid:offline-coordinator",
                "expected_member_roles": {"dbid:offline-coordinator": "owner"},
                "shared_folder_id": "offline-share",
                "link_coverage": "offline_complete",
            }
        )
        capture = OriginalCapture(
            order_sha256=digest(order),
            actor_session_ref=order.actor.session_ref,
            namespace=order.namespace,
            started=NOW,
            ended=NOW,
            before_hex=(),
            after_hex=(),
            exchanges=(
                Exchange(
                    request=order.request,
                    status=200,
                    provider_request_id="offline",
                    response_hex=canonical_json_bytes(body).hex(),
                ),
            ),
        )
        assert classify_capture(order, capture).result != "PASS"
    finally:
        journal.close()


def test_fake_account_state_is_not_derived_from_expected_order(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import FakeHTTP

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = journal.next()
        provider.accounts[order.actor.session_ref] = ("dbid:unexpected", order.namespace)
        result = journal.import_capture(provider.execute(order))
        assert result.result == "INCONCLUSIVE"
        assert journal.stopped
        assert provider.dispatches == 1
    finally:
        journal.close()


def test_closed_or_resumed_intent_cannot_dispatch(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import FakeHTTP

    root, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    order = journal.next()
    journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
    try:
        with pytest.raises(ValueError, match="not released"):
            provider.execute(order)
        assert provider.dispatches == 0
        assert resumed.pending == order
    finally:
        resumed.close()


def test_acknowledged_share_resumes_only_job_observation(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_evidence import EvidenceJournal
    from peru_conflicts.execution.setup_offline import FakeHTTP

    root, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    provider.async_sharing = True
    try:
        while True:
            order = journal.next()
            result = journal.import_capture(provider.execute(order))
            if order.action == "share":
                assert result.result == "PENDING"
                assert not journal.stopped
                break
            assert result.result == "PASS"
    finally:
        journal.close()
    resumed = EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)
    try:
        status = resumed.next()
        assert status.action == "share_status"
        assert resumed.import_capture(provider.execute(status)).result == "PASS"
        assert resumed.next().action == "invite"
        assert sum(r.route == "sharing/share_folder" for r in provider.calls) == 1
    finally:
        resumed.close()


def test_mount_requires_followup_identity_at_observed_actor_locator(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_offline import FakeHTTP

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        while True:
            order = journal.next()
            result = journal.import_capture(provider.execute(order))
            assert result.result == "PASS"
            if order.action == "mount":
                break
        verification = journal.next()
        assert verification.action == "mount_verify"
        assert verification.actor.actor == order.actor.actor
        assert verification.actor_locator != verification.logical_path
        assert journal.import_capture(provider.execute(verification)).result == "PASS"
    finally:
        journal.close()


@pytest.mark.parametrize("change", ["revision", "identity", "location", "folder", "bytes"])
def test_cleanup_preflight_drift_releases_zero_deletes(tmp_path: Path, change: str) -> None:
    from peru_conflicts.execution.setup_dropbox import FileObservation, FolderObservation

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = drive_until(
            journal, provider, "cleanup_read" if change == "bytes" else "cleanup_metadata"
        )
        owned = provider.objects[order.logical_path]
        assert isinstance(owned, FileObservation)
        if change == "revision":
            provider.objects[order.logical_path] = owned.model_copy(
                update={"rev": "same-bytes-new-revision"}
            )
        elif change == "identity":
            provider.objects[order.logical_path] = owned.model_copy(update={"id": "id:replacement"})
            provider.contents["id:replacement"] = provider.contents[owned.id]
        elif change == "location":
            del provider.objects[order.logical_path]
            provider.objects["/outside/probe"] = owned.model_copy(
                update={"path_display": "/outside/probe", "path_lower": "/outside/probe"}
            )
        elif change == "folder":
            provider.objects[order.logical_path] = FolderObservation(
                id=owned.id,
                name=owned.name,
                path_display=order.logical_path,
                path_lower=order.logical_path.lower(),
            )
        else:
            provider.contents[owned.id] = b"different OFFLINE bytes"
        assert journal.import_capture(provider.execute(order)).result != "PASS"
        with pytest.raises(ValueError, match="stopped"):
            journal.next()
        assert not any(r.route == "files/delete_v2" for r in provider.calls)
    finally:
        journal.close()


def test_cleanup_stale_observation_blocks_before_release(tmp_path: Path) -> None:
    from datetime import timedelta

    from peru_conflicts.execution.setup_offline import NOW, advance_fixture_clock

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = drive_until(journal, provider, "cleanup_read")
        assert journal.import_capture(provider.execute(order)).result == "PASS"
        advance_fixture_clock(permit, NOW + timedelta(seconds=61))
        with pytest.raises(ValueError, match=r"fresh|stale"):
            journal.next()
        assert not any(r.route == "files/delete_v2" for r in provider.calls)
    finally:
        journal.close()


def test_provider_revision_precondition_stops_post_observation_race(tmp_path: Path) -> None:
    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = drive_until(journal, provider, "cleanup")
        current = provider.objects[order.logical_path]
        provider.objects[order.logical_path] = current.model_copy(
            update={"rev": "changed-after-read"}
        )
        assert journal.import_capture(provider.execute(order)).result != "PASS"
        assert order.logical_path in provider.objects
        assert sum(r.route == "files/delete_v2" for r in provider.calls) == 1
        with pytest.raises(ValueError, match="already dispatched"):
            provider.execute(order)
    finally:
        journal.close()


def test_missing_source_capability_blocks_active_release(tmp_path: Path) -> None:
    from peru_conflicts.execution import setup_offline

    _, permit, journal = admitted_journal(tmp_path)
    try:
        # Fault in the separate TEST authority source, not an uploaded work-order flag.
        setup_offline._CAPABILITIES[permit].pop("conditional_delete_identity_version")  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(ValueError, match="capability"):
            journal.next()
        assert journal.records == []
    finally:
        journal.close()


def test_membership_capture_contains_all_actual_pages(tmp_path: Path) -> None:
    from peru_conflicts.execution.setup_dropbox import OriginalCapture

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    provider.page_size = 1
    try:
        order = drive_until(journal, provider, "membership")
        assert journal.import_capture(provider.execute(order)).result == "PASS"
        raw = bytes.fromhex(journal.records[-2]["payload"]["original_hex"])
        capture = OriginalCapture.model_validate_json(raw)
        assert len(capture.exchanges) == 2
        assert capture.exchanges[1].request.route == "sharing/list_folder_members/continue"
    finally:
        journal.close()


def test_incomplete_member_pagination_cannot_pass(tmp_path: Path) -> None:
    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    provider.page_size = 1
    try:
        order = drive_until(journal, provider, "membership")
        assert (
            journal.import_capture(provider.execute(order, fault="truncate_pages")).result
            == "INCONCLUSIVE"
        )
    finally:
        journal.close()


@pytest.mark.parametrize("encoded", ["plain", "hex", "escaped_hex", "header"])
def test_even_witnessed_credential_fields_are_rejected_before_retention(
    tmp_path: Path, encoded: str
) -> None:
    from peru_conflicts.execution import setup_offline
    from peru_conflicts.execution.references import sha256
    from peru_conflicts.execution.setup_bridge import digest
    from peru_conflicts.hashing import canonical_json_bytes

    _, permit, journal = admitted_journal(tmp_path)
    try:
        order = journal.next()
        marker = b'{"Authorization":"OFFLINE_MARKER_NOT_A_CREDENTIAL"}'
        raw = marker
        if encoded in ("hex", "escaped_hex"):
            raw = canonical_json_bytes({"response_hex": marker.hex()})
        if encoded == "escaped_hex":
            raw = raw.replace(b"7b", b"\\u0037b", 1)
        if encoded == "header":
            raw = canonical_json_bytes({"result_header": marker.decode()})
        # Separate TEST witness channel. The imported document asserts no authentication.
        setup_offline._WITNESSES[permit, digest(order)] = sha256(raw)  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(ValueError, match="credential"):
            journal.import_capture(raw)
        assert len(journal.records) == 1
    finally:
        journal.close()


@pytest.mark.parametrize("state", ["progress", "failed", "unknown"])
def test_async_status_is_bounded_without_repeating_mutation(tmp_path: Path, state: str) -> None:
    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    provider.async_sharing = True
    provider.pending_polls = 10 if state == "progress" else 0
    try:
        order = drive_until(journal, provider, "share")
        assert journal.import_capture(provider.execute(order)).result == "PENDING"
        job = next(iter(provider.jobs))
        if state == "failed":
            provider.failed_jobs.add(job)
        elif state == "unknown":
            del provider.jobs[job]
        for _ in range(4):
            try:
                order = journal.next()
            except ValueError:
                break
            assert order.action == "share_status"
            result = journal.import_capture(provider.execute(order))
            if state != "progress":
                assert result.result not in ("PASS", "PENDING")
        else:
            pytest.fail("unbounded pending status release")
        assert sum(call.route == "sharing/share_folder" for call in provider.calls) == 1
    finally:
        journal.close()


def test_actor_handoff_reobserves_account_before_mount(tmp_path: Path) -> None:
    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        invitation = drive_until(journal, provider, "invite")
        assert journal.import_capture(provider.execute(invitation)).result == "PASS"
        session = "fixture-session-annotator-a"
        provider.accounts[session] = ("dbid:wrong-account", "offline-a-home")
        order = journal.next()
        assert order.action == "root"
        assert order.actor.actor == "annotator-a"
        assert journal.import_capture(provider.execute(order)).result == "INCONCLUSIVE"
        assert not any(call.route == "sharing/mount_folder" for call in provider.calls)
    finally:
        journal.close()


def test_released_request_expires_before_dispatch(tmp_path: Path) -> None:
    from datetime import timedelta

    from peru_conflicts.execution.setup_offline import NOW, advance_fixture_clock

    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = journal.next()
        advance_fixture_clock(permit, NOW + timedelta(seconds=61))
        with pytest.raises(ValueError, match=r"expired|fresh"):
            provider.execute(order)
        assert provider.calls == []
        assert journal.pending == order
    finally:
        journal.close()


def test_ancestor_link_is_observed_by_leaf_privacy_check(tmp_path: Path) -> None:
    _, permit, journal = admitted_journal(tmp_path)
    provider = FakeHTTP(permit)
    try:
        order = drive_until(journal, provider, "links")
        ancestor = str(PurePosixPath(order.logical_path).parent)
        provider.links[ancestor] = [{"url": "https://example.invalid/OFFLINE"}]
        assert journal.import_capture(provider.execute(order)).result == "FAIL"
        assert journal.stopped
    finally:
        journal.close()


@pytest.mark.parametrize("damage", ["missing", "mismatched"])
def test_checkpoint_damage_cannot_reopen_active_run(tmp_path: Path, damage: str) -> None:
    root, permit, journal = admitted_journal(tmp_path)
    journal.next()
    journal.close()
    checkpoint = root / "checkpoint" / "000001.json"
    # Disposable synthetic fault injection, not a repair of retained evidence.
    if damage == "missing":
        checkpoint.unlink()
    else:
        checkpoint.write_bytes(b"0" * 64)
    with pytest.raises(ValueError, match="checkpoint"):
        EvidenceJournal(root / "run", root / "checkpoint", permit, create=False)


def test_retained_schedule_counts_and_order_are_exact() -> None:
    from collections import Counter

    from peru_conflicts.execution.operational_plan import build_operational_plan, make_candidate
    from peru_conflicts.execution.setup_authority import schedule

    rows = schedule()
    assert rows == build_operational_plan(make_candidate())["checks"]
    assert len({row["check_id"] for row in rows}) == len(rows) == 108
    assert Counter(row["operation"] for row in rows) == {"list": 36, "read": 36, "write": 36}
    assert Counter(row["expected_outcome"] for row in rows) == {"ALLOW": 46, "DENY": 62}
