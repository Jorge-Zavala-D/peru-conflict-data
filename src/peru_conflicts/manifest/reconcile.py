"""Deterministic, evidence-bounded M1 corpus-manifest reconciliation."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass

from peru_conflicts.discovery.models import IdentityEvidenceType, UrlRole
from peru_conflicts.discovery.policy import normalize_url
from peru_conflicts.manifest.evidence import AcquisitionClosure, DiscoveryEvidence
from peru_conflicts.manifest.models import (
    AcquisitionState,
    AssociationStatus,
    ByteVersionRecord,
    CandidateCompletenessStatus,
    CorpusReportManifestEntry,
    CoverageReport,
    EdgeRelationType,
    EvidenceReference,
    GapClassification,
    GapDimension,
    GapDisposition,
    GapRegisterEntry,
    ObservationEvidenceStatus,
    ReviewStatus,
    SourceObservationRecord,
    SourceTitleObservation,
    VersionSourceRelationshipEdge,
)

MATERIALIZER_VERSION = "m1-04a-v2"


class ReconciliationError(RuntimeError):
    """Discovery or acquisition evidence cannot be reconciled deterministically."""


@dataclass(frozen=True, slots=True)
class ReconciliationContext:
    repository_base_sha: str
    implementation_tree_sha: str


@dataclass(frozen=True, slots=True)
class CandidatePackage:
    manifest: tuple[CorpusReportManifestEntry, ...]
    source_observations: tuple[SourceObservationRecord, ...]
    byte_versions: tuple[ByteVersionRecord, ...]
    version_edges: tuple[VersionSourceRelationshipEdge, ...]
    gaps: tuple[GapRegisterEntry, ...]
    coverage: CoverageReport


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:24]}"


def _manifest_id(report_number: int) -> str:
    return f"manifest-report-{report_number}"


def _evidence_ref(run_id: str, record_id: str, evidence_id: str) -> EvidenceReference:
    return EvidenceReference(
        discovery_run_id=run_id,
        discovery_record_id=record_id,
        evidence_id=evidence_id,
    )


def _source_observation_id(
    run_id: str,
    source_line: int,
    discovery_record_id: str,
    observation_id: str,
) -> str:
    return _stable_id(
        "source-observation",
        run_id,
        source_line,
        discovery_record_id,
        observation_id,
    )


def _source_observations(
    discovery: DiscoveryEvidence,
    report_months: dict[int, str],
) -> tuple[SourceObservationRecord, ...]:
    result: list[SourceObservationRecord] = []
    for occurrence in discovery.occurrences:
        record = occurrence.record
        manifest_report_id = (
            _manifest_id(record.candidate_report_number)
            if record.candidate_report_number in report_months
            else None
        )
        first = record.url_observations[0]
        evidence_by_observation: dict[str, list[EvidenceReference]] = defaultdict(list)
        for evidence in record.identity_evidence:
            evidence_by_observation[evidence.source_observation_id].append(
                _evidence_ref(occurrence.run_id, record.discovery_record_id, evidence.evidence_id)
            )
        relation_by_observation: dict[str, list[str]] = defaultdict(list)
        for relation in record.candidate_source_relations:
            relation_by_observation[relation.source_observation_id].append(relation.relation_id)
            relation_by_observation[relation.related_observation_id].append(relation.relation_id)
        issue_by_observation: dict[str, list[str]] = defaultdict(list)
        for issue in record.discovery_issues:
            for observation_id in issue.related_observation_ids:
                issue_by_observation[observation_id].append(issue.issue_id)

        for observation in record.url_observations:
            result.append(
                SourceObservationRecord(
                    source_observation_record_id=_source_observation_id(
                        occurrence.run_id,
                        occurrence.source_line,
                        record.discovery_record_id,
                        observation.observation_id,
                    ),
                    discovery_run_id=occurrence.run_id,
                    discovery_record_id=record.discovery_record_id,
                    original_observation_id=observation.observation_id,
                    manifest_report_id=manifest_report_id,
                    source_url_original=observation.url,
                    normalized_transport_url=normalize_url(observation.url),
                    url_role=observation.role.value,
                    containing_source_url=first.url,
                    containing_surface_role=first.role.value,
                    source_page_title_original=record.source_page_title_original,
                    entry_title_original=record.entry_title_original,
                    entry_publication_date_original=record.entry_publication_date_original,
                    entry_description_original=record.entry_description_original,
                    observed_report_number=record.candidate_report_number,
                    observed_reference_month=record.candidate_reference_period,
                    identity_evidence_refs=tuple(
                        sorted(
                            evidence_by_observation[observation.observation_id],
                            key=lambda item: item.evidence_id,
                        )
                    ),
                    relation_ids=tuple(sorted(relation_by_observation[observation.observation_id])),
                    discovery_issue_ids=tuple(
                        sorted(issue_by_observation[observation.observation_id])
                    ),
                    captured_at=observation.captured_at,
                    uncertainty_notes=record.uncertainty_notes
                    + ((observation.uncertainty_note,) if observation.uncertainty_note else ()),
                )
            )
    return tuple(sorted(result, key=lambda item: item.source_observation_record_id))


def _identity_maps(discovery: DiscoveryEvidence) -> tuple[dict[int, str], dict[str, int]]:
    number_to_months: dict[int, set[str]] = defaultdict(set)
    month_to_numbers: dict[str, set[int]] = defaultdict(set)
    for occurrence in discovery.occurrences:
        record = occurrence.record
        if record.candidate_report_number is None or record.candidate_reference_period is None:
            continue
        number_to_months[record.candidate_report_number].add(record.candidate_reference_period)
        month_to_numbers[record.candidate_reference_period].add(record.candidate_report_number)
    if any(len(months) > 1 for months in number_to_months.values()):
        raise ReconciliationError("report number maps to multiple months")
    if any(len(numbers) > 1 for numbers in month_to_numbers.values()):
        raise ReconciliationError("reference month maps to multiple reports")
    number_to_month = {number: next(iter(months)) for number, months in number_to_months.items()}
    month_to_number = {month: next(iter(numbers)) for month, numbers in month_to_numbers.items()}
    return number_to_month, month_to_number


def _historical_months() -> tuple[str, ...]:
    return tuple(
        f"{year:04d}-{month:02d}"
        for year, start, end in ((2004, 4, 12), (2005, 1, 12))
        for month in range(start, end + 1)
    )


def reconcile_manifest(
    discovery: DiscoveryEvidence,
    acquisition: AcquisitionClosure,
    context: ReconciliationContext,
) -> CandidatePackage:
    """Reconcile frozen M1 evidence without inventing identities or byte equivalence."""

    if not acquisition.authorization_spent:
        raise ReconciliationError("acquisition evidence is not a spent terminal authorization")
    number_to_month, _ = _identity_maps(discovery)
    observations = _source_observations(discovery, number_to_month)
    observations_by_report: dict[int, list[SourceObservationRecord]] = defaultdict(list)
    for observation in observations:
        if observation.observed_report_number in number_to_month:
            observations_by_report[observation.observed_report_number].append(observation)

    acquisition_by_report = {item.report_number: item for item in acquisition.reports}
    byte_versions: list[ByteVersionRecord] = []
    version_edges: list[VersionSourceRelationshipEdge] = []
    gaps: list[GapRegisterEntry] = []

    for occurrence in discovery.occurrences:
        record = occurrence.record
        report_number = record.candidate_report_number
        if report_number not in number_to_month:
            continue
        for relation in record.candidate_source_relations:
            version_edges.append(
                VersionSourceRelationshipEdge(
                    edge_id=_stable_id(
                        "edge-candidate-source",
                        occurrence.run_id,
                        occurrence.source_line,
                        record.discovery_record_id,
                        relation.relation_id,
                    ),
                    manifest_report_id=_manifest_id(report_number),
                    relation_type=EdgeRelationType.CANDIDATE_SAME_REPORT_WITHOUT_BYTE_EVIDENCE,
                    source_observation_record_ids=(
                        _source_observation_id(
                            occurrence.run_id,
                            occurrence.source_line,
                            record.discovery_record_id,
                            relation.source_observation_id,
                        ),
                        _source_observation_id(
                            occurrence.run_id,
                            occurrence.source_line,
                            record.discovery_record_id,
                            relation.related_observation_id,
                        ),
                    ),
                    byte_version_ids=(),
                    acquisition_evidence_ids=(),
                    rationale=relation.rationale,
                    review_status=ReviewStatus.CANDIDATE,
                )
            )

    for month in _historical_months():
        gaps.append(
            GapRegisterEntry(
                gap_id=f"gap-reference-month-{month}",
                gap_dimension=GapDimension.REFERENCE_MONTH,
                expected_value=month,
                observed_evidence_status=ObservationEvidenceStatus.UNOBSERVED,
                classification=GapClassification.HISTORICAL_MONTH_UNRESOLVED,
                evidence_refs=(),
                rationale=(
                    "Research coverage starts in April 2004, but no qualifying monthly "
                    "identity was observed."
                ),
                manual_review_required=True,
                disposition=GapDisposition.PENDING_HUMAN_REVIEW,
                related_manifest_report_ids=(),
            )
        )
    for report_number in range(1, 23):
        gaps.append(
            GapRegisterEntry(
                gap_id=f"gap-report-number-{report_number}",
                gap_dimension=GapDimension.REPORT_NUMBER,
                expected_value=str(report_number),
                observed_evidence_status=ObservationEvidenceStatus.UNOBSERVED,
                classification=GapClassification.UNOBSERVED_REPORT_NUMBER,
                evidence_refs=(),
                rationale=(
                    "The report number is a coverage hypothesis, not an observed report identity."
                ),
                manual_review_required=True,
                disposition=GapDisposition.PENDING_HUMAN_REVIEW,
                related_manifest_report_ids=(),
            )
        )

    unnumbered_by_year: dict[int, list[str]] = defaultdict(list)
    for occurrence in discovery.occurrences:
        record = occurrence.record
        if record.candidate_report_number is not None:
            continue
        searchable = " ".join(
            value
            for value in (
                record.source_page_title_original,
                record.entry_title_original,
                record.entry_description_original,
            )
            if value
        )
        for year in (2004, 2005):
            if str(year) in searchable:
                unnumbered_by_year[year].append(f"{occurrence.run_id}:{record.discovery_record_id}")
    for year, refs in sorted(unnumbered_by_year.items()):
        gaps.append(
            GapRegisterEntry(
                gap_id=f"gap-historical-unnumbered-lead-{year}",
                gap_dimension=GapDimension.SOURCE_EVIDENCE,
                expected_value=str(year),
                observed_evidence_status=ObservationEvidenceStatus.LEAD_ONLY,
                classification=GapClassification.HISTORICAL_UNNUMBERED_SOURCE_LEAD,
                evidence_refs=tuple(sorted(set(refs))),
                rationale=(
                    "Official historical source evidence exists without a qualifying numbered "
                    "monthly identity."
                ),
                manual_review_required=True,
                disposition=GapDisposition.RETAIN_AS_UNNUMBERED_LEAD,
                related_manifest_report_ids=(),
            )
        )

    for report_number, _month in sorted(number_to_month.items()):
        manifest_report_id = _manifest_id(report_number)
        report_observations = observations_by_report[report_number]
        direct = [item for item in report_observations if item.url_role == UrlRole.DIRECT_DOWNLOAD]
        distinct_direct = {item.normalized_transport_url for item in direct}
        if len(distinct_direct) > 1:
            version_edges.append(
                VersionSourceRelationshipEdge(
                    edge_id=f"edge-multiple-official-urls-{report_number}",
                    manifest_report_id=manifest_report_id,
                    relation_type=EdgeRelationType.MULTIPLE_OFFICIAL_URLS_ONE_OBSERVED_IDENTITY,
                    source_observation_record_ids=tuple(
                        sorted(item.source_observation_record_id for item in direct)
                    ),
                    byte_version_ids=(),
                    acquisition_evidence_ids=(),
                    rationale=(
                        "Multiple distinct official direct URLs were observed for one report "
                        "identity; byte equivalence is unknown."
                    ),
                    review_status=ReviewStatus.REQUIRES_HUMAN_REVIEW,
                )
            )
            gaps.append(
                GapRegisterEntry(
                    gap_id=f"gap-multiple-direct-url-bytes-{report_number}",
                    gap_dimension=GapDimension.VERSION_AMBIGUITY,
                    expected_value=str(report_number),
                    observed_evidence_status=ObservationEvidenceStatus.AMBIGUOUS,
                    classification=GapClassification.MULTIPLE_DIRECT_URL_BYTES_UNKNOWN,
                    evidence_refs=tuple(
                        sorted(item.source_observation_record_id for item in direct)
                    ),
                    rationale=(
                        "Distinct official direct URLs cannot be collapsed without acquired "
                        "byte evidence."
                    ),
                    manual_review_required=True,
                    disposition=GapDisposition.PENDING_HUMAN_REVIEW,
                    related_manifest_report_ids=(manifest_report_id,),
                )
            )

        completed = acquisition_by_report.get(report_number)
        if completed is None:
            gaps.append(
                GapRegisterEntry(
                    gap_id=f"gap-byte-acquisition-{report_number}",
                    gap_dimension=GapDimension.BYTE_ACQUISITION,
                    expected_value=str(report_number),
                    observed_evidence_status=ObservationEvidenceStatus.NOT_ACQUIRED,
                    classification=GapClassification.BYTE_ACQUISITION_NOT_ESTABLISHED,
                    evidence_refs=(),
                    rationale=(
                        "Discovery evidence does not establish an authoritative acquired byte "
                        "object."
                    ),
                    manual_review_required=False,
                    disposition=GapDisposition.DEFERRED_FUTURE_ACQUISITION,
                    related_manifest_report_ids=(manifest_report_id,),
                )
            )
        else:
            byte_version_id = f"byte-version-{completed.protected.sha256}"
            association = AssociationStatus(completed.association_status)
            byte_versions.append(
                ByteVersionRecord(
                    byte_version_id=byte_version_id,
                    manifest_report_id=manifest_report_id,
                    report_number=report_number,
                    bytes=completed.protected.bytes,
                    sha256=completed.protected.sha256,
                    protected_local_path=completed.protected.relative_path,
                    acquisition_evidence_ids=completed.acquisition_evidence_ids,
                    official_remote_observation_evidence_ids=(
                        completed.remote_observation_evidence_ids
                    ),
                    first_seen_run_id=acquisition.run_id,
                    disposition="identical_no_duplicate",
                    review_status=ReviewStatus.VERIFIED,
                    association_status=association,
                    comparison_authorization_spent=True,
                )
            )
            version_edges.append(
                VersionSourceRelationshipEdge(
                    edge_id=f"edge-exact-identical-bytes-{report_number}",
                    manifest_report_id=manifest_report_id,
                    relation_type=EdgeRelationType.EXACT_IDENTICAL_BYTES,
                    source_observation_record_ids=tuple(
                        sorted(item.source_observation_record_id for item in direct)
                    ),
                    byte_version_ids=(byte_version_id,),
                    acquisition_evidence_ids=completed.acquisition_evidence_ids,
                    rationale=(
                        "The authorized remote observation and protected source have exact "
                        "identical SHA-256 bytes."
                    ),
                    review_status=ReviewStatus.VERIFIED,
                )
            )
            if association is AssociationStatus.UNRESOLVED_OPAQUE_FILENAME:
                gaps.append(
                    GapRegisterEntry(
                        gap_id=f"gap-opaque-direct-file-association-{report_number}",
                        gap_dimension=GapDimension.IDENTITY_AMBIGUITY,
                        expected_value=str(report_number),
                        observed_evidence_status=ObservationEvidenceStatus.AMBIGUOUS,
                        classification=GapClassification.OPAQUE_DIRECT_FILE_ASSOCIATION,
                        evidence_refs=completed.remote_observation_evidence_ids,
                        rationale=(
                            "Byte identity is exact, but the official direct filename remains "
                            "opaque."
                        ),
                        manual_review_required=True,
                        disposition=GapDisposition.PENDING_HUMAN_REVIEW,
                        related_manifest_report_ids=(manifest_report_id,),
                    )
                )

    for report_number in sorted(number_to_month):
        title_refs = {
            occurrence.record.entry_title_original: (
                f"{occurrence.run_id}:{occurrence.record.discovery_record_id}"
            )
            for occurrence in discovery.occurrences
            if occurrence.record.candidate_report_number == report_number
            and occurrence.record.entry_title_original
        }
        if len(title_refs) > 1:
            gaps.append(
                GapRegisterEntry(
                    gap_id=f"gap-source-title-review-{report_number}",
                    gap_dimension=GapDimension.SOURCE_EVIDENCE,
                    expected_value=str(report_number),
                    observed_evidence_status=ObservationEvidenceStatus.CONFLICTING,
                    classification=GapClassification.SOURCE_METADATA_REQUIRES_REVIEW,
                    evidence_refs=tuple(sorted(title_refs.values())),
                    rationale=(
                        "Multiple source-original entry titles remain preserved; no preferred "
                        "title is selected without review."
                    ),
                    manual_review_required=True,
                    disposition=GapDisposition.PENDING_HUMAN_REVIEW,
                    related_manifest_report_ids=(_manifest_id(report_number),),
                )
            )

    gaps_by_report: dict[str, list[str]] = defaultdict(list)
    manual_review_by_report: set[str] = set()
    for gap in gaps:
        for report_id in gap.related_manifest_report_ids:
            gaps_by_report[report_id].append(gap.gap_id)
            if gap.manual_review_required:
                manual_review_by_report.add(report_id)

    manifest: list[CorpusReportManifestEntry] = []
    for report_number, month in sorted(number_to_month.items()):
        manifest_report_id = _manifest_id(report_number)
        qualifying_occurrences = [
            occurrence
            for occurrence in discovery.occurrences
            if occurrence.record.candidate_report_number == report_number
        ]
        identity_refs: list[EvidenceReference] = []
        titles: dict[str, list[EvidenceReference]] = defaultdict(list)
        run_ids: set[str] = set()
        record_refs: set[str] = set()
        for occurrence in qualifying_occurrences:
            record = occurrence.record
            run_ids.add(occurrence.run_id)
            record_refs.add(f"{occurrence.run_id}:{record.discovery_record_id}")
            qualified = [
                item
                for item in record.identity_evidence
                if item.evidence_type
                in {IdentityEvidenceType.DOCUMENT_VISIBLE, IdentityEvidenceType.OFFICIAL_METADATA}
            ]
            refs = [
                _evidence_ref(occurrence.run_id, record.discovery_record_id, item.evidence_id)
                for item in qualified
            ]
            identity_refs.extend(refs)
            if record.entry_title_original:
                titles[record.entry_title_original].extend(refs)
        source_titles = tuple(
            SourceTitleObservation(
                title_original=title,
                evidence_refs=tuple(
                    sorted(set(refs), key=lambda item: (item.discovery_run_id, item.evidence_id))
                ),
            )
            for title, refs in sorted(titles.items())
            if refs
        )
        preferred_title = source_titles[0].title_original if len(source_titles) == 1 else None
        preferred_refs = source_titles[0].evidence_refs if len(source_titles) == 1 else ()
        completed = acquisition_by_report.get(report_number)
        association = (
            AssociationStatus(completed.association_status)
            if completed
            else AssociationStatus.NOT_APPLICABLE
        )
        manifest.append(
            CorpusReportManifestEntry(
                manifest_report_id=manifest_report_id,
                source_institution="Defensoría del Pueblo",
                source_series="Reporte Mensual de Conflictos Sociales",
                report_number=report_number,
                reference_month=month,
                source_titles=source_titles,
                preferred_title_original=preferred_title,
                preferred_title_evidence_refs=preferred_refs,
                identity_evidence_refs=tuple(
                    sorted(
                        set(identity_refs),
                        key=lambda item: (
                            item.discovery_run_id,
                            item.discovery_record_id,
                            item.evidence_id,
                        ),
                    )
                ),
                discovery_record_refs=tuple(sorted(record_refs)),
                source_observation_record_ids=tuple(
                    sorted(
                        item.source_observation_record_id
                        for item in observations_by_report[report_number]
                    )
                ),
                acquisition_state=(
                    AcquisitionState.BYTE_VERIFIED_IDENTICAL
                    if completed
                    else AcquisitionState.OFFICIAL_SOURCE_DISCOVERED
                ),
                known_byte_version_count=1 if completed else 0,
                preferred_protected_local_path=(
                    completed.protected.relative_path if completed else None
                ),
                association_status=association,
                review_status=(
                    ReviewStatus.REQUIRES_HUMAN_REVIEW
                    if manifest_report_id in manual_review_by_report
                    else (ReviewStatus.VERIFIED if completed else ReviewStatus.CANDIDATE)
                ),
                gap_ids=tuple(sorted(gaps_by_report[manifest_report_id])),
                discovery_run_ids=tuple(sorted(run_ids)),
                input_artifact_fingerprints=discovery.artifact_fingerprints,
            )
        )

    verified_numbers = sorted(acquisition_by_report)
    gap_counts = Counter(gap.classification for gap in gaps)
    coverage = CoverageReport(
        research_coverage_start="2004-04",
        observation_cutoff=max(number_to_month.values()),
        observed_numbered_report_min=min(number_to_month),
        observed_numbered_report_max=max(number_to_month),
        observed_numbered_report_count=len(number_to_month),
        observed_reference_month_min=min(number_to_month.values()),
        observed_reference_month_max=max(number_to_month.values()),
        observed_reference_month_count=len(set(number_to_month.values())),
        report_to_month_conflict_count=0,
        month_to_report_conflict_count=0,
        historical_bundle_lead_years=tuple(sorted(unnumbered_by_year)),
        reports_1_22_status="unobserved_report_number_hypotheses",
        byte_verified_report_min=min(verified_numbers) if verified_numbers else None,
        byte_verified_report_max=max(verified_numbers) if verified_numbers else None,
        byte_verified_report_count=len(verified_numbers),
        unresolved_gap_counts=tuple(sorted(gap_counts.items(), key=lambda item: item[0].value)),
        candidate_completeness_status=(CandidateCompletenessStatus.CANDIDATE_REQUIRES_HUMAN_REVIEW),
        human_review_required=True,
        input_artifact_fingerprints=(
            *discovery.artifact_fingerprints,
            *acquisition.operational_fingerprints,
        ),
        implementation_tree_sha=context.implementation_tree_sha,
        manifest_schema_version="0.1.1",
        materializer_version=MATERIALIZER_VERSION,
    )
    return CandidatePackage(
        manifest=tuple(manifest),
        source_observations=observations,
        byte_versions=tuple(sorted(byte_versions, key=lambda item: item.report_number)),
        version_edges=tuple(sorted(version_edges, key=lambda item: item.edge_id)),
        gaps=tuple(sorted(gaps, key=lambda item: item.gap_id)),
        coverage=coverage,
    )
