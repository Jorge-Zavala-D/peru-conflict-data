"""Canonical, cache-only materialization of M1-04A candidate evidence."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.manifest.evidence import AcquisitionClosure
from peru_conflicts.manifest.models import (
    MANIFEST_SCHEMA_VERSION,
    ArtifactFingerprint,
    ByteVersionRecord,
    CorpusReportManifestEntry,
    CoverageReport,
    GapRegisterEntry,
    MaterializationReceipt,
    SourceObservationRecord,
    VersionSourceRelationshipEdge,
)
from peru_conflicts.manifest.reconcile import CandidatePackage
from peru_conflicts.models.common import StrictModel


class MaterializationError(RuntimeError):
    """Candidate output target or deterministic serialization is unsafe."""


def _canonical_json_line(model: StrictModel) -> bytes:
    return canonical_json_bytes(model.model_dump(mode="json")) + b"\n"


def _jsonl[T: StrictModel](items: Sequence[T], *, key: Callable[[T], str]) -> bytes:
    return b"".join(_canonical_json_line(item) for item in sorted(items, key=key))


def _fingerprint(filename: str, raw: bytes, *, record_count: int) -> ArtifactFingerprint:
    return ArtifactFingerprint(
        artifact_role=f"candidate_output:{filename}",
        path=filename,
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        record_count=record_count,
    )


def _require_new_cache_target(output_dir: Path, repository_root: Path) -> Path:
    root = repository_root.resolve()
    cache_root = root / ".cache"
    output = output_dir.resolve()
    if not output.is_relative_to(cache_root) or output == cache_root:
        raise MaterializationError("candidate output must be beneath the ignored repository cache")
    if output.exists():
        raise MaterializationError("candidate output directory already exists")
    return output


def _render_outputs(package: CandidatePackage) -> dict[str, tuple[bytes, int]]:
    return {
        "corpus_manifest_candidate.jsonl": (
            _jsonl(package.manifest, key=lambda item: f"{item.report_number:09d}"),
            len(package.manifest),
        ),
        "source_observations_candidate.jsonl": (
            _jsonl(
                package.source_observations,
                key=lambda item: item.source_observation_record_id,
            ),
            len(package.source_observations),
        ),
        "byte_versions_candidate.jsonl": (
            _jsonl(package.byte_versions, key=lambda item: item.byte_version_id),
            len(package.byte_versions),
        ),
        "version_edges_candidate.jsonl": (
            _jsonl(package.version_edges, key=lambda item: item.edge_id),
            len(package.version_edges),
        ),
        "gap_register_candidate.jsonl": (
            _jsonl(package.gaps, key=lambda item: item.gap_id),
            len(package.gaps),
        ),
        "coverage_report_candidate.json": (_canonical_json_line(package.coverage), 1),
    }


def _verify_written_package(output: Path, expected: dict[str, tuple[bytes, int]]) -> None:
    jsonl_models = {
        "corpus_manifest_candidate.jsonl": CorpusReportManifestEntry,
        "source_observations_candidate.jsonl": SourceObservationRecord,
        "byte_versions_candidate.jsonl": ByteVersionRecord,
        "version_edges_candidate.jsonl": VersionSourceRelationshipEdge,
        "gap_register_candidate.jsonl": GapRegisterEntry,
    }
    for filename, model in jsonl_models.items():
        raw = (output / filename).read_bytes()
        if raw != expected[filename][0] or (raw and not raw.endswith(b"\n")):
            raise MaterializationError(f"candidate output byte verification failed: {filename}")
        for line in raw.splitlines():
            parsed = model.model_validate_json(line)
            if _canonical_json_line(parsed) != line + b"\n":
                raise MaterializationError(f"candidate output is not canonical: {filename}")

    coverage_name = "coverage_report_candidate.json"
    coverage_raw = (output / coverage_name).read_bytes()
    coverage = CoverageReport.model_validate_json(coverage_raw)
    if coverage_raw != expected[coverage_name][0] or _canonical_json_line(coverage) != coverage_raw:
        raise MaterializationError("candidate coverage report failed canonical roundtrip")


def materialize_candidate_package(
    package: CandidatePackage,
    *,
    acquisition: AcquisitionClosure,
    output_dir: Path,
    repository_root: Path,
    repository_base_sha: str,
    repository_head_sha: str,
    protected_source_receipt_refs: tuple[str, ...],
) -> Path:
    """Write one deterministic, noncanonical candidate package under ``.cache``."""

    output = _require_new_cache_target(output_dir, repository_root)
    rendered = _render_outputs(package)
    fingerprints = tuple(
        sorted(
            (
                _fingerprint(filename, raw, record_count=record_count)
                for filename, (raw, record_count) in rendered.items()
            ),
            key=lambda item: item.path,
        )
    )
    report_numbers = [item.report_number for item in package.manifest]
    report_months = [item.reference_month for item in package.manifest]
    gap_counts = Counter(item.classification for item in package.gaps)
    discovery_fingerprints = tuple(
        item
        for item in package.coverage.input_artifact_fingerprints
        if item.artifact_role.startswith("discovery_")
    )
    discovery_run_ids = tuple(
        sorted({item.discovery_run_id for item in package.source_observations})
    )
    receipt = MaterializationReceipt(
        task_id="M1-04A",
        repository_base_sha=repository_base_sha,
        repository_head_sha=repository_head_sha,
        implementation_tree_sha=package.coverage.implementation_tree_sha,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        discovery_run_ids=discovery_run_ids,
        input_artifacts=discovery_fingerprints,
        operational_artifacts=acquisition.operational_fingerprints,
        protected_source_receipt_refs=protected_source_receipt_refs,
        output_artifacts=fingerprints,
        record_counts=tuple(
            sorted(
                ((filename, record_count) for filename, (_, record_count) in rendered.items()),
                key=lambda item: item[0],
            )
        ),
        observed_numbered_report_count=len(report_numbers),
        observed_numbered_report_min=min(report_numbers),
        observed_numbered_report_max=max(report_numbers),
        observed_reference_month_count=len(set(report_months)),
        observed_reference_month_min=min(report_months),
        observed_reference_month_max=max(report_months),
        gap_counts=tuple(sorted(gap_counts.items(), key=lambda item: item[0].value)),
        byte_verified_count=len(package.byte_versions),
        unresolved_review_count=sum(item.manual_review_required for item in package.gaps),
        deterministic_sort_rules=(
            "manifest:report_number",
            "source_observations:source_observation_record_id",
            "byte_versions:byte_version_id",
            "version_edges:edge_id",
            "gaps:gap_id",
            "json:canonical_utf8_lf",
        ),
        no_network_assertion=True,
        no_raw_write_assertion=True,
        no_canonical_database_write_assertion=True,
    )
    receipt_raw = _canonical_json_line(receipt)

    output.mkdir(parents=True)
    for filename, (raw, _) in rendered.items():
        (output / filename).write_bytes(raw)
    _verify_written_package(output, rendered)
    receipt_path = output / "materialization_receipt.json"
    receipt_path.write_bytes(receipt_raw)
    reread_receipt = MaterializationReceipt.model_validate_json(receipt_path.read_bytes())
    if _canonical_json_line(reread_receipt) != receipt_raw:
        raise MaterializationError("materialization receipt failed canonical roundtrip")
    return receipt_path
