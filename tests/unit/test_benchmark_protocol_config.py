from __future__ import annotations

from pathlib import Path

import yaml

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
