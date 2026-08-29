"""Strict additive acquisition v0.2 contracts for comparison-only readiness."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from peru_conflicts.acquisition.models import SafeResponseHeaders
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Identifier, Sha256, StrictModel

GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


def _validate_safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value.strip()
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("path must be a safe repository-relative POSIX path")
    return value


SafeRelativePath = Annotated[str, AfterValidator(_validate_safe_relative_path)]
APPROVED_REPORT_NUMBERS = tuple(range(260, 270))
APPROVED_HOSTS = ("defensoria.gob.pe", "www.defensoria.gob.pe")


class AuthorizationCapabilitiesV2(StrictModel):
    """Closed capabilities for the comparison-only pilot."""

    external_network_comparison: Literal[True]
    operational_ledger_writes: Literal[True]
    raw_staging: Literal[False]
    raw_promotion: Literal[False]
    historical_full_corpus_expansion: Literal[False]


class RedirectPolicyV2(StrictModel):
    """Strict redirect policy bound into owner authorization."""

    max_hops: Literal[5]
    path_policy: Literal["canonical_wire_equivalent_only"]
    approved_host_aliases: tuple[Identifier, ...]
    require_https: Literal[True]
    default_port_only: Literal[True]
    allow_query: Literal[False]

    @model_validator(mode="after")
    def require_exact_hosts(self) -> Self:
        if self.approved_host_aliases != APPROVED_HOSTS:
            raise ValueError("redirect aliases must be the exact reviewed authoritative hosts")
        return self


class DependencyRecordPinV2(StrictModel):
    """One exact installed-wheel RECORD file required by the isolated bootstrap."""

    distribution: Literal[
        "annotated-types",
        "pydantic",
        "pydantic-core",
        "pyyaml",
        "typing-extensions",
        "typing-inspection",
    ]
    record_path: SafeRelativePath
    record_sha256: Sha256

    @model_validator(mode="after")
    def require_record_path(self) -> Self:
        normalized = self.record_path.casefold().replace("_", "-")
        distribution = self.distribution.casefold().replace("_", "-")
        if not normalized.endswith(".dist-info/record") or not normalized.startswith(distribution):
            raise ValueError("dependency RECORD path does not match its distribution")
        return self


class StorageNamespaceMarkerV2(StrictModel):
    """Canonical inert marker that identifies one approved manifest namespace."""

    schema_version: Literal["0.2.0"]
    namespace_id: Identifier
    owner_nonce_sha256: Sha256


def marker_bytes(marker: StorageNamespaceMarkerV2) -> bytes:
    """Return canonical marker bytes, including the required final LF."""

    return canonical_json_bytes(marker.model_dump(mode="json")) + b"\n"


class NetworkAuthorizationArtifactV2(StrictModel):
    """Owner-reviewed grant for one exact comparison-only run and resumptions."""

    schema_version: Literal["0.2.0"]
    authorization_id: Identifier
    authorization_status: Literal["authorized"]
    scope: Literal["m1_03b_reports_260_269_compare_only"]
    plan_id: Identifier
    plan_file_sha256: Sha256
    plan_semantic_sha256: Sha256
    ordered_target_set_sha256: Sha256
    plan_limits_sha256: Sha256
    protected_source_receipt_path: Literal["docs/source_integrity_receipt_m1_03b1.md"]
    protected_source_receipt_git_commit: GitCommit
    protected_source_receipt_sha256: Sha256
    execution_git_commit: GitCommit
    execution_tree_manifest_sha256: Sha256
    execution_tree_sha256: Sha256
    dependency_records: tuple[DependencyRecordPinV2, ...]
    approved_report_numbers: tuple[int, ...]
    approved_hosts: tuple[Identifier, ...]
    capabilities: AuthorizationCapabilitiesV2
    redirect_policy: RedirectPolicyV2
    storage_namespace_marker: StorageNamespaceMarkerV2
    storage_namespace_marker_sha256: Sha256
    data_root_identity_sha256: Sha256
    execution_host_identity_sha256: Sha256
    approved_by: Identifier
    approved_at: datetime
    reuse_policy: Literal["one_shot_same_run_resume_only"]

    @field_validator("approved_at")
    @classmethod
    def require_aware_approval_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization approval time must include a timezone")
        return value

    @model_validator(mode="after")
    def require_exact_scope(self) -> Self:
        if self.approved_report_numbers != APPROVED_REPORT_NUMBERS:
            raise ValueError("authorization must contain exactly reports 260 through 269")
        if self.approved_hosts != APPROVED_HOSTS:
            raise ValueError("authorization must contain the exact reviewed hosts")
        dependency_names = tuple(record.distribution for record in self.dependency_records)
        expected_dependencies = (
            "annotated-types",
            "pydantic",
            "pydantic-core",
            "pyyaml",
            "typing-extensions",
            "typing-inspection",
        )
        if dependency_names != expected_dependencies:
            raise ValueError("authorization must pin the exact frozen runtime dependency set")
        observed_marker_sha = hashlib.sha256(
            marker_bytes(self.storage_namespace_marker)
        ).hexdigest()
        if observed_marker_sha != self.storage_namespace_marker_sha256:
            raise ValueError("storage namespace marker bytes do not match their pinned SHA-256")
        return self


def authorization_registry_core_sha256(artifact: NetworkAuthorizationArtifactV2) -> str:
    """Hash every semantic field, including the reviewed execution commit."""

    payload = artifact.model_dump(mode="json")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class AuthorizationRegistryGrantV2(StrictModel):
    """One exact-byte and semantic owner grant independently pinned by protected main."""

    authorization_id: Identifier
    artifact_sha256: Sha256
    artifact_core_sha256: Sha256


class AuthorizationRegistryV2(StrictModel):
    """Fixed reviewed registry; M1-03B.1 contains no grants."""

    schema_version: Literal["0.2.0"]
    grants: tuple[AuthorizationRegistryGrantV2, ...]

    @model_validator(mode="after")
    def require_unique_sorted_grants(self) -> Self:
        identifiers = tuple(grant.authorization_id for grant in self.grants)
        if identifiers != tuple(sorted(identifiers)) or len(set(identifiers)) != len(identifiers):
            raise ValueError("registry grants must be sorted and unique")
        return self


class ExecutionTreeEntryV2(StrictModel):
    """One exact executable input."""

    path: SafeRelativePath
    sha256: Sha256
    byte_count: int = Field(ge=0)


class ExecutionTreeManifestV2(StrictModel):
    """Closed, ordered manifest of all code/configuration allowed to execute."""

    schema_version: Literal["0.2.0"]
    entries: tuple[ExecutionTreeEntryV2, ...]
    execution_tree_sha256: Sha256

    @staticmethod
    def calculate_tree_sha256(entries: tuple[ExecutionTreeEntryV2, ...]) -> str:
        payload = [entry.model_dump(mode="json") for entry in entries]
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @classmethod
    def from_entries(cls, entries: tuple[ExecutionTreeEntryV2, ...]) -> Self:
        return cls(
            schema_version="0.2.0",
            entries=entries,
            execution_tree_sha256=cls.calculate_tree_sha256(entries),
        )

    @model_validator(mode="after")
    def require_sorted_unique_bound_entries(self) -> Self:
        paths = tuple(entry.path for entry in self.entries)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("execution-tree paths must be sorted and unique")
        if self.execution_tree_sha256 != self.calculate_tree_sha256(self.entries):
            raise ValueError("execution-tree hash does not match the exact entries")
        return self


class DurableRecordBaseV2(StrictModel):
    """Common hash-chain coordinates for one immutable ledger event."""

    schema_version: Literal["0.2.0"]
    record_id: Identifier
    authorization_id: Identifier
    run_id: Identifier
    plan_id: Identifier
    sequence: int = Field(ge=1)
    previous_record_sha256: Sha256 | None
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_aware_record_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ledger timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_chain_origin(self) -> Self:
        if (self.sequence == 1) != (self.previous_record_sha256 is None):
            raise ValueError("only sequence one may omit the previous-record hash")
        return self


class DurableRunOpenedV2(DurableRecordBaseV2):
    record_type: Literal["run_opened"]
    authorization_artifact_sha256: Sha256
    execution_tree_sha256: Sha256
    data_root_identity_sha256: Sha256
    execution_host_identity_sha256: Sha256


class DurableAttemptStartedV2(DurableRecordBaseV2):
    record_type: Literal["attempt_started"]
    attempt_id: Identifier
    attempt_ordinal: int = Field(ge=1, le=60)
    report_number: int = Field(ge=260, le=269)
    request_kind: Literal["robots", "landing_html", "pdf"]
    source_url_sha256: Sha256
    normalized_url: Identifier
    wire_target: Identifier
    reserved_bytes: int = Field(ge=0, le=500_000_000)
    continued_from_attempt_id: Identifier | None = None
    continuation_reason: Literal["redirect", "retry"] | None = None

    @model_validator(mode="after")
    def require_paired_continuation(self) -> Self:
        if (self.continued_from_attempt_id is None) != (self.continuation_reason is None):
            raise ValueError("attempt continuation ID and reason must be paired")
        return self


class DurableAttemptFinishedV2(DurableRecordBaseV2):
    record_type: Literal["attempt_finished"]
    attempt_id: Identifier
    attempt_ordinal: int = Field(ge=1, le=60)
    outcome: Literal[
        "success",
        "redirect",
        "rejected",
        "retryable_failure",
        "interrupted",
        "crash_outcome_unknown",
    ]
    status_code: int | None = Field(default=None, ge=100, le=599)
    accepted_bytes: int | None = Field(default=None, ge=0, le=500_000_000)
    body_sha256: Sha256 | None
    error_code: Identifier | None
    response_headers: SafeResponseHeaders | None

    @model_validator(mode="after")
    def require_outcome_evidence(self) -> Self:
        if (self.status_code is None) != (self.response_headers is None):
            raise ValueError("HTTP status and selected response headers must be paired")
        if self.outcome == "success":
            if self.status_code is None or not 200 <= self.status_code < 300:
                raise ValueError("successful attempts require a 2xx status")
            if (
                self.accepted_bytes is None
                or self.body_sha256 is None
                or self.error_code is not None
            ):
                raise ValueError("successful attempts require a body hash and no error")
        elif self.outcome == "crash_outcome_unknown":
            if (
                self.accepted_bytes is not None
                or self.status_code is not None
                or self.response_headers is not None
                or self.body_sha256 is not None
                or self.error_code != "process_crash_outcome_unknown"
            ):
                raise ValueError("crash outcomes require explicitly unknown HTTP and byte evidence")
        elif self.accepted_bytes is None or self.error_code is None or self.body_sha256 is not None:
            raise ValueError("non-success attempts require an error and no complete body hash")
        if self.outcome == "redirect" and (
            self.response_headers is None or self.response_headers.location_sha256 is None
        ):
            raise ValueError("redirect attempts require sanitized Location evidence")
        return self


class DurableLandingAssociationV2(DurableRecordBaseV2):
    record_type: Literal["landing_association"]
    report_number: int = Field(ge=260, le=269)
    landing_attempt_id: Identifier
    landing_body_sha256: Sha256
    landing_body_bytes: int = Field(ge=1)
    excerpt_sha256: Sha256
    source_span_text: Identifier
    character_start: int = Field(ge=0)
    character_end: int = Field(ge=0)
    byte_start: int | None = Field(default=None, ge=0)
    byte_end: int | None = Field(default=None, ge=0)
    parser_version: Identifier
    reviewed_href_original: Identifier
    reviewed_url_normalized: Identifier
    reviewed_wire_target: Identifier
    candidate_url_sha256s: tuple[Sha256, ...]
    identity_association_status: Literal["visibly_associated", "unresolved_opaque_filename"]

    @model_validator(mode="after")
    def require_ordered_spans(self) -> Self:
        if self.character_end < self.character_start:
            raise ValueError("character span is reversed")
        if (self.byte_start is None) != (self.byte_end is None):
            raise ValueError("byte offsets must be both present or both absent")
        if (
            self.byte_start is not None
            and self.byte_end is not None
            and self.byte_end < self.byte_start
        ):
            raise ValueError("byte span is reversed")
        return self


class DurableByteObjectV2(DurableRecordBaseV2):
    record_type: Literal["byte_object"]
    report_number: int = Field(ge=260, le=269)
    source_attempt_id: Identifier
    observed_sha256: Sha256
    observed_bytes: int = Field(ge=1, le=50_000_000)


class DurableComparisonV2(DurableRecordBaseV2):
    record_type: Literal["comparison"]
    report_number: int = Field(ge=260, le=269)
    source_attempt_id: Identifier
    observed_sha256: Sha256
    observed_bytes: int = Field(ge=1, le=50_000_000)
    expected_source_sha256: Sha256
    source_sha256_before: Sha256
    source_sha256_after: Sha256
    relationship: Literal["identical_bytes", "different_bytes_association_unresolved"]
    disposition: Literal["identical_no_duplicate", "stop_for_review"]

    @model_validator(mode="after")
    def require_comparison_consistency(self) -> Self:
        if self.source_sha256_before != self.source_sha256_after:
            raise ValueError("protected local source changed during comparison")
        identical = self.observed_sha256 == self.expected_source_sha256
        if identical != (self.relationship == "identical_bytes"):
            raise ValueError("byte relationship contradicts the compared hashes")
        if identical != (self.disposition == "identical_no_duplicate"):
            raise ValueError("disposition contradicts the compared hashes")
        return self


class DurableCleanupV2(DurableRecordBaseV2):
    record_type: Literal["cleanup"]
    report_number: int = Field(ge=260, le=269)
    attempt_id: Identifier
    cleanup_status: Literal["removed", "already_absent"]


class DurableTemporaryRecoveryV2(DurableRecordBaseV2):
    record_type: Literal["temporary_recovery"]
    report_number: int = Field(ge=260, le=269)
    attempt_id: Identifier
    object_state: Literal["partial", "complete"]
    recovery_action: Literal[
        "removed_partial",
        "observed_unaccepted_complete",
        "removed_unaccepted_complete",
        "accepted_complete_for_resume",
    ]
    observed_bytes: int | None = Field(default=None, ge=1, le=50_000_000)
    observed_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def require_complete_evidence(self) -> Self:
        accepts_complete = self.recovery_action == "accepted_complete_for_resume"
        observes_complete = self.recovery_action == "observed_unaccepted_complete"
        removes_complete = self.recovery_action == "removed_unaccepted_complete"
        if (accepts_complete or observes_complete or removes_complete) != (
            self.object_state == "complete"
        ):
            raise ValueError("temporary recovery state and action differ")
        if (accepts_complete or observes_complete) != (
            self.observed_bytes is not None and self.observed_sha256 is not None
        ):
            raise ValueError("complete observation actions require exact byte evidence")
        return self


class DurableSourceRehashV2(DurableRecordBaseV2):
    record_type: Literal["source_rehash"]
    report_number: int = Field(ge=260, le=269)
    expected_sha256: Sha256
    observed_sha256: Sha256
    phase: Literal["pre_network", "comparison_before", "comparison_after", "terminal"]


class DurableIssueV2(DurableRecordBaseV2):
    record_type: Literal["issue"]
    report_number: int | None = Field(default=None, ge=260, le=269)
    classification: Literal[
        "PARSER_ERROR",
        "MISSING_EVIDENCE",
        "AMBIGUITY",
        "SOURCE_INCONSISTENCY",
        "POLICY_VIOLATION",
        "INFRASTRUCTURE_FAILURE",
    ]
    reason_code: Identifier
    evidence_sha256: Sha256 | None = None


class DurableRunTerminalV2(DurableRecordBaseV2):
    record_type: Literal["run_terminal"]
    terminal_status: Literal["completed", "abandoned", "stop_for_review"]
    reason_code: Identifier


DurableLedgerRecordV2 = Annotated[
    DurableRunOpenedV2
    | DurableAttemptStartedV2
    | DurableAttemptFinishedV2
    | DurableLandingAssociationV2
    | DurableByteObjectV2
    | DurableComparisonV2
    | DurableCleanupV2
    | DurableTemporaryRecoveryV2
    | DurableSourceRehashV2
    | DurableIssueV2
    | DurableRunTerminalV2,
    Field(discriminator="record_type"),
]


class UseIndexRecordBaseV2(StrictModel):
    """Common hash-chain coordinates for the global authorization-use index."""

    schema_version: Literal["0.2.0"]
    index_sequence: int = Field(ge=1)
    previous_index_sha256: Sha256 | None
    authorization_id: Identifier
    run_id: Identifier
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_aware_index_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("use-index timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_index_chain_origin(self) -> Self:
        if (self.index_sequence == 1) != (self.previous_index_sha256 is None):
            raise ValueError("only use-index sequence one may omit the previous hash")
        return self


class UseIndexClaimV2(UseIndexRecordBaseV2):
    record_type: Literal["authorization_claim"]
    plan_id: Identifier
    authorization_artifact_sha256: Sha256
    storage_namespace_marker_sha256: Sha256
    data_root_identity_sha256: Sha256
    execution_host_identity_sha256: Sha256


class UseIndexLedgerCreatedV2(UseIndexRecordBaseV2):
    record_type: Literal["ledger_created"]
    ledger_name: Identifier


class UseIndexLedgerAnchorV2(UseIndexRecordBaseV2):
    record_type: Literal["ledger_anchor"]
    ledger_sequence: int = Field(ge=1)
    ledger_head_sha256: Sha256


class UseIndexTerminalV2(UseIndexRecordBaseV2):
    record_type: Literal["authorization_terminal"]
    terminal_status: Literal["completed", "abandoned", "stop_for_review"]
    ledger_sequence: int = Field(ge=1)
    ledger_head_sha256: Sha256


UseIndexRecordV2 = Annotated[
    UseIndexClaimV2 | UseIndexLedgerCreatedV2 | UseIndexLedgerAnchorV2 | UseIndexTerminalV2,
    Field(discriminator="record_type"),
]
