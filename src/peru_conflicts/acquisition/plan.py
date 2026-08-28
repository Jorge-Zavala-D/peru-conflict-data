"""Versioned acquisition-plan loading and deterministic fingerprints."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from peru_conflicts.acquisition.models import AcquisitionPilotPlan
from peru_conflicts.hashing import canonical_json_bytes

REVIEWED_V2_PLAN_FILE_SHA256 = "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"
REVIEWED_V2_PLAN_SEMANTIC_SHA256 = (
    "e4b8ca609af2290563dab312488da0017ec67f5c8e05dbdf269861262b979c5b"
)
REVIEWED_TARGET_SET_SHA256 = "721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1"


class PlanDigestMismatch(ValueError):
    """The caller or reviewed repository digest did not match the plan bytes."""


class PlanFingerprintMismatch(ValueError):
    """Validated plan semantics did not match the reviewed pilot."""


@dataclass(frozen=True, slots=True)
class LoadedPilotPlan:
    """Validated plan plus its three non-interchangeable fingerprints."""

    plan: AcquisitionPilotPlan
    file_sha256: str
    semantic_sha256: str
    target_set_sha256: str


def validate_reviewed_loaded_plan(loaded: LoadedPilotPlan) -> AcquisitionPilotPlan:
    """Revalidate an in-memory plan and all reviewed fingerprints before use."""

    try:
        plan = AcquisitionPilotPlan.model_validate(
            loaded.plan.model_dump(mode="python"), strict=True
        )
    except ValidationError as error:
        raise PlanFingerprintMismatch("loaded plan fails strict reviewed validation") from error
    rendered = plan.model_dump(mode="json")
    semantic_sha256 = hashlib.sha256(canonical_json_bytes(rendered)).hexdigest()
    target_set_sha256 = hashlib.sha256(canonical_json_bytes(rendered["targets"])).hexdigest()
    if (
        loaded.file_sha256 != REVIEWED_V2_PLAN_FILE_SHA256
        or loaded.semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256
        or loaded.target_set_sha256 != REVIEWED_TARGET_SET_SHA256
        or semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256
        or target_set_sha256 != REVIEWED_TARGET_SET_SHA256
    ):
        raise PlanFingerprintMismatch("loaded plan does not match the exact reviewed pilot")
    return plan


def load_reviewed_pilot_plan(path: Path, *, required_sha256: str) -> LoadedPilotPlan:
    """Load the reviewed v2 pilot after caller and repository digest checks."""

    if re.fullmatch(r"[0-9a-f]{64}", required_sha256) is None:
        raise PlanDigestMismatch("required plan SHA-256 must be 64 lowercase hexadecimal digits")
    raw = path.read_bytes()
    file_sha256 = hashlib.sha256(raw).hexdigest()
    if file_sha256 != required_sha256:
        raise PlanDigestMismatch("plan bytes do not match the caller-required SHA-256")
    if file_sha256 != REVIEWED_V2_PLAN_FILE_SHA256:
        raise PlanDigestMismatch("plan bytes do not match the reviewed v2 plan fingerprint")

    payload = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("acquisition plan must be a YAML mapping")
    plan = AcquisitionPilotPlan.model_validate(payload)
    rendered = plan.model_dump(mode="json")
    semantic_sha256 = hashlib.sha256(canonical_json_bytes(rendered)).hexdigest()
    target_set_sha256 = hashlib.sha256(canonical_json_bytes(rendered["targets"])).hexdigest()
    if semantic_sha256 != REVIEWED_V2_PLAN_SEMANTIC_SHA256:
        raise PlanFingerprintMismatch("plan semantics do not match the reviewed v2 fingerprint")
    if target_set_sha256 != REVIEWED_TARGET_SET_SHA256:
        raise PlanFingerprintMismatch(
            "plan targets do not match the reviewed target-set fingerprint"
        )
    loaded = LoadedPilotPlan(
        plan=plan,
        file_sha256=file_sha256,
        semantic_sha256=semantic_sha256,
        target_set_sha256=target_set_sha256,
    )
    validate_reviewed_loaded_plan(loaded)
    return loaded
