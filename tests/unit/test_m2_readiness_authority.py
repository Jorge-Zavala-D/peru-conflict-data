"""Readiness implementation cannot expand historical scientific or execution authority."""

import hashlib
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]


def config(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load((ROOT / "config/benchmark" / name).read_bytes()))


def test_frozen_contracts_and_approvals_are_exact() -> None:
    readiness = config("m2_02a_readiness_v1.yaml")
    for folder, count, key in (
        ("schemas/benchmark/v0.1.0", 19, "benchmark_digest"),
        ("schemas/v0.3.0", 26, "scientific_digest"),
    ):
        root = ROOT / folder
        paths = sorted(root.rglob("*.json"))
        assert len(paths) == count
        data = "\n".join(
            f"{p.relative_to(root).as_posix()}:{hashlib.sha256(p.read_bytes()).hexdigest()}"
            for p in paths
        ).encode()
        assert hashlib.sha256(data).hexdigest() == readiness[key]
    for path, key in (
        ("config/benchmark/m2_01_owner_approval_v1.yaml", "m2_01_approval_sha256"),
        ("config/benchmark/m2_02_owner_approval_v1.yaml", "m2_02_approval_sha256"),
    ):
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == readiness[key]
    from test_m2_contract_versions import assert_metric_correction_scope

    assert (
        readiness["normative_evaluator_sha256"]
        == "a6264b995f05d4ac80f08e1f545b93813d88452eafa7857c52343703c6f8261f"
    )
    assert_metric_correction_scope()


def test_readiness_and_run_cannot_authorize_annotation_or_m3() -> None:
    readiness = config("m2_02a_readiness_v1.yaml")
    assert readiness["implementation_authorized"] is True
    for key in (
        "owner_readiness_approved",
        "annotation_launch_approved",
        "annotation_started",
        "human_gold_created",
        "dropbox_writes_approved",
        "parser_work_approved",
        "normative_metric_amendment_approved",
    ):
        assert readiness[key] is False
    gate = config("m3_acceptance_gates_v1.yaml")
    assert gate["policy_status"] == "owner_review_draft"
    assert gate["owner_approved"] is False and gate["object_metric_thresholds"] == []
    run = config("m2_02_annotation_run_v1.yaml")
    assert run["launch_approved"] is False and run["annotation_started"] is False
    assert run["human_gold_created"] is False and run["coordinator_only"] is True
    sources = run["sources"]
    assert [s["report_number"] for s in sources] == list(range(260, 270))
    assert sum(s["page_count"] for s in sources) == 1128
    assert [
        s["report_number"] for s in sources if s["partition_role"] == "held_out_evaluation"
    ] == [261, 263, 265, 267]
    for source in sources:
        if source["report_number"] in {261, 263}:
            assert source["source_association_status"] == "unresolved_opaque_filename"
