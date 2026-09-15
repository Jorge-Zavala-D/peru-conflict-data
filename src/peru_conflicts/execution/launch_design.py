"""Coordinator-only design authority; never distribution, issuance or launch authority."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import ValidationInfo, field_validator, model_validator

from peru_conflicts.models.common import Sha256, StrictModel

from .launch import DRAFT_FALSE_FLAGS, LaunchCandidate, model_sha256, verify_candidate
from .launch_review import DECISIONS
from .references import sha256

ROOT = Path(__file__).resolve().parents[3]
APPROVAL_PATH = ROOT / "config/benchmark/m2_02b1_launch_design_approval_v1.yaml"
CANDIDATE_PATH = ROOT / "config/benchmark/m2_02_launch_candidate_v2.yaml"
V1_PATH = ROOT / "config/benchmark/m2_02_launch_candidate_v1.yaml"
# Exact UTF-8 LF-normalized owner scope paragraphs, including every qualification.
SCOPE_HASHES = [
    "67e18eebc66d5b3dabb8b2cb57399ec00d172693676f308e6870a96de882e577",
    "3cede0c7b65a1040c749e70c3eb46153878a6c21d7244066187557a15c8421ca",
    "88feb36b1acbe117d7489142ef36fdbff6033804783ef8c5d075fb4fb0b661ea",
    "63b1c0e7ec188f00970d2371051a95a481ba1badb0add3901bd1fddc8b06e043",
    "2544787374f7accb83b1469681237f53f01a6971140af11be0318da3d172ebc3",
    "10f05d9ad1fcf3505f2ff7857de9874aa89104280496582711b85cb0ffc6604e",
    "c84a72e6f4f033760e869a7c13a5dbbed7cc3b9f0b29ec5f4830132427dd5bc8",
    "a875e780af47b5a1546fa2404afcb1cc3ae118f9d8e0473a91895a724d4d69cf",
    "6de5ce1d96bae23f6efc88cbc7bef69c1fbfe579f3a84b9675f1d90f5d22ba5d",
]
REVIEW_BINDINGS = {
    "owner_readiness_approval_sha256": (
        "36a5074264f93a9c565b4011b7162031d62e3a135eaba17336dcd8c51cc43cba"
    ),
    "readiness_v3_sha256": "b6fd726b2f7067cb38e8e04df51eb9f39d7f6928837775a747beb4b5e3dcc4a2",
    "evidence_v5_sha256": "5cd65a2d78884e9744ef2cc8c21bbbf9ef4bfe1342553c62c11f29156034f224",
    "candidate_v1_sha256": "e230f9d277803e8ff8324922a1c91e1a8ce5ae5d689aac8146b1745b96d7ba02",
    "candidate_v1_model_sha256": "173d0cb66f2faa36cde73a7844cc963b97cbc2fbe0bf6c6e0cda915700219cf2",
    "access_policy_sha256": "54d0d97c05bee58680064ca61f9a7cf512f6b5244b10ff9be035c82892624422",
    "runtime_sha256": "1e9efd35c82ee95ccc382c379b34009b70f0bfd85b284530871c91bc98c677ba",
    "runtime_file_set_sha256": "49d686c9349fda6230e49f22ae136f203977015b329f2cf2023276187231c476",
    "python_environment_sha256": "f1ecff17cd7adbe8b544270c3ea4fe5e3bd12a512ad1f6fbdb77816a6d286455",
    "python_environment_manifest_sha256": (
        "9ea05dd0a396e8dda33b21d0050b0110bbe7e64188ce8324b333b7c9f9461db2"
    ),
    "launcher_sha256": "44489530f735f09418ef2bd4a9aee9c15eb65b5519f97136d484eaa71852f1a0",
    "interpreter_sha256": "88b9e780cfdc38597c7f53e20f7165262befa28d9a5e9470360d349e172ecf37",
    "dependency_sha256": "e1b8506b39c87b76b0d7f9bad508d4ae319f6c3271384b5cb4b03c2490baf03f",
    "reference_manifest_sha256": "060d6f166e35400ba53d563fb75dfae4c4872d22796b12762e35bd6d15f88202",
    "annotator_a_package_manifest_sha256": (
        "45540cc5face34903fa98fb1fc7763546d3e8328d189a68588ae93e23ec27484"
    ),
    "annotator_b_package_manifest_sha256": (
        "c4b8acc6f0dbe4920ac8a0c4e06607dedcc04f6377a3723f4293a314058a77b7"
    ),
    "annotator_a_view_sha256": "4a741fdbb087457ac3e9c7803db6527b7e01bbca5943d1fb5f8f376599e9d225",
    "annotator_b_view_sha256": "58f33685eb4d9a2664b2176516fc23f5917ac6799dee579102af30f7a5362668",
    "final_hardening_packet_sha256": (
        "b676ad1f1db287763318e5fbcf1f1f4f40f290b45e3c379fa4b2a359358f4c84"
    ),
}


class DesignState(StrictModel):
    owner_readiness_approved: Literal[True] = True
    launch_design_approved: Literal[True] = True
    launch_design_decisions_approved: Literal[9] = 9
    launch_operational_decisions_pending: Literal[7] = 7
    owner_launch_approved: Literal[False] = False
    annotation_launch_approved: Literal[False] = False
    annotation_started: Literal[False] = False
    real_humans_assigned: Literal[False] = False
    real_eligibility_attestations_created: Literal[False] = False
    external_root_created: Literal[False] = False
    dropbox_writes_approved: Literal[False] = False
    real_access_tests_passed: Literal[False] = False
    real_issuance_receipts_created: Literal[False] = False
    real_packages_issued: Literal[False] = False
    production_locking_enabled: Literal[False] = False
    human_gold_created: Literal[False] = False
    parser_work_approved: Literal[False] = False
    m3_owner_approved: Literal[False] = False
    normative_metric_amendment_approved: Literal[False] = False

    @field_validator(
        "launch_design_decisions_approved", "launch_operational_decisions_pending", mode="before"
    )
    @classmethod
    def exact_count_type(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("decision counts require exact integers")
        return value

    @field_validator(
        *DRAFT_FALSE_FLAGS, "owner_readiness_approved", "launch_design_approved", mode="before"
    )
    @classmethod
    def exact_authority_types(cls, value: object, info: ValidationInfo) -> object:
        if info.field_name in DRAFT_FALSE_FLAGS and value is not False:
            raise ValueError("design approval cannot authorize operation")
        if (
            info.field_name in ("owner_readiness_approved", "launch_design_approved")
            and value is not True
        ):
            raise ValueError("explicit design/readiness authority required")
        return value


class DesignDecision(StrictModel):
    decision_id: str
    status: Literal["APPROVED", "UNRESOLVED"]
    response: Literal["APPROVE"] | None
    scope: str | None


class LaunchDesignApproval(DesignState):
    approval_id: Literal["M2-02B1-LAUNCH-DESIGN-APPROVAL-V1"]
    owner: Literal["Jorge Zavala"]
    authority: Literal["Explicit owner decisions in M2-02B.1c prompt"]
    recorded_at: datetime
    pr: Literal[16]
    branch: Literal["codex/m2-02b1-launch-preflight"]
    reviewed_head: Literal["2f0f7a78a09306952aaa548757ce29f6694d767d"]
    reviewed_tree: Literal["1d7cbdf43ba0701fe8057b5ffed4e652a6224817"]
    reviewed_merge_test: Literal["beb9ab22f0b08411f14d60038b8d91e5bfc7cf6f"]
    reviewed_actions_run: Literal[34855471245]
    decision_count: Literal[16]
    approved_count: Literal[9]
    pending_count: Literal[7]
    decisions: tuple[DesignDecision, ...]
    bindings: dict[str, Sha256]
    python_environment_design_approved: Literal[True]
    production_python_environment_approved: Literal[False]
    independent_preexecution_provisioning_required: Literal[True]

    @field_validator("decision_count", "approved_count", "pending_count", mode="before")
    @classmethod
    def exact_approval_count_type(cls, value: object) -> object:
        return cls.exact_count_type(value)

    @field_validator(
        "python_environment_design_approved",
        "independent_preexecution_provisioning_required",
        mode="before",
    )
    @classmethod
    def explicit_design_safeguard(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit boolean design safeguard required")
        return value

    @field_validator("production_python_environment_approved", mode="before")
    @classmethod
    def no_production_environment(cls, value: object) -> object:
        if value is not False:
            raise ValueError("production environment remains unapproved")
        return value

    @model_validator(mode="after")
    def faithful_decisions(self) -> Self:
        if self.recorded_at.utcoffset() is None:
            raise ValueError("recorded timestamp must be offset-aware")
        if tuple(row.decision_id for row in self.decisions) != tuple(row[0] for row in DECISIONS):
            raise ValueError("exact sixteen canonical ordered decisions required")
        for index, row in enumerate(self.decisions):
            if index < 9:
                if row.status != "APPROVED" or row.response != "APPROVE":
                    raise ValueError("first nine decisions must be approved")
                if row.scope is None or sha256(row.scope.encode("utf-8")) != SCOPE_HASHES[index]:
                    raise ValueError("owner scope qualification drift")
            elif row.status != "UNRESOLVED" or row.response is not None or row.scope is not None:
                raise ValueError("last seven operational decisions remain unresolved/null")
        if self.bindings != REVIEW_BINDINGS:
            raise ValueError("review evidence identity drift")
        return self


class LaunchDesignCandidate(DesignState):
    candidate_id: Literal["M2-02-LAUNCH-CANDIDATE-V2"]
    status: Literal["design_approved_operational_pending"]
    launch_design_approval_sha256: Sha256
    reviewed_candidate: LaunchCandidate


def validate_active_design(
    approval_bytes: bytes | None = None,
    candidate_bytes: bytes | None = None,
) -> LaunchDesignCandidate:
    """Validate coordinator successor; returned design grants no execution capability."""
    approval_bytes = APPROVAL_PATH.read_bytes() if approval_bytes is None else approval_bytes
    candidate_bytes = CANDIDATE_PATH.read_bytes() if candidate_bytes is None else candidate_bytes
    approval = LaunchDesignApproval.model_validate_json(json.dumps(yaml.safe_load(approval_bytes)))
    candidate = LaunchDesignCandidate.model_validate_json(
        json.dumps(yaml.safe_load(candidate_bytes))
    )
    if candidate.launch_design_approval_sha256 != sha256(approval_bytes):
        raise ValueError("candidate must bind exact approval bytes")
    v1_bytes = V1_PATH.read_bytes()
    if sha256(v1_bytes) != approval.bindings["candidate_v1_sha256"]:
        raise ValueError("historical candidate v1 byte drift")
    v1 = LaunchCandidate.model_validate_json(json.dumps(yaml.safe_load(v1_bytes)))
    if (
        model_sha256(v1) != approval.bindings["candidate_v1_model_sha256"]
        or candidate.reviewed_candidate != v1
    ):
        raise ValueError("successor must preserve complete reviewed candidate")
    verify_candidate(v1, approval.bindings["candidate_v1_model_sha256"], v1.identities)
    return candidate
