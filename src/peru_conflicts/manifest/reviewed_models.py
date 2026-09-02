"""Strict reviewed records for owner-approved M1 manifest canonicalization."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from peru_conflicts.manifest.models import ArtifactFingerprint, GitCommit, GitTreeSha
from peru_conflicts.models.common import Identifier, ReferencePeriod, Sha256, StrictModel

REVIEWED_MANIFEST_SCHEMA_VERSION = "0.2.0"


class AdjudicationOutcome(StrEnum):
    """Owner-approved conservative outcomes for the frozen M1 review queue."""

    EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED = "evidence_insufficient_retain_unresolved"
    BYTES_NOT_OBSERVED_REMAIN_UNKNOWN = "bytes_not_observed_remain_unknown"
    RETAIN_UNRESOLVED_OPAQUE_FILENAME = "retain_unresolved_opaque_filename"


class HumanReviewStatus(StrEnum):
    """Closure of the human decision process, not resolution of source evidence."""

    OWNER_APPROVED = "owner_approved"


class CoverageAccountingStatus(StrEnum):
    """Coverage-accounting status that does not imply acquired byte completeness."""

    REVIEWED_WITH_EXPLICIT_LIMITATIONS = "reviewed_with_explicit_limitations"


class ApprovalFingerprint(StrictModel):
    """Portable exact-byte binding used by an owner approval event."""

    path: Identifier
    bytes: int = Field(ge=0)
    sha256: Sha256
    record_count: int | None = Field(default=None, ge=0)


class GitStateBinding(StrictModel):
    """Protected-main state to which the reviewed evidence was bound."""

    commit: GitCommit
    tree: GitTreeSha


class ManifestContractBinding(StrictModel):
    """Frozen candidate contract reviewed by the owner."""

    schema_version: Literal["0.1.1"]
    materializer_version: Identifier


class ApprovedDecision(StrictModel):
    """One exact owner-approved review-unit outcome."""

    review_unit_id: Identifier
    approved_outcome: AdjudicationOutcome


class ApprovedDeferredAcquisitionPolicy(StrictModel):
    """Owner decision to retain, not erase, the future byte-acquisition queue."""

    authoritative_byte_corpus_complete: Literal[False]
    blocks_identity_coverage_canonicalization: Literal[False]
    count: Literal[237]
    future_evidence_classification: Literal["useful_but_deferred"]
    report_numbers: tuple[int, ...] = Field(min_length=237, max_length=237)

    @model_validator(mode="after")
    def require_exact_deferred_range(self) -> Self:
        if self.report_numbers != tuple(range(23, 260)):
            raise ValueError("deferred acquisition reports must be exactly 23 through 259")
        return self


class ApprovalScientificAssertions(StrictModel):
    """Negative scientific assertions that prevent owner approval from adding facts."""

    new_report_identities_created: Literal[False]
    new_month_mappings_created: Literal[False]
    new_byte_identities_created: Literal[False]
    unresolved_evidence_retained: Literal[True]
    authoritative_byte_corpus_complete: Literal[False]


class OwnerApprovalArtifact(StrictModel):
    """Exact owner approval event over the frozen M1-04B evidence bytes."""

    schema_version: Literal["0.2.0"] = REVIEWED_MANIFEST_SCHEMA_VERSION
    approval_id: Literal["m1-04b-owner-adjudications-v1"]
    approved_by: Literal["Jorge Zavala"]
    approved_at: AwareDatetime
    owner_approved: Literal[True]
    protected_main: GitStateBinding
    manifest_contract: ManifestContractBinding
    candidate_fingerprints: tuple[ArtifactFingerprint, ...] = Field(min_length=6, max_length=6)
    post_merge_materialization_receipt: ApprovalFingerprint
    review_input_fingerprints: dict[str, ApprovalFingerprint]
    approved_decisions: tuple[ApprovedDecision, ...] = Field(min_length=50, max_length=50)
    approved_outcome_counts: dict[AdjudicationOutcome, int]
    approved_deferred_acquisition_policy: ApprovedDeferredAcquisitionPolicy
    approved_permissible_coverage_statement: tuple[Identifier, ...] = Field(min_length=1)
    prohibited_overclaims: tuple[Identifier, ...] = Field(min_length=1)
    scientific_assertions: ApprovalScientificAssertions

    @model_validator(mode="after")
    def require_exact_review_bindings(self) -> Self:
        required_inputs = {
            "canonicalization_gate",
            "evidence_dossier",
            "m1_04b_review_spec_v011",
            "owner_decision_packet",
            "proposed_adjudications",
            "review_receipt",
        }
        if set(self.review_input_fingerprints) != required_inputs:
            raise ValueError("owner approval must bind the exact six review inputs")
        decision_ids = [item.review_unit_id for item in self.approved_decisions]
        if len(set(decision_ids)) != 50:
            raise ValueError("owner approval decision IDs must be unique")
        actual = Counter(item.approved_outcome for item in self.approved_decisions)
        expected = {
            AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED: 45,
            AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN: 3,
            AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME: 2,
        }
        if dict(actual) != expected or self.approved_outcome_counts != expected:
            raise ValueError("owner approval outcomes must be exactly 45/3/2")
        candidate_paths = [item.path for item in self.candidate_fingerprints]
        expected_candidate_paths = {
            "byte_versions_candidate.jsonl",
            "corpus_manifest_candidate.jsonl",
            "coverage_report_candidate.json",
            "gap_register_candidate.jsonl",
            "source_observations_candidate.jsonl",
            "version_edges_candidate.jsonl",
        }
        if set(candidate_paths) != expected_candidate_paths:
            raise ValueError("candidate fingerprints must bind the exact six outputs")
        return self


class ManifestAdjudicationRecord(StrictModel):
    """Append-only human decision that retains the underlying unresolved evidence."""

    schema_version: Literal["0.2.0"] = REVIEWED_MANIFEST_SCHEMA_VERSION
    adjudication_id: Identifier
    source_review_unit_id: Identifier
    related_gap_ids: tuple[Identifier, ...]
    related_manifest_ids: tuple[Identifier, ...]
    proposed_adjudications_sha256: Sha256
    approved_outcome: AdjudicationOutcome
    approved_by: Literal["Jorge Zavala"]
    owner_approval_id: Literal["m1-04b-owner-adjudications-v1"]
    owner_approval_sha256: Sha256
    evidence_refs: tuple[Identifier, ...] = Field(min_length=1)
    identity_changes: Literal[False]
    month_mapping_changes: Literal[False]
    byte_assertion_changes: Literal[False]
    unresolved_evidence_retained: Literal[True]
    decision_rationale: Identifier
    decided_at: AwareDatetime


class DeferredAcquisitionPolicy(StrictModel):
    """Reviewed policy for observed reports whose authoritative bytes remain deferred."""

    schema_version: Literal["0.2.0"] = REVIEWED_MANIFEST_SCHEMA_VERSION
    policy_id: Literal["m1-deferred-byte-acquisition-23-259-v1"]
    report_numbers: tuple[int, ...] = Field(min_length=237, max_length=237)
    deferred_report_count: Literal[237]
    report_identities_observed: Literal[True]
    authoritative_bytes_acquired: Literal[False]
    authoritative_byte_corpus_complete: Literal[False]
    future_evidence_classification: Literal["useful_but_deferred"]
    owner_approval_id: Literal["m1-04b-owner-adjudications-v1"]
    owner_approval_sha256: Sha256

    @model_validator(mode="after")
    def require_exact_report_range(self) -> Self:
        if self.report_numbers != tuple(range(23, 260)):
            raise ValueError("deferred acquisition policy must retain reports 23 through 259")
        return self


class ReviewedCoverageReport(StrictModel):
    """Owner-reviewed identity coverage with explicit byte-corpus limitations."""

    schema_version: Literal["0.2.0"] = REVIEWED_MANIFEST_SCHEMA_VERSION
    research_coverage_start: Literal["2004-04"]
    observation_cutoff: Literal["2026-07"]
    observed_numbered_report_min: Literal[23]
    observed_numbered_report_max: Literal[269]
    observed_numbered_report_count: Literal[247]
    observed_reference_month_min: Literal["2006-01"]
    observed_reference_month_max: Literal["2026-07"]
    observed_reference_month_count: Literal[247]
    report_to_month_conflict_count: Literal[0]
    month_to_report_conflict_count: Literal[0]
    human_review_status: Literal[HumanReviewStatus.OWNER_APPROVED]
    owner_approved_decision_count: Literal[50]
    approved_outcome_counts: dict[AdjudicationOutcome, int]
    coverage_accounting_status: Literal[CoverageAccountingStatus.REVIEWED_WITH_EXPLICIT_LIMITATIONS]
    factual_gap_count: Literal[287]
    unresolved_evidence_retained: Literal[True]
    deferred_byte_acquisition_count: Literal[237]
    byte_verified_report_count: Literal[10]
    authoritative_byte_corpus_complete: Literal[False]
    reports_1_22_status: Literal["unobserved_report_number_hypotheses"]
    unresolved_historical_months: tuple[ReferencePeriod, ...] = Field(min_length=21, max_length=21)
    historical_unnumbered_lead_years: tuple[Literal[2004, 2005], ...] = Field(
        min_length=2, max_length=2
    )
    byte_unknown_report_numbers: tuple[Literal[69, 153, 169], ...] = Field(
        min_length=3, max_length=3
    )
    opaque_association_report_numbers: tuple[Literal[261, 263], ...] = Field(
        min_length=2, max_length=2
    )
    approved_coverage_claims: tuple[Identifier, ...] = Field(min_length=1)
    prohibited_overclaims: tuple[Identifier, ...] = Field(min_length=1)
    owner_approval_id: Literal["m1-04b-owner-adjudications-v1"]
    owner_approval_sha256: Sha256

    @model_validator(mode="after")
    def require_exact_reviewed_limitations(self) -> Self:
        expected_counts = {
            AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED: 45,
            AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN: 3,
            AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME: 2,
        }
        if self.approved_outcome_counts != expected_counts:
            raise ValueError("reviewed coverage outcomes must be exactly 45/3/2")
        expected_months = tuple(
            f"{year:04d}-{month:02d}"
            for year, start, stop in ((2004, 4, 13), (2005, 1, 13))
            for month in range(start, stop)
        )
        if self.unresolved_historical_months != expected_months:
            raise ValueError("historical months must remain unresolved from 2004-04 to 2005-12")
        if self.historical_unnumbered_lead_years != (2004, 2005):
            raise ValueError("historical leads must remain unnumbered for 2004 and 2005")
        if self.byte_unknown_report_numbers != (69, 153, 169):
            raise ValueError("reports 69, 153, and 169 must remain byte-unknown")
        if self.opaque_association_report_numbers != (261, 263):
            raise ValueError("reports 261 and 263 must retain opaque association uncertainty")
        return self


class CanonicalizationReceipt(StrictModel):
    """Immutable receipt for one reviewed v0.2.0 canonical package."""

    schema_version: Literal["0.2.0"] = REVIEWED_MANIFEST_SCHEMA_VERSION
    task_id: Literal["M1-04C.1"]
    execution_commit: GitCommit
    implementation_tree_sha: GitTreeSha
    manifest_schema_version: Literal["0.2.0"]
    canonical_target_relative_path: Literal["06_validation/m1_corpus_manifest/v0.2.0"]
    candidate_input_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=6)
    review_input_artifacts: tuple[ApprovalFingerprint, ...] = Field(min_length=6)
    discovery_input_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    operational_input_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    owner_approval_artifact: ApprovalFingerprint
    proposed_adjudications_artifact: ApprovalFingerprint
    adjudication_records_artifact: ArtifactFingerprint
    output_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=10)
    record_counts: tuple[tuple[Identifier, int], ...] = Field(min_length=10)
    unresolved_gap_counts: tuple[tuple[Identifier, int], ...]
    deferred_acquisition_count: Literal[237]
    byte_verified_count: Literal[10]
    authoritative_byte_corpus_complete: Literal[False]
    approved_coverage_claims: tuple[Identifier, ...] = Field(min_length=1)
    deterministic_sort_rules: tuple[Identifier, ...] = Field(min_length=1)
    no_network_assertion: Literal[True]
    no_raw_write_assertion: Literal[True]
    write_once_no_overwrite: Literal[True]
    receipt_written_last: Literal[True]

    @model_validator(mode="after")
    def require_unique_output_paths(self) -> Self:
        paths = [item.path for item in self.output_artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("canonical output paths must be unique")
        return self
