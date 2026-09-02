from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from peru_conflicts.manifest.models import ArtifactFingerprint
from peru_conflicts.manifest.reviewed_models import (
    AdjudicationOutcome,
    DeferredAcquisitionPolicy,
    OwnerApprovalArtifact,
    ReviewedCoverageReport,
)

SHA = "a" * 64
COMMIT = "b" * 40
TREE = "c" * 40
CANDIDATE_NAMES = (
    "byte_versions_candidate.jsonl",
    "corpus_manifest_candidate.jsonl",
    "coverage_report_candidate.json",
    "gap_register_candidate.jsonl",
    "source_observations_candidate.jsonl",
    "version_edges_candidate.jsonl",
)


def test_reviewed_manifest_model_layer_exists() -> None:
    module = importlib.import_module("peru_conflicts.manifest.reviewed_models")

    assert module.REVIEWED_MANIFEST_SCHEMA_VERSION == "0.2.0"
    assert module.ManifestAdjudicationRecord.model_fields
    assert module.OwnerApprovalArtifact.model_fields
    assert module.DeferredAcquisitionPolicy.model_fields
    assert module.ReviewedCoverageReport.model_fields
    assert module.CanonicalizationReceipt.model_fields


def _fingerprint(path: str) -> dict[str, object]:
    return {
        "path": path,
        "bytes": 1,
        "sha256": SHA,
        "record_count": 1,
    }


def _approval_payload() -> dict[str, object]:
    outcomes = (
        [AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED] * 45
        + [AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN] * 3
        + [AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME] * 2
    )
    required_inputs = (
        "canonicalization_gate",
        "evidence_dossier",
        "m1_04b_review_spec_v011",
        "owner_decision_packet",
        "proposed_adjudications",
        "review_receipt",
    )
    return {
        "schema_version": "0.2.0",
        "approval_id": "m1-04b-owner-adjudications-v1",
        "approved_by": "Jorge Zavala",
        "approved_at": datetime(2026, 9, 2, tzinfo=UTC),
        "owner_approved": True,
        "protected_main": {"commit": COMMIT, "tree": TREE},
        "manifest_contract": {
            "schema_version": "0.1.1",
            "materializer_version": "m1-04a-v2",
        },
        "candidate_fingerprints": tuple(
            ArtifactFingerprint(
                artifact_role=f"candidate:{index}",
                path=name,
                bytes=1,
                sha256=SHA,
                record_count=1,
            )
            for index, name in enumerate(CANDIDATE_NAMES)
        ),
        "post_merge_materialization_receipt": _fingerprint("materialization_receipt.json"),
        "review_input_fingerprints": {
            name: _fingerprint(f"{name}.json") for name in required_inputs
        },
        "approved_decisions": tuple(
            {"review_unit_id": f"review-{index:02d}", "approved_outcome": outcome}
            for index, outcome in enumerate(outcomes)
        ),
        "approved_outcome_counts": {
            AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED: 45,
            AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN: 3,
            AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME: 2,
        },
        "approved_deferred_acquisition_policy": {
            "authoritative_byte_corpus_complete": False,
            "blocks_identity_coverage_canonicalization": False,
            "count": 237,
            "future_evidence_classification": "useful_but_deferred",
            "report_numbers": tuple(range(23, 260)),
        },
        "approved_permissible_coverage_statement": (
            "Reviewed coverage accounting retains explicit limitations.",
        ),
        "prohibited_overclaims": ("The complete official PDF byte corpus has been acquired.",),
        "scientific_assertions": {
            "new_report_identities_created": False,
            "new_month_mappings_created": False,
            "new_byte_identities_created": False,
            "unresolved_evidence_retained": True,
            "authoritative_byte_corpus_complete": False,
        },
    }


def test_owner_approval_requires_exact_unique_50_decision_queue() -> None:
    valid = _approval_payload()
    artifact = OwnerApprovalArtifact.model_validate(valid)
    assert len(artifact.approved_decisions) == 50

    missing = _approval_payload()
    missing_decisions = cast(tuple[dict[str, object], ...], missing["approved_decisions"])
    missing["approved_decisions"] = missing_decisions[:-1]
    with pytest.raises(ValidationError):
        OwnerApprovalArtifact.model_validate(missing)

    duplicate = _approval_payload()
    decisions = list(cast(tuple[dict[str, object], ...], duplicate["approved_decisions"]))
    decisions[-1] = decisions[-1] | {"review_unit_id": decisions[0]["review_unit_id"]}
    duplicate["approved_decisions"] = tuple(decisions)
    with pytest.raises(ValidationError, match="unique"):
        OwnerApprovalArtifact.model_validate(duplicate)


def test_owner_approval_rejects_wrong_outcome_owner_or_input_set() -> None:
    wrong_outcome = _approval_payload()
    decisions = list(cast(tuple[dict[str, object], ...], wrong_outcome["approved_decisions"]))
    decisions[0] = decisions[0] | {
        "approved_outcome": AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN
    }
    wrong_outcome["approved_decisions"] = tuple(decisions)
    with pytest.raises(ValidationError, match="45/3/2"):
        OwnerApprovalArtifact.model_validate(wrong_outcome)

    wrong_owner = _approval_payload()
    wrong_owner["approved_by"] = "Different owner"
    with pytest.raises(ValidationError):
        OwnerApprovalArtifact.model_validate(wrong_owner)

    altered_packet = _approval_payload()
    review_inputs = cast(dict[str, object], altered_packet["review_input_fingerprints"])
    del review_inputs["owner_decision_packet"]
    with pytest.raises(ValidationError, match="six review inputs"):
        OwnerApprovalArtifact.model_validate(altered_packet)


def test_deferred_policy_cannot_change_acquisition_state_or_report_range() -> None:
    valid = DeferredAcquisitionPolicy(
        policy_id="m1-deferred-byte-acquisition-23-259-v1",
        report_numbers=tuple(range(23, 260)),
        deferred_report_count=237,
        report_identities_observed=True,
        authoritative_bytes_acquired=False,
        authoritative_byte_corpus_complete=False,
        future_evidence_classification="useful_but_deferred",
        owner_approval_id="m1-04b-owner-adjudications-v1",
        owner_approval_sha256=SHA,
    )
    assert valid.deferred_report_count == 237
    with pytest.raises(ValidationError, match="23 through 259"):
        DeferredAcquisitionPolicy.model_validate(
            valid.model_dump() | {"report_numbers": tuple(range(24, 261))}
        )
    with pytest.raises(ValidationError):
        DeferredAcquisitionPolicy.model_validate(
            valid.model_dump() | {"authoritative_byte_corpus_complete": True}
        )


def _reviewed_coverage_payload() -> dict[str, object]:
    months = [f"2004-{month:02d}" for month in range(4, 13)] + [
        f"2005-{month:02d}" for month in range(1, 13)
    ]
    return {
        "research_coverage_start": "2004-04",
        "observation_cutoff": "2026-07",
        "observed_numbered_report_min": 23,
        "observed_numbered_report_max": 269,
        "observed_numbered_report_count": 247,
        "observed_reference_month_min": "2006-01",
        "observed_reference_month_max": "2026-07",
        "observed_reference_month_count": 247,
        "report_to_month_conflict_count": 0,
        "month_to_report_conflict_count": 0,
        "human_review_status": "owner_approved",
        "owner_approved_decision_count": 50,
        "approved_outcome_counts": {
            AdjudicationOutcome.EVIDENCE_INSUFFICIENT_RETAIN_UNRESOLVED: 45,
            AdjudicationOutcome.BYTES_NOT_OBSERVED_REMAIN_UNKNOWN: 3,
            AdjudicationOutcome.RETAIN_UNRESOLVED_OPAQUE_FILENAME: 2,
        },
        "coverage_accounting_status": "reviewed_with_explicit_limitations",
        "factual_gap_count": 287,
        "unresolved_evidence_retained": True,
        "deferred_byte_acquisition_count": 237,
        "byte_verified_report_count": 10,
        "authoritative_byte_corpus_complete": False,
        "reports_1_22_status": "unobserved_report_number_hypotheses",
        "unresolved_historical_months": tuple(months),
        "historical_unnumbered_lead_years": (2004, 2005),
        "byte_unknown_report_numbers": (69, 153, 169),
        "opaque_association_report_numbers": (261, 263),
        "approved_coverage_claims": (
            "Reviewed coverage accounting with explicit unresolved evidence.",
        ),
        "prohibited_overclaims": ("Complete official PDF byte corpus.",),
        "owner_approval_id": "m1-04b-owner-adjudications-v1",
        "owner_approval_sha256": SHA,
    }


def test_reviewed_coverage_closes_human_review_without_resolving_evidence() -> None:
    coverage = ReviewedCoverageReport.model_validate(_reviewed_coverage_payload())
    assert coverage.owner_approved_decision_count == 50
    assert coverage.factual_gap_count == 287
    assert coverage.unresolved_evidence_retained is True
    assert coverage.authoritative_byte_corpus_complete is False

    overclaim = _reviewed_coverage_payload()
    overclaim["authoritative_byte_corpus_complete"] = True
    with pytest.raises(ValidationError):
        ReviewedCoverageReport.model_validate(overclaim)


def test_historical_and_version_uncertainties_remain_exact() -> None:
    coverage = ReviewedCoverageReport.model_validate(_reviewed_coverage_payload())
    assert coverage.reports_1_22_status == "unobserved_report_number_hypotheses"
    assert coverage.unresolved_historical_months[0] == "2004-04"
    assert coverage.unresolved_historical_months[-1] == "2005-12"
    assert coverage.historical_unnumbered_lead_years == (2004, 2005)
    assert coverage.byte_unknown_report_numbers == (69, 153, 169)
    assert coverage.opaque_association_report_numbers == (261, 263)
