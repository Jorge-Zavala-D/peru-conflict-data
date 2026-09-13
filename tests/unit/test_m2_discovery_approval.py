"""Owner governance approval is not annotation-launch or metric authority."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).parents[2]
APPROVAL = ROOT / "config/benchmark/m2_02_owner_approval_v1.yaml"
DECISIONS = {
    "DISCOVERY-WINDOW",
    "POST-DISCOVERY-UNITIZATION",
    "CASE-DETECTION-ANCHOR",
    "DETECTION-VS-PAGE-ATTRIBUTION",
    "AB-DISCOVERY-DISAGREEMENT",
    "CARDINALITY-NONIDENTITY",
    "REPEATED-OBJECT-DISCOVERY",
    "FUTURE-METRIC-AMENDMENT",
    "BENCHMARK-SCHEMA-NO-CHANGE",
}


def approval() -> dict[str, Any]:
    assert APPROVAL.is_file(), "tracked discovery-policy owner approval is missing"
    value = yaml.safe_load(APPROVAL.read_bytes())
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_exact_owner_decisions_are_recorded_without_extra_approvals() -> None:
    record = approval()
    assert record["approval_record_version"] == "1.0.0"
    assert record["policy_id"] == "m2-02-execution-policy-v1"
    assert record["owner"] == "Jorge Zavala"
    assert record["owner_decision_status"] == "approved"
    assert record["decisions"] == dict.fromkeys(DECISIONS, "APPROVE")
    assert datetime.fromisoformat(record["recorded_at"]).utcoffset() is not None


def test_approval_binds_substantive_review_not_its_own_commit() -> None:
    reviewed = approval()["reviewed_identity"]
    assert reviewed == {
        "pr_number": 12,
        "branch": "codex/m2-02a0-discovery-window-policy",
        "base_sha": "a511b61229746bb5b59a58ad9212fa3bac79cc3c",
        "base_tree": "36b3a462af2eae4982b6b9067083e5741966d3c6",
        "original_head": "e3680473392a7ef2d403e65dbd03a91f8c4f1de1",
        "original_tree": "8b54fdd39c9bb6938807aa5ed11ef6ba2668db64",
        "corrected_head": "d89c7a20636bee74f35dca28d9f5437e49106d8d",
        "corrected_tree": "e6b25184fcf302d67076458751c84d31f50ca390",
        "merge_test_sha": "caa407859a055ed810c9324dc418e41b4c4fed90",
        "actions_run_id": 33999762426,
    }


def test_review_evidence_is_bound_without_tracking_local_packets() -> None:
    assert approval()["review_evidence"] == {
        "packet_v1_sha256": "550411065c23cf82c130beb4dd55a43e5fba96a4a8d1afad1fe6bfbcae89cda9",
        "proof_v1_sha256": "177505674e6bfd1727f7da1306dc93021ecbe4ea85d463fe563e0981074efe0c",
        "packet_v2_bytes": 7105,
        "packet_v2_sha256": "78a5339be2fc14c870d1ddc0554f9b95e00043f42edd94d5cc051544537b73ad",
        "proof_v2_bytes": 4344,
        "proof_v2_sha256": "794eecec7b3b9d5954ed5a37461185b9720eb7eb8d3a81c84ba581aecd723b72",
    }
    assert approval()["reviewed_policy_bytes"] == {
        "config_path": "config/benchmark/m2_02_execution_policy_v1.yaml",
        "config_sha256": "1da5db2b35c2a6548b2fa1f1b81ec58b5f64124e8fb0792949579130191aa4dd",
        "document_path": "docs/m2_02_discovery_execution_policy.md",
        "document_sha256": "edd6d272f86ec38b056055d18fe9b8ebb605535e8ead080bf30aff3cfbd6ca75",
    }


def test_policy_approval_cannot_be_used_as_launch_or_scoring_approval() -> None:
    limits = approval()["authorization_limits"]
    assert set(limits) == {
        "annotation_launch_authorized",
        "human_gold_creation_authorized",
        "normative_evaluator_amendment_approved",
        "final_m3_gate_approved",
        "production_readiness_approved",
        "parser_development_authorized",
        "parser_evaluation_authorized",
        "dropbox_writes_authorized",
        "ocr_authorized",
        "source_acquisition_authorized",
    }
    assert all(value is False for value in limits.values())
    policy = yaml.safe_load((ROOT / "config/benchmark/m2_02_execution_policy_v1.yaml").read_bytes())
    assert policy["owner_approved"] is True and policy["status"] == "owner_approved"
    assert policy["owner_approval_record"] == "config/benchmark/m2_02_owner_approval_v1.yaml"
    for key in (
        "annotation_started",
        "human_gold_created",
        "m2_02a_implementation_resumed",
        "final_m3_gate_approved",
    ):
        assert policy[key] is False
    assert policy["case_detection_anchor"]["status"] == "owner_approved_correspondence_only"
    assert policy["metric_amendment"]["required_for_start_key_scoring"] is True
    assert policy["metric_amendment"]["owner_approval_required"] is True
    assert policy["metric_amendment"]["normative_evaluator_changed"] is False


def test_future_readiness_and_blinding_remain_required() -> None:
    safeguards = approval()["safeguards"]
    for field in (
        "separate_readiness_and_launch_gate_required",
        "versioned_owner_approved_metric_amendment_required_before_start_key_scoring",
        "benchmark_role_blinding_required",
        "coordinator_wrapper_never_distributed",
        "private_human_eligibility_attestation_required",
        "two_distinct_blind_humans_required",
        "post_discovery_unitization_required",
        "unresolved_discoveries_preserved_for_m2_03",
        "no_automatic_correspondence_repair",
        "cardinality_local_only",
    ):
        assert safeguards[field] is True


def test_frozen_authority_and_evaluator_are_not_amended_by_approval() -> None:
    authority = approval()["frozen_authority"]
    for directory, version_key, version, digest_key, count, digest in (
        (
            "schemas/benchmark/v0.1.0",
            "benchmark_schema",
            "v0.1.0",
            "benchmark_digest",
            19,
            "23a5ee953541c93b9e51898872901f8b9432588f8c9ea03758ea85a5a1ff28fa",
        ),
        (
            "schemas/v0.3.0",
            "scientific_schema",
            "v0.3.0",
            "scientific_digest",
            26,
            "cd5bdea78e6314242685ea89d43850f8ff42e639ba74606aba3d929b2e81444d",
        ),
    ):
        folder = ROOT / directory
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        rows = [
            p.relative_to(folder).as_posix() + ":" + hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        ]
        assert len(files) == count
        assert hashlib.sha256("\n".join(rows).encode()).hexdigest() == digest
        assert authority[digest_key] == digest and authority[version_key] == version
    old_approval = ROOT / "config/benchmark/m2_01_owner_approval_v1.yaml"
    assert (
        hashlib.sha256(old_approval.read_bytes()).hexdigest()
        == authority["m2_01_owner_approval_sha256"]
        == "e338944f504c4bcce1c8312758121330b9487e4f996bf66fd8623c1eeae29ce5"
    )
    from test_m2_contract_versions import assert_metric_correction_scope

    assert_metric_correction_scope()
    gate = yaml.safe_load((ROOT / "config/benchmark/m3_acceptance_gates_v1.yaml").read_bytes())
    assert gate["owner_approved"] is False
    assert gate["policy_status"] == "owner_review_draft"
    assert gate["object_metric_thresholds"] == []
