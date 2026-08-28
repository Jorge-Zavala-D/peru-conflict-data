from __future__ import annotations

from copy import copy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.models import NetworkAuthorizationArtifact
from peru_conflicts.acquisition.plan import LoadedPilotPlan, load_reviewed_pilot_plan

V2_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml")
V2_SHA256 = "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"


def _loaded() -> LoadedPilotPlan:
    return load_reviewed_pilot_plan(V2_PATH, required_sha256=V2_SHA256)


def _authorization(loaded: LoadedPilotPlan) -> NetworkAuthorizationArtifact:
    return NetworkAuthorizationArtifact(
        schema_version="0.1.0",
        authorization_id="owner-reviewed-m1-03b-test-artifact",
        authorization_status="authorized",
        scope="m1_03b_reports_260_269_network",
        plan_id=loaded.plan.plan_id,
        plan_file_sha256=loaded.file_sha256,
        baseline_git_commit=loaded.plan.baseline_receipt_git_commit,
        approved_by="research-owner-test-fixture",
        approved_at=datetime(2026, 8, 28, tzinfo=UTC),
    )


def test_missing_authorization_fails_before_transport_factory() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationRequired,
        require_network_authorization,
    )

    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(NetworkAuthorizationRequired, match="separate reviewed"):
        require_network_authorization(_loaded(), None, factory)

    assert called is False


def test_mismatched_authorization_fails_before_transport_factory() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    mismatched = _authorization(loaded).model_copy(update={"plan_file_sha256": "0" * 64})
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(NetworkAuthorizationMismatch, match="plan fingerprint"):
        require_network_authorization(loaded, mismatched, factory)

    assert called is False


def test_exact_authorization_allows_transport_factory_only_after_validation() -> None:
    from peru_conflicts.acquisition.policy import require_network_authorization

    loaded = _loaded()
    transport = object()
    calls = 0

    def factory() -> object:
        nonlocal calls
        calls += 1
        return transport

    grant = require_network_authorization(loaded, _authorization(loaded), factory)

    assert grant.transport is transport
    assert grant.plan_id == loaded.plan.plan_id
    assert grant.allowed_landing_targets == tuple(
        (target.report_number, target.landing_page_url) for target in loaded.plan.targets
    )
    assert grant.allowed_pdf_targets == tuple(
        (target.report_number, target.direct_download_url) for target in loaded.plan.targets
    )
    assert grant.limits == loaded.plan.limits
    assert calls == 1


def test_network_grant_is_single_use_and_attempt_budget_cannot_be_widened() -> None:
    from peru_conflicts.acquisition.policy import (
        AttemptBudget,
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    transport = object()
    grant = require_network_authorization(
        loaded,
        _authorization(loaded),
        lambda: transport,
    )

    assert grant.claim_transport() is transport
    with pytest.raises(NetworkAuthorizationMismatch, match="already been claimed"):
        grant.claim_transport()

    budget = AttemptBudget(limit=60)
    with pytest.raises(FrozenInstanceError):
        budget.limit = 600  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        budget.used = 0  # type: ignore[misc]


def test_network_grant_clones_share_one_consumable_claim_state() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    transport = object()
    grant = require_network_authorization(
        loaded,
        _authorization(loaded),
        lambda: transport,
    )
    shallow_clone = copy(grant)
    replaced_clone = replace(grant)

    assert shallow_clone.claim_transport() is transport
    for candidate in (grant, replaced_clone):
        with pytest.raises(NetworkAuthorizationMismatch, match="already been claimed"):
            candidate.claim_transport()


def test_network_grant_rejects_post_authorization_scope_or_limit_replacement() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    grant = require_network_authorization(loaded, _authorization(loaded), object)
    changed_targets = replace(
        grant,
        allowed_pdf_targets=(
            (260, "https://www.defensoria.gob.pe/unreviewed.pdf"),
            *grant.allowed_pdf_targets[1:],
        ),
    )
    weakened_limits = replace(
        grant,
        limits=grant.limits.model_copy(
            update={
                "max_redirects_per_url": 999,
                "per_file_min_bytes": 1,
                "per_file_max_bytes": 400_000_000,
            }
        ),
    )

    for candidate in (changed_targets, weakened_limits):
        with pytest.raises(NetworkAuthorizationMismatch, match=r"policy.*changed"):
            candidate.require_valid()


@pytest.mark.parametrize(
    "unsafe_update",
    (
        {"authorization_status": "not_authorized"},
        {"scope": "wrong_scope"},
        {"schema_version": "9.9.9"},
        {"approved_by": ""},
    ),
)
def test_nonvalidating_artifact_mutation_cannot_reach_transport_factory(
    unsafe_update: dict[str, str],
) -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    tampered = _authorization(loaded).model_copy(update=unsafe_update)
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(NetworkAuthorizationMismatch, match="artifact is invalid"):
        require_network_authorization(loaded, tampered, factory)

    assert called is False


def test_nonvalidating_plan_limit_mutation_cannot_reach_transport_factory() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    weakened_limits = loaded.plan.limits.model_copy(
        update={
            "max_redirects_per_url": 999,
            "per_file_min_bytes": 0,
            "per_file_max_bytes": 400_000_000,
        }
    )
    weakened_plan = loaded.plan.model_copy(update={"limits": weakened_limits})
    weakened_loaded = LoadedPilotPlan(
        plan=weakened_plan,
        file_sha256=loaded.file_sha256,
        semantic_sha256=loaded.semantic_sha256,
        target_set_sha256=loaded.target_set_sha256,
    )
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(NetworkAuthorizationMismatch, match="pilot plan is invalid"):
        require_network_authorization(
            weakened_loaded,
            _authorization(loaded),
            factory,
        )

    assert called is False


def test_valid_but_unreviewed_plan_mutation_cannot_reach_transport_factory() -> None:
    from peru_conflicts.acquisition.policy import (
        NetworkAuthorizationMismatch,
        require_network_authorization,
    )

    loaded = _loaded()
    changed_target = loaded.plan.targets[0].model_copy(
        update={"landing_page_url": "https://www.defensoria.gob.pe/documentos/unreviewed-target/"}
    )
    changed_plan = loaded.plan.model_copy(
        update={"targets": (changed_target, *loaded.plan.targets[1:])}
    )
    changed_loaded = LoadedPilotPlan(
        plan=changed_plan,
        file_sha256=loaded.file_sha256,
        semantic_sha256=loaded.semantic_sha256,
        target_set_sha256=loaded.target_set_sha256,
    )
    called = False

    def factory() -> object:
        nonlocal called
        called = True
        return object()

    with pytest.raises(NetworkAuthorizationMismatch, match="fingerprints are invalid"):
        require_network_authorization(changed_loaded, _authorization(loaded), factory)

    assert called is False


@pytest.mark.parametrize(
    "url",
    (
        "http://defensoria.gob.pe/documentos/reporte.pdf",
        "https://defensoria.gob.pe:444/documentos/reporte.pdf",
        "https://user:secret@defensoria.gob.pe/documentos/reporte.pdf",
        "https://files.defensoria.gob.pe/documentos/reporte.pdf",
        "https://example.org/reporte.pdf",
        "https://defensoria.gob.pe/documentos/reporte.pdf?token=secret",
    ),
)
def test_url_policy_rejects_non_authoritative_or_non_default_https(url: str) -> None:
    from peru_conflicts.acquisition.policy import UnapprovedAcquisitionUrl, validate_url

    with pytest.raises(UnapprovedAcquisitionUrl):
        validate_url(url, frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe")))


def test_url_policy_accepts_exact_approved_https_host_and_normalizes_fragment() -> None:
    from peru_conflicts.acquisition.policy import validate_url

    normalized = validate_url(
        "https://WWW.DEFENSORIA.GOB.PE:443/documentos/reporte.pdf#download",
        frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe")),
    )

    assert normalized == "https://www.defensoria.gob.pe/documentos/reporte.pdf"


def test_redirect_policy_rejects_off_host_loop_and_sixth_hop() -> None:
    from peru_conflicts.acquisition.policy import (
        RedirectLimitExceeded,
        RedirectLoop,
        UnapprovedAcquisitionUrl,
        validate_redirect_target,
    )

    approved = frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe"))
    current = "https://www.defensoria.gob.pe/a"
    with pytest.raises(UnapprovedAcquisitionUrl):
        validate_redirect_target(
            current_url=current,
            location="https://example.org/b",
            approved_hosts=approved,
            seen=frozenset((current,)),
            redirect_hop=1,
            max_redirects=5,
        )
    with pytest.raises(RedirectLoop):
        validate_redirect_target(
            current_url=current,
            location="/a",
            approved_hosts=approved,
            seen=frozenset((current,)),
            redirect_hop=1,
            max_redirects=5,
        )
    with pytest.raises(RedirectLimitExceeded):
        validate_redirect_target(
            current_url=current,
            location="/b",
            approved_hosts=approved,
            seen=frozenset((current,)),
            redirect_hop=6,
            max_redirects=5,
        )


def test_scheduler_enforces_two_seconds_and_global_attempt_budget() -> None:
    from peru_conflicts.acquisition.policy import (
        AttemptBudget,
        AttemptBudgetExhausted,
        SerialScheduler,
    )

    now = 10.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    budget = AttemptBudget(limit=2)
    scheduler = SerialScheduler(
        delay_seconds=2.0,
        budget=budget,
        clock=clock,
        sleep=sleep,
    )
    scheduler.before_attempt()
    scheduler.before_attempt(requested_wait=0.5)

    assert sleeps == [2.0]
    assert budget.used == 2
    with pytest.raises(AttemptBudgetExhausted):
        scheduler.before_attempt()
    assert sleeps == [2.0]


def test_retry_after_wait_begins_when_the_response_is_observed_not_at_request_start() -> None:
    from peru_conflicts.acquisition.policy import AttemptBudget, SerialScheduler

    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    scheduler = SerialScheduler(
        delay_seconds=2.0,
        budget=AttemptBudget(limit=2),
        clock=clock,
        sleep=sleep,
    )
    scheduler.before_attempt()
    now = 3.0  # the response arrived three seconds after the request began
    scheduler.before_attempt(requested_wait=7.0)

    assert sleeps == [7.0]
    assert now == 10.0


def test_scheduler_rejects_unsafe_live_limits() -> None:
    from peru_conflicts.acquisition.policy import AttemptBudget, SerialScheduler

    with pytest.raises(ValueError, match=r"at least 2\.0"):
        SerialScheduler(delay_seconds=1.99, budget=AttemptBudget(limit=60))
    with pytest.raises(ValueError, match="at most 60"):
        AttemptBudget(limit=61)
