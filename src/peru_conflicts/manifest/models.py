"""Strict technical records for M1 corpus-manifest reconciliation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from peru_conflicts.models.common import Identifier, ReferencePeriod, Sha256, StrictModel

MANIFEST_SCHEMA_VERSION = "0.1.0"
GitCommit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]


class AcquisitionState(StrEnum):
    """Evidence-backed acquisition state for one observed report identity."""

    OFFICIAL_SOURCE_DISCOVERED = "official_source_discovered"
    BYTE_VERIFIED_IDENTICAL = "byte_verified_identical"


class AssociationStatus(StrEnum):
    """Strength of the reviewed direct-file/report association."""

    NOT_APPLICABLE = "not_applicable"
    VISIBLY_ASSOCIATED = "visibly_associated"
    UNRESOLVED_OPAQUE_FILENAME = "unresolved_opaque_filename"


class ReviewStatus(StrEnum):
    """Review state of a candidate technical record."""

    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class CandidateCompletenessStatus(StrEnum):
    """M1-04A cannot assert final corpus completeness."""

    CANDIDATE_REQUIRES_HUMAN_REVIEW = "candidate_requires_human_review"


class EdgeRelationType(StrEnum):
    """Supported source/byte relationships without speculative collapsing."""

    EXACT_IDENTICAL_BYTES = "exact_identical_bytes"
    MULTIPLE_OFFICIAL_URLS_ONE_OBSERVED_IDENTITY = "multiple_official_urls_one_observed_identity"
    CANDIDATE_SAME_REPORT_WITHOUT_BYTE_EVIDENCE = "candidate_same_report_without_byte_evidence"
    DIFFERENT_BYTES_REQUIRING_REVIEW = "different_bytes_requiring_review"
    UNRESOLVED_RELATION = "unresolved_relation"


class GapDimension(StrEnum):
    """Dimension in which evidence or expected coverage remains unresolved."""

    REFERENCE_MONTH = "reference_month"
    REPORT_NUMBER = "report_number"
    SOURCE_EVIDENCE = "source_evidence"
    BYTE_ACQUISITION = "byte_acquisition"
    IDENTITY_AMBIGUITY = "identity_ambiguity"
    VERSION_AMBIGUITY = "version_ambiguity"


class GapClassification(StrEnum):
    """Scientifically distinct unresolved candidate conditions."""

    HISTORICAL_MONTH_UNRESOLVED = "historical_month_unresolved"
    UNOBSERVED_REPORT_NUMBER = "unobserved_report_number"
    HISTORICAL_UNNUMBERED_SOURCE_LEAD = "historical_unnumbered_source_lead"
    BYTE_ACQUISITION_NOT_ESTABLISHED = "byte_acquisition_not_established"
    OPAQUE_DIRECT_FILE_ASSOCIATION = "opaque_direct_file_association"
    MULTIPLE_DIRECT_URL_BYTES_UNKNOWN = "multiple_direct_url_bytes_unknown"
    SOURCE_METADATA_REQUIRES_REVIEW = "source_metadata_requires_review"


class ObservationEvidenceStatus(StrEnum):
    """Whether evidence resolves the expectation represented by a gap."""

    UNOBSERVED = "unobserved"
    LEAD_ONLY = "lead_only"
    PARTIAL = "partial"
    CONFLICTING = "conflicting"
    NOT_ACQUIRED = "not_acquired"
    AMBIGUOUS = "ambiguous"


class GapDisposition(StrEnum):
    """Candidate-only action state; none adjudicates the gap."""

    PENDING_HUMAN_REVIEW = "pending_human_review"
    RETAIN_AS_UNNUMBERED_LEAD = "retain_as_unnumbered_lead"
    DEFERRED_FUTURE_ACQUISITION = "deferred_future_acquisition"


class ArtifactFingerprint(StrictModel):
    """Portable path and immutable byte fingerprint for one input/output artifact."""

    artifact_role: Identifier
    path: Identifier
    bytes: int = Field(ge=0)
    sha256: Sha256
    record_count: int | None = Field(default=None, ge=0)


class EvidenceReference(StrictModel):
    """One run-qualified discovery evidence reference."""

    discovery_run_id: Identifier
    discovery_record_id: Identifier
    evidence_id: Identifier


class SourceTitleObservation(StrictModel):
    """One source-original report title and the evidence that displayed it."""

    title_original: Identifier
    evidence_refs: tuple[EvidenceReference, ...] = Field(min_length=1)


class CorpusReportManifestEntry(StrictModel):
    """One canonical candidate identity for an observed numbered report."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    manifest_report_id: Identifier
    source_institution: Literal["Defensoría del Pueblo"]
    source_series: Literal["Reporte Mensual de Conflictos Sociales"]
    report_number: int = Field(ge=1)
    reference_month: ReferencePeriod
    source_titles: tuple[SourceTitleObservation, ...] = ()
    preferred_title_original: str | None = None
    preferred_title_evidence_refs: tuple[EvidenceReference, ...] = ()
    identity_evidence_refs: tuple[EvidenceReference, ...] = Field(min_length=2)
    discovery_record_refs: tuple[Identifier, ...] = Field(min_length=1)
    source_observation_record_ids: tuple[Identifier, ...] = Field(min_length=1)
    acquisition_state: AcquisitionState
    known_byte_version_count: int = Field(ge=0)
    preferred_protected_local_path: str | None = None
    association_status: AssociationStatus
    review_status: ReviewStatus
    gap_ids: tuple[Identifier, ...] = ()
    discovery_run_ids: tuple[Identifier, ...] = Field(min_length=1)
    input_artifact_fingerprints: tuple[ArtifactFingerprint, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_supported_preferred_title_and_acquisition(self) -> Self:
        available = {item.title_original for item in self.source_titles}
        if self.preferred_title_original is not None:
            if self.preferred_title_original not in available:
                raise ValueError("preferred title must be one of the source titles")
            if not self.preferred_title_evidence_refs:
                raise ValueError("preferred title requires source evidence")
        elif self.preferred_title_evidence_refs:
            raise ValueError("preferred title evidence requires a preferred title")

        if self.acquisition_state is AcquisitionState.BYTE_VERIFIED_IDENTICAL:
            if self.known_byte_version_count < 1:
                raise ValueError("byte-verified entry requires one or more byte versions")
            if self.preferred_protected_local_path is None:
                raise ValueError("byte-verified entry requires a protected local path")
        elif self.known_byte_version_count or self.preferred_protected_local_path is not None:
            raise ValueError("discovery-only entry cannot claim a protected byte version")
        return self


class SourceObservationRecord(StrictModel):
    """One URL observation within one run-qualified discovery occurrence."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    source_observation_record_id: Identifier
    discovery_run_id: Identifier
    discovery_record_id: Identifier
    original_observation_id: Identifier
    manifest_report_id: Identifier | None
    source_url_original: Identifier
    normalized_transport_url: Identifier | None
    url_role: Identifier
    containing_source_url: Identifier
    containing_surface_role: Identifier
    source_page_title_original: str | None
    entry_title_original: str | None
    entry_publication_date_original: str | None
    entry_description_original: str | None
    observed_report_number: int | None = Field(default=None, ge=1)
    observed_reference_month: ReferencePeriod | None
    identity_evidence_refs: tuple[EvidenceReference, ...] = ()
    relation_ids: tuple[Identifier, ...] = ()
    discovery_issue_ids: tuple[Identifier, ...] = ()
    captured_at: AwareDatetime
    uncertainty_notes: tuple[Identifier, ...] = ()


class ByteVersionRecord(StrictModel):
    """One authoritative, actually observed byte object."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    byte_version_id: Identifier
    manifest_report_id: Identifier
    report_number: int = Field(ge=1)
    bytes: int = Field(gt=0)
    sha256: Sha256
    protected_local_path: Identifier
    acquisition_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    official_remote_observation_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    first_seen_run_id: Identifier
    disposition: Literal["identical_no_duplicate"]
    review_status: Literal[ReviewStatus.VERIFIED]
    association_status: AssociationStatus
    comparison_authorization_spent: Literal[True]

    @model_validator(mode="after")
    def bind_identifier_to_sha256(self) -> Self:
        if self.byte_version_id != f"byte-version-{self.sha256}":
            raise ValueError("byte-version ID must be derived from the exact SHA-256")
        return self


class VersionSourceRelationshipEdge(StrictModel):
    """One evidence-bounded relationship among observations and byte versions."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    edge_id: Identifier
    manifest_report_id: Identifier
    relation_type: EdgeRelationType
    source_observation_record_ids: tuple[Identifier, ...]
    byte_version_ids: tuple[Identifier, ...]
    acquisition_evidence_ids: tuple[Identifier, ...]
    rationale: Identifier
    review_status: ReviewStatus

    @model_validator(mode="after")
    def require_relation_specific_evidence(self) -> Self:
        if self.relation_type is EdgeRelationType.EXACT_IDENTICAL_BYTES:
            if not self.byte_version_ids or not self.acquisition_evidence_ids:
                raise ValueError("exact byte relation requires byte and acquisition evidence")
        elif self.relation_type is EdgeRelationType.MULTIPLE_OFFICIAL_URLS_ONE_OBSERVED_IDENTITY:
            if len(set(self.source_observation_record_ids)) < 2:
                raise ValueError("multiple-URL relation requires at least two source observations")
            if self.byte_version_ids or self.acquisition_evidence_ids:
                raise ValueError("multiple-URL relation cannot assert byte identity")
        elif self.relation_type is EdgeRelationType.CANDIDATE_SAME_REPORT_WITHOUT_BYTE_EVIDENCE:
            if len(set(self.source_observation_record_ids)) < 2:
                raise ValueError("candidate same-report relation requires two source observations")
            if self.byte_version_ids or self.acquisition_evidence_ids:
                raise ValueError("pre-hash candidate relation cannot assert byte identity")
        elif (
            self.relation_type is EdgeRelationType.DIFFERENT_BYTES_REQUIRING_REVIEW
            and len(set(self.byte_version_ids)) < 2
        ):
            raise ValueError("different-byte relation requires at least two byte versions")
        return self


class GapRegisterEntry(StrictModel):
    """One unresolved research expectation or evidence limitation."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    gap_id: Identifier
    gap_dimension: GapDimension
    expected_value: Identifier
    observed_evidence_status: ObservationEvidenceStatus
    classification: GapClassification
    evidence_refs: tuple[Identifier, ...]
    rationale: Identifier
    manual_review_required: bool
    disposition: GapDisposition
    related_manifest_report_ids: tuple[Identifier, ...]


class CoverageReport(StrictModel):
    """Deterministic M1-04A summary that cannot claim final completeness."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    research_coverage_start: ReferencePeriod
    observation_cutoff: ReferencePeriod
    observed_numbered_report_min: int = Field(ge=1)
    observed_numbered_report_max: int = Field(ge=1)
    observed_numbered_report_count: int = Field(ge=0)
    observed_reference_month_min: ReferencePeriod
    observed_reference_month_max: ReferencePeriod
    observed_reference_month_count: int = Field(ge=0)
    report_to_month_conflict_count: int = Field(ge=0)
    month_to_report_conflict_count: int = Field(ge=0)
    historical_bundle_lead_years: tuple[int, ...]
    reports_1_22_status: Literal["unobserved_report_number_hypotheses"]
    byte_verified_report_min: int | None = Field(default=None, ge=1)
    byte_verified_report_max: int | None = Field(default=None, ge=1)
    byte_verified_report_count: int = Field(ge=0)
    unresolved_gap_counts: tuple[tuple[GapClassification, int], ...]
    candidate_completeness_status: Literal[
        CandidateCompletenessStatus.CANDIDATE_REQUIRES_HUMAN_REVIEW
    ]
    human_review_required: Literal[True]
    input_artifact_fingerprints: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    implementation_git_sha: GitCommit
    manifest_schema_version: Literal["0.1.0"]
    materializer_version: Identifier

    @model_validator(mode="after")
    def require_ordered_ranges_and_gap_counts(self) -> Self:
        if self.observed_numbered_report_min > self.observed_numbered_report_max:
            raise ValueError("observed report range is reversed")
        if self.observed_reference_month_min > self.observed_reference_month_max:
            raise ValueError("observed month range is reversed")
        if (self.byte_verified_report_min is None) != (self.byte_verified_report_max is None):
            raise ValueError("byte-verified report range must be wholly present or absent")
        if self.byte_verified_report_count == 0 and self.byte_verified_report_min is not None:
            raise ValueError("empty byte-verified coverage cannot claim a report range")
        if self.byte_verified_report_count > 0 and self.byte_verified_report_min is None:
            raise ValueError("byte-verified coverage requires a report range")
        if (
            self.byte_verified_report_min is not None
            and self.byte_verified_report_max is not None
            and self.byte_verified_report_min > self.byte_verified_report_max
        ):
            raise ValueError("byte-verified report range is reversed")
        if any(count < 0 for _, count in self.unresolved_gap_counts):
            raise ValueError("gap counts cannot be negative")
        return self


class MaterializationReceipt(StrictModel):
    """Immutable local receipt for one candidate-only materialization."""

    schema_version: Literal["0.1.0"] = MANIFEST_SCHEMA_VERSION
    task_id: Literal["M1-04A"]
    repository_base_sha: GitCommit
    repository_head_sha: GitCommit
    implementation_git_sha: GitCommit
    manifest_schema_version: Literal["0.1.0"]
    discovery_run_ids: tuple[Identifier, ...] = Field(min_length=1)
    input_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    operational_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    protected_source_receipt_refs: tuple[Identifier, ...] = Field(min_length=1)
    output_artifacts: tuple[ArtifactFingerprint, ...] = Field(min_length=1)
    record_counts: tuple[tuple[Identifier, int], ...] = Field(min_length=1)
    observed_numbered_report_count: int = Field(ge=0)
    observed_numbered_report_min: int = Field(ge=1)
    observed_numbered_report_max: int = Field(ge=1)
    observed_reference_month_count: int = Field(ge=0)
    observed_reference_month_min: ReferencePeriod
    observed_reference_month_max: ReferencePeriod
    gap_counts: tuple[tuple[GapClassification, int], ...]
    byte_verified_count: int = Field(ge=0)
    unresolved_review_count: int = Field(ge=0)
    deterministic_sort_rules: tuple[Identifier, ...] = Field(min_length=1)
    no_network_assertion: Literal[True]
    no_raw_write_assertion: Literal[True]
    no_canonical_database_write_assertion: Literal[True]
