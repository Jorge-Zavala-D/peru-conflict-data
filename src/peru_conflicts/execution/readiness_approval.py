"""Strict owner-readiness authority, explicitly excluding annotation launch."""

from datetime import datetime
from typing import Literal

from pydantic import field_validator

from peru_conflicts.models.common import Sha256, StrictModel

DECISION_SCOPES = {
    "REFERENCE-EXTRACTION-POLICY": "native_raw_lf_codepoint_reference_aid_only",
    "REFERENCE-SNAPSHOT-CUSTODY": "retained_source_protected_snapshot_custody_design_only",
    "ANNOTATOR-PACKAGE-SURFACE": "neutral_blank_surface_only_no_distribution",
    "SOURCE-POSITION-HELPER": "human_selected_coordinate_conversion_only",
    "DISCOVERY-COMPLETENESS": "explicit_inspection_and_zero_certification_only",
    "FIELD-ANNOTATION-WORKFLOW": "empty_slots_from_human_declarations_only",
    "EVIDENCE-WORKFLOW": "typed_evidence_structure_only_not_substantive_correctness",
    "LOCK-AND-SUPERSESSION": "design_only",
    "AB-ISOLATION": "design_conditional_on_launch_time_real_access_testing",
    "HUMAN-ELIGIBILITY": "launch_prerequisite_only_no_person_assigned",
    "HELDOUT-SEALING": "design_only_future_real_access_testing_required",
    "EXTERNAL-DROPBOX-STRUCTURE": "layout_only_no_creation_or_write",
    "REAL-SOURCE-BLANK-PREVIEW": "readiness_review_only_noncanonical_unissued",
    "SYNTHETIC-REHEARSAL": "implementation_evidence_only",
    "READINESS-TO-PREPARE-LAUNCH": "readiness_to_prepare_separate_launch_gate_only",
}


class ReadinessDecision(StrictModel):
    status: Literal["APPROVED"]
    approved_scope: str
    qualifications: list[str]

    @field_validator("qualifications")
    @classmethod
    def qualified(cls, value: list[str]) -> list[str]:
        if not value or any(not item.strip() for item in value):
            raise ValueError("each decision requires explicit scope qualifications")
        return value


class OwnerReadinessApproval(StrictModel):
    approval_record_version: Literal["1.0.0"]
    approval_id: Literal["M2-02A-OWNER-READINESS-APPROVAL-V1"]
    milestone: Literal["M2-02A"]
    owner: Literal["Jorge Zavala"]
    owner_decision_status: Literal["approved"]
    approved_at: str
    authority: Literal["explicit_owner_decisions_in_m2_02a_2_prompt"]
    reviewed_pr_number: Literal[13]
    reviewed_branch: Literal["codex/m2-02a1-production-readiness"]
    reviewed_head_sha: Literal["35bc0fa78c5ddfde51e9acf88bf4fcda754d89f3"]
    reviewed_tree_sha: Literal["5caf98cd8ee6acc60ddc26b832524594152eada6"]
    reviewed_actions_run_id: Literal[34683159130]
    readiness_evidence_index_v4_sha256: Sha256
    owner_readiness_dossier_json_sha256: Sha256
    owner_readiness_dossier_md_sha256: Sha256
    final_owner_readiness_packet_sha256: Sha256
    date_pair_interpretation_approval_sha256: Sha256
    critical_field_set_sha256: Sha256
    scientific_schema_digest: Sha256
    benchmark_schema_digest: Sha256
    evaluator_sha256: Sha256
    reference_manifest_sha256: Sha256
    prereview_package_a_manifest_sha256: Sha256
    prereview_package_b_manifest_sha256: Sha256
    decision_count: Literal[15]
    pending_decisions_after_approval: Literal[0]
    decisions: dict[str, ReadinessDecision]
    owner_readiness_approved: Literal[True]
    annotation_launch_approved: Literal[False]
    annotation_started: Literal[False]
    human_gold_created: Literal[False]
    dropbox_writes_approved: Literal[False]
    parser_work_approved: Literal[False]
    normative_metric_amendment_approved: Literal[False]
    m3_approved: Literal[False]

    @field_validator("approved_at")
    @classmethod
    def aware_time(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("approval recording timestamp must be offset-aware")
        return value

    @field_validator("decisions")
    @classmethod
    def exact_decisions(cls, value: dict[str, ReadinessDecision]) -> dict[str, ReadinessDecision]:
        if list(value) != list(DECISION_SCOPES):
            raise ValueError("exact fifteen ordered owner decision IDs required")
        if any(value[key].approved_scope != scope for key, scope in DECISION_SCOPES.items()):
            raise ValueError("owner decision scope differs from explicit authority")
        return value
