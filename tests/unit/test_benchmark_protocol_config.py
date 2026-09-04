from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

import peru_conflicts.benchmark as benchmark
from peru_conflicts.benchmark import (
    BenchmarkPartition,
    BenchmarkPartitionAssignment,
    PartitionRole,
)


def test_tracked_partition_freezes_report_level_leakage_boundary() -> None:
    repo_root = Path(__file__).parents[2]
    payload = yaml.safe_load(
        (repo_root / "config/benchmark/m2_partition_v1.yaml").read_text(encoding="utf-8")
    )
    partition = BenchmarkPartition(
        partition_id=payload["partition_id"],
        assignments=tuple(
            BenchmarkPartitionAssignment(
                report_number=entry["report_number"],
                role=PartitionRole(entry["role"]),
            )
            for entry in payload["assignments"]
        ),
    )

    assert [assignment.report_number for assignment in partition.assignments] == list(
        range(260, 270)
    )
    assert tuple(payload["pilot_unit_ids"]) == (
        "annotation-unit-030194f7766a7f805b39d87c",
        "annotation-unit-87fb8912e4e617f91bb4c415",
    )
    assert [
        assignment.report_number
        for assignment in partition.assignments
        if assignment.role is PartitionRole.HELD_OUT_EVALUATION
    ] == [261, 263, 265, 267]


def test_critical_field_config_is_selective_and_grouped() -> None:
    repo_root = Path(__file__).parents[2]
    payload = yaml.safe_load(
        (repo_root / "config/benchmark/m2_critical_fields_v1.yaml").read_text(encoding="utf-8")
    )
    source_groups = payload["source_value_critical"]
    source_fields = [field for group in source_groups.values() for field in group["fields"]]

    assert set(source_groups) == {
        "identity",
        "monthly_status",
        "location",
        "violence_casualty",
        "dialogue_mediation",
        "event_dates",
    }
    assert len(source_fields) == len(set(source_fields)) == 40
    assert "case_month.monthly_facts_original" in source_fields
    assert "case_reported_indicator.value" in source_fields
    assert "case.case_id" not in source_fields
    assert payload["custody_prerequisites"]["fields"] == [
        "report.sha256",
        "provenance.source_sha256",
    ]
    assert payload["technical_matching_keys"]["fields"] == [
        "annotation_unit.unit_id",
        "provenance.source_report_id",
    ]
    assert payload["evidence_requirements"]["required_components"] == [
        "exact_source_sha",
        "exact_page",
        "source_section",
        "granularity_appropriate_locator",
    ]
    assert payload["excluded_later_stage_fields"]["fields"] == ["case.case_id"]


def test_proposed_m3_gate_config_is_versioned_and_requires_owner_review() -> None:
    repo_root = Path(__file__).parents[2]
    payload = yaml.safe_load(
        (repo_root / "config/benchmark/m3_acceptance_gates_v1.yaml").read_text(encoding="utf-8")
    )
    spec = benchmark.BenchmarkAcceptanceGateSpec.model_validate_json(json.dumps(payload))

    assert spec.gate_id == "m3-acceptance-gates-v1"
    assert spec.policy_status is benchmark.GatePolicyStatus.OWNER_REVIEW_DRAFT
    assert spec.owner_approval_required is True
    assert spec.owner_approved is False
    assert spec.case_detection_precision_threshold == 0.99
    assert spec.case_detection_recall_threshold == 0.99
    assert spec.exact_page_attribution_threshold == 0.99
    assert spec.strict_source_value_accuracy_threshold == 0.99
    assert spec.evidence_completeness_threshold == 1.0
    assert spec.evidence_policy_interpretation == "PROPOSED_OWNER_GATE_INTERPRETATION"
    assert spec.object_metric_thresholds == ()
    assert spec.require_critical_parser_errors_closed is True
    assert spec.require_arithmetic_discrepancies_classified is True


def test_m2_01_owner_approval_binds_reviewed_contract_without_approving_m3() -> None:
    repo_root = Path(__file__).parents[2]
    payload = yaml.safe_load(
        (repo_root / "config/benchmark/m2_01_owner_approval_v1.yaml").read_text(encoding="utf-8")
    )
    approval = benchmark.M201OwnerApproval.model_validate_json(json.dumps(payload))

    assert approval.milestone == "M2-01"
    assert approval.owner == "Jorge Zavala"
    assert approval.reviewed_pr_number == 11
    assert approval.reviewed_head_sha == "7a2e2da82349f6d2311f0291b4d6f5ece1e72354"
    assert approval.reviewed_tree_sha == "ecab90aae4681abe2b6e5a15451fa863e309494f"
    assert approval.reviewed_base_sha == "46fab9b1f878453b3c1d3f2ec8b964ff5ecfb1e1"
    assert approval.reviewed_actions_run_id == 33844007460
    assert isinstance(approval.approved_at, datetime)
    assert approval.approved_at.utcoffset() is not None
    assert len(approval.approved_decision_ids) == 18
    assert set(approval.approved_decision_ids) == {
        "SCI-Q1",
        "SCI-Q2",
        "SCI-Q3",
        "SCI-Q4",
        "SCI-Q5",
        "BENCH-STATES",
        "BENCH-EVIDENCE",
        "CRIT-SET",
        "METRIC-STRICT",
        "METRIC-OBJECTS",
        "PARTITION",
        "M3-GATE-CASE-PRECISION",
        "M3-GATE-CASE-RECALL",
        "M3-GATE-PAGE-ATTRIBUTION",
        "M3-GATE-SOURCE-VALUE-ACCURACY",
        "M3-GATE-EVIDENCE-COMPLETENESS",
        "M3-GATE-CRITICAL-ERROR-CLOSURE",
        "M3-GATE-ARITHMETIC-CLASSIFICATION",
    }
    assert len(approval.scientific_q5_rejections) == 5
    assert set(approval.scientific_q5_rejections) == {
        "closed_historical_taxonomies",
        "automatic_annex_to_case_links",
        "automatic_mediation_continuity",
        "reconstructed_cumulative_violence_replacing_source_values",
        "timeless_case_description",
    }
    assert approval.pilots.machine_aids_remain_non_gold is True
    assert approval.pilots.human_submissions_created is False
    assert approval.pilots.human_gold_created is False
    assert approval.object_threshold_policy.option == "A"
    assert approval.object_threshold_policy.final_m3_gate_approved is False
    assert approval.object_threshold_policy.new_owner_approved_gate_required is True


def test_owner_approval_evidence_hashes_are_exact_and_contains_no_machine_values() -> None:
    repo_root = Path(__file__).parents[2]
    approval_path = repo_root / "config/benchmark/m2_01_owner_approval_v1.yaml"
    payload = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
    approval = benchmark.M201OwnerApproval.model_validate_json(json.dumps(payload))

    assert approval.review_evidence.model_dump(mode="json") == {
        "owner_decision_matrix_v3_sha256": (
            "b04619da33f1f7bf7a39f46768cc4a53cb14be7a7a69c86204308c2816a8db1b"
        ),
        "owner_review_packet_v3_sha256": (
            "b4498a91d4d2631d7a05401993ab30870c015088337f8a46363af3051c7bc62f"
        ),
        "pilot_264_v3_sha256": "10e043d1938d89f4461664a221bcf605e5ef04712da33563bec7aaf79f3aedb9",
        "pilot_269_v3_sha256": "7471dc0d00f0b32b6590d0152ae5475a3e3e7d9af244127fff55b70a4ab33a1a",
        "owner_review_session_packet_sha256": (
            "001a2cd9d2710f44117d5ba03b5f35eacfeddbb9cab8aa89aec3939bdfd6a42f"
        ),
        "owner_review_form_sha256": (
            "a03d6fdee779683d17df41cd12f9f403ab3f1662a109db092e17764624bc72cb"
        ),
    }
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for prohibited in (
        "machine_proposed_source_reading",
        "raw_value",
        "annotator_a",
        "annotator_b",
    ):
        assert prohibited not in serialized


def test_m3_draft_remains_fail_closed_under_owner_selected_object_policy_a() -> None:
    repo_root = Path(__file__).parents[2]
    gate_payload = yaml.safe_load(
        (repo_root / "config/benchmark/m3_acceptance_gates_v1.yaml").read_text(encoding="utf-8")
    )
    approval_payload = yaml.safe_load(
        (repo_root / "config/benchmark/m2_01_owner_approval_v1.yaml").read_text(encoding="utf-8")
    )
    gate = benchmark.BenchmarkAcceptanceGateSpec.model_validate_json(json.dumps(gate_payload))
    approval = benchmark.M201OwnerApproval.model_validate_json(json.dumps(approval_payload))

    assert gate.policy_status is benchmark.GatePolicyStatus.OWNER_REVIEW_DRAFT
    assert gate.owner_approved is False
    assert gate.object_metric_thresholds == ()
    assert approval.object_threshold_policy.option == "A"
    assert approval.object_threshold_policy.threshold_selection_after_milestone == "M2-03"
    assert approval.object_threshold_policy.final_m3_gate_approved is False
