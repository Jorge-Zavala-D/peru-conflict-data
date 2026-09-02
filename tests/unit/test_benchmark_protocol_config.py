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
    groups = payload["groups"]
    fields = [field for group in groups.values() for field in group["fields"]]

    assert set(groups) == {
        "identity",
        "monthly_status",
        "location",
        "violence_casualty",
        "dialogue_mediation",
        "event_dates",
        "provenance",
    }
    assert len(fields) == len(set(fields))
    assert 35 <= len(fields) <= 55
    assert "case_month.monthly_facts_original" in fields
    assert "case_reported_indicator.value" in fields
    assert "provenance.source_page" in fields
