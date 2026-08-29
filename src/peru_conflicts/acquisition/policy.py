"""Fail-closed authority, authorization, timing, and attempt-budget policy."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlsplit

from pydantic import ValidationError

from peru_conflicts.acquisition.models import (
    AcquisitionPilotPlan,
    NetworkAuthorizationArtifact,
)
from peru_conflicts.acquisition.models_v2 import NetworkAuthorizationArtifactV2
from peru_conflicts.acquisition.plan import (
    REVIEWED_TARGET_SET_SHA256,
    REVIEWED_V2_PLAN_FILE_SHA256,
    REVIEWED_V2_PLAN_SEMANTIC_SHA256,
    LoadedPilotPlan,
)
from peru_conflicts.discovery.pilot import PilotLimits
from peru_conflicts.discovery.policy import classify_host, normalize_url
from peru_conflicts.hashing import canonical_json_bytes


class AcquisitionPolicyError(RuntimeError):
    """Base class for a rejected future acquisition operation."""


class NetworkAuthorizationRequired(AcquisitionPolicyError):
    """No separately reviewed network-authorization artifact was supplied."""


class NetworkAuthorizationMismatch(AcquisitionPolicyError):
    """The authorization artifact does not identify the reviewed plan."""


class UnapprovedAcquisitionUrl(AcquisitionPolicyError):
    """A URL is outside the exact approved HTTPS authority boundary."""


class RedirectLoop(AcquisitionPolicyError):
    """A redirect revisited an already observed URL."""


class RedirectLimitExceeded(AcquisitionPolicyError):
    """A redirect would exceed the reviewed hop limit."""


class AttemptBudgetExhausted(AcquisitionPolicyError):
    """The global attempt budget was exhausted before transport use."""


class SealedTransportPolicyError(AcquisitionPolicyError):
    """A production request differed from its reviewed canonical capability."""


_NETWORK_GRANT_SEAL = object()


class _GrantClaimState:
    """One shared, atomically consumed state across shallow/dataclass grant clones."""

    __slots__ = ("_claimed", "_lock", "_policy_fingerprint", "_seal", "_transport")

    def __init__(self, seal: object, policy_fingerprint: str, transport: object) -> None:
        self._claimed = False
        self._lock = Lock()
        self._policy_fingerprint = policy_fingerprint
        self._seal = seal
        self._transport = transport

    def require_valid(self, *, policy_fingerprint: str, transport: object) -> None:
        if self._seal is not _NETWORK_GRANT_SEAL:
            raise NetworkAuthorizationMismatch("network access grant is not authentic")
        if self._policy_fingerprint != policy_fingerprint or self._transport is not transport:
            raise NetworkAuthorizationMismatch("network access grant policy changed after review")

    def claim(self, *, policy_fingerprint: str, transport: object) -> None:
        self.require_valid(policy_fingerprint=policy_fingerprint, transport=transport)
        with self._lock:
            if self._claimed:
                raise NetworkAuthorizationMismatch("network access grant has already been claimed")
            self._claimed = True


@dataclass(frozen=True, slots=True)
class NetworkAccessGrant[TransportT]:
    """Opaque pilot-scoped capability created only after full artifact validation."""

    transport: TransportT
    authorization_id: str
    plan_id: str
    plan_file_sha256: str
    baseline_git_commit: str
    approved_hosts: frozenset[str]
    limits: PilotLimits
    allowed_landing_targets: tuple[tuple[int, str], ...]
    allowed_pdf_targets: tuple[tuple[int, str], ...]
    _seal: object
    _claim_state: _GrantClaimState = field(repr=False, compare=False)

    def require_valid(self) -> None:
        if self._seal is not _NETWORK_GRANT_SEAL:
            raise NetworkAuthorizationMismatch("network access grant is not authentic")
        self._claim_state.require_valid(
            policy_fingerprint=_grant_policy_fingerprint(self), transport=self.transport
        )

    def claim_transport(self) -> TransportT:
        """Consume this run-scoped capability exactly once."""

        self.require_valid()
        self._claim_state.claim(
            policy_fingerprint=_grant_policy_fingerprint(self), transport=self.transport
        )
        return self.transport


def _grant_policy_fingerprint[TransportT](grant: NetworkAccessGrant[TransportT]) -> str:
    payload = {
        "authorization_id": grant.authorization_id,
        "plan_id": grant.plan_id,
        "plan_file_sha256": grant.plan_file_sha256,
        "baseline_git_commit": grant.baseline_git_commit,
        "approved_hosts": sorted(grant.approved_hosts),
        "limits": grant.limits.model_dump(mode="json"),
        "allowed_landing_targets": grant.allowed_landing_targets,
        "allowed_pdf_targets": grant.allowed_pdf_targets,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def require_network_authorization[TransportT](
    loaded_plan: LoadedPilotPlan,
    artifact: NetworkAuthorizationArtifact | None,
    transport_factory: Callable[[], TransportT],
) -> NetworkAccessGrant[TransportT]:
    """Construct a transport only after an exact separate artifact is verified."""

    if artifact is None:
        raise NetworkAuthorizationRequired(
            "network access requires a separate reviewed authorization artifact"
        )
    try:
        validated = NetworkAuthorizationArtifact.model_validate(
            artifact.model_dump(mode="python"), strict=True
        )
    except ValidationError as error:
        raise NetworkAuthorizationMismatch("authorization artifact is invalid") from error
    if (
        validated.authorization_status != "authorized"
        or validated.scope != "m1_03b_reports_260_269_network"
    ):
        raise NetworkAuthorizationMismatch("authorization artifact is invalid")

    try:
        plan = AcquisitionPilotPlan.model_validate(
            loaded_plan.plan.model_dump(mode="python"), strict=True
        )
    except ValidationError as error:
        raise NetworkAuthorizationMismatch("reviewed pilot plan is invalid") from error
    rendered = plan.model_dump(mode="json")
    semantic_sha256 = hashlib.sha256(canonical_json_bytes(rendered)).hexdigest()
    target_set_sha256 = hashlib.sha256(canonical_json_bytes(rendered["targets"])).hexdigest()
    if (
        loaded_plan.file_sha256 != REVIEWED_V2_PLAN_FILE_SHA256
        or loaded_plan.semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256
        or loaded_plan.target_set_sha256 != REVIEWED_TARGET_SET_SHA256
        or semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256
        or target_set_sha256 != REVIEWED_TARGET_SET_SHA256
    ):
        raise NetworkAuthorizationMismatch("reviewed pilot fingerprints are invalid")
    if validated.plan_id != plan.plan_id or validated.plan_file_sha256 != loaded_plan.file_sha256:
        raise NetworkAuthorizationMismatch("authorization plan fingerprint does not match")
    if validated.baseline_git_commit != plan.baseline_receipt_git_commit:
        raise NetworkAuthorizationMismatch("authorization baseline Git commit does not match")
    transport = transport_factory()
    approved_hosts = frozenset(plan.approved_hosts)
    landing_targets = tuple(
        (target.report_number, target.landing_page_url) for target in plan.targets
    )
    pdf_targets = tuple(
        (target.report_number, target.direct_download_url) for target in plan.targets
    )
    provisional = NetworkAccessGrant(
        transport=transport,
        authorization_id=validated.authorization_id,
        plan_id=plan.plan_id,
        plan_file_sha256=loaded_plan.file_sha256,
        baseline_git_commit=plan.baseline_receipt_git_commit,
        approved_hosts=approved_hosts,
        limits=plan.limits,
        allowed_landing_targets=landing_targets,
        allowed_pdf_targets=pdf_targets,
        _seal=_NETWORK_GRANT_SEAL,
        _claim_state=_GrantClaimState(_NETWORK_GRANT_SEAL, "pending", transport),
    )
    policy_fingerprint = _grant_policy_fingerprint(provisional)
    return NetworkAccessGrant(
        transport=transport,
        authorization_id=provisional.authorization_id,
        plan_id=provisional.plan_id,
        plan_file_sha256=provisional.plan_file_sha256,
        baseline_git_commit=provisional.baseline_git_commit,
        approved_hosts=approved_hosts,
        limits=plan.limits,
        allowed_landing_targets=landing_targets,
        allowed_pdf_targets=pdf_targets,
        _seal=_NETWORK_GRANT_SEAL,
        _claim_state=_GrantClaimState(_NETWORK_GRANT_SEAL, policy_fingerprint, transport),
    )


def seal_validated_v2_network_grant[TransportT](
    loaded_plan: LoadedPilotPlan,
    artifact: NetworkAuthorizationArtifactV2,
    transport: TransportT,
) -> NetworkAccessGrant[TransportT]:
    """Seal transport only after the independently reviewed v0.2 artifact is validated."""

    plan = loaded_plan.plan
    limits_sha256 = hashlib.sha256(
        canonical_json_bytes(plan.limits.model_dump(mode="json"))
    ).hexdigest()
    if (
        loaded_plan.file_sha256 != REVIEWED_V2_PLAN_FILE_SHA256
        or loaded_plan.semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256
        or loaded_plan.target_set_sha256 != REVIEWED_TARGET_SET_SHA256
        or artifact.plan_id != plan.plan_id
        or artifact.plan_file_sha256 != loaded_plan.file_sha256
        or artifact.plan_semantic_sha256 != loaded_plan.semantic_sha256
        or artifact.ordered_target_set_sha256 != loaded_plan.target_set_sha256
        or artifact.plan_limits_sha256 != limits_sha256
        or artifact.approved_report_numbers
        != tuple(target.report_number for target in plan.targets)
        or artifact.approved_hosts != tuple(plan.approved_hosts)
    ):
        raise NetworkAuthorizationMismatch("v0.2 authorization does not bind the reviewed pilot")
    approved_hosts = frozenset(plan.approved_hosts)
    landing_targets = tuple(
        (target.report_number, target.landing_page_url) for target in plan.targets
    )
    pdf_targets = tuple(
        (target.report_number, target.direct_download_url) for target in plan.targets
    )
    provisional = NetworkAccessGrant(
        transport=transport,
        authorization_id=artifact.authorization_id,
        plan_id=plan.plan_id,
        plan_file_sha256=loaded_plan.file_sha256,
        baseline_git_commit=artifact.protected_source_receipt_git_commit,
        approved_hosts=approved_hosts,
        limits=plan.limits,
        allowed_landing_targets=landing_targets,
        allowed_pdf_targets=pdf_targets,
        _seal=_NETWORK_GRANT_SEAL,
        _claim_state=_GrantClaimState(_NETWORK_GRANT_SEAL, "pending", transport),
    )
    fingerprint = _grant_policy_fingerprint(provisional)
    return NetworkAccessGrant(
        transport=transport,
        authorization_id=provisional.authorization_id,
        plan_id=provisional.plan_id,
        plan_file_sha256=provisional.plan_file_sha256,
        baseline_git_commit=provisional.baseline_git_commit,
        approved_hosts=approved_hosts,
        limits=plan.limits,
        allowed_landing_targets=landing_targets,
        allowed_pdf_targets=pdf_targets,
        _seal=_NETWORK_GRANT_SEAL,
        _claim_state=_GrantClaimState(_NETWORK_GRANT_SEAL, fingerprint, transport),
    )


def validate_url(url: str, approved_hosts: frozenset[str]) -> str:
    """Normalize a URL and require an exact approved HTTPS host/default port."""

    try:
        normalized = normalize_url(url)
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as error:
        raise UnapprovedAcquisitionUrl("invalid acquisition URL") from error
    original = urlsplit(url)
    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or original.username is not None
        or original.password is not None
        or bool(parsed.query)
        or classify_host(normalized, approved_hosts) != "authoritative"
    ):
        raise UnapprovedAcquisitionUrl(
            "acquisition URLs require an exact approved HTTPS host and default port"
        )
    return normalized


def validate_redirect_target(
    *,
    current_url: str,
    location: str,
    approved_hosts: frozenset[str],
    seen: frozenset[str],
    redirect_hop: int,
    max_redirects: int,
) -> str:
    """Resolve one redirect without widening authority or allowing loops."""

    if redirect_hop > max_redirects:
        raise RedirectLimitExceeded(f"redirect limit of {max_redirects} exceeded")
    try:
        target = normalize_url(location, base_url=current_url)
    except ValueError as error:
        raise UnapprovedAcquisitionUrl("redirect Location is not a valid URL") from error
    target = validate_url(target, approved_hosts)
    if target in seen:
        raise RedirectLoop(f"redirect revisits an observed URL: {target}")
    return target


@dataclass(frozen=True, slots=True)
class AttemptBudget:
    """A bounded counter debited immediately before every transport attempt."""

    limit: int = 60
    used: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 60:
            raise ValueError("attempt budget must contain at most 60 attempts")
        if self.used != 0:
            raise ValueError("a new attempt budget must start unused")

    def consume(self) -> int:
        if self.used >= self.limit:
            raise AttemptBudgetExhausted("global attempt budget exhausted before request")
        object.__setattr__(self, "used", self.used + 1)
        return self.used


class SerialScheduler:
    """Enforce serial request spacing while respecting a stricter retry wait."""

    def __init__(
        self,
        *,
        delay_seconds: float,
        budget: AttemptBudget,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        if delay_seconds < 2.0:
            raise ValueError("live request spacing must be at least 2.0 seconds")
        self._delay_seconds = delay_seconds
        self._budget = budget
        self._clock = clock
        self._sleep = sleep
        self._last_attempt_at: float | None = None

    @property
    def budget(self) -> AttemptBudget:
        return self._budget

    def before_attempt(self, *, requested_wait: float = 0.0) -> int:
        """Debit first, then wait, so exhaustion cannot cause an extra sleep/request."""

        attempt_number = self._budget.consume()
        now = self._clock()
        earliest = now + max(0.0, requested_wait)
        if self._last_attempt_at is not None:
            earliest = max(earliest, self._last_attempt_at + self._delay_seconds)
            remaining = max(0.0, earliest - now)
            if remaining:
                self._sleep(remaining)
        self._last_attempt_at = self._clock()
        return attempt_number
