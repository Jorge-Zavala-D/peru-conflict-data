from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from peru_conflicts.discovery.pilot import (
    PilotAcquisitionPlan,
    load_pilot_acquisition_plan,
)

PLAN_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v1.yaml")


def test_reviewed_pilot_plan_is_bounded_source_safe_and_not_authorized() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)

    assert plan.schema_version == "0.3.0"
    assert plan.authorization_status == "not_authorized"
    assert [target.report_number for target in plan.targets] == list(range(260, 270))
    assert plan.limits.max_reports == 10
    assert plan.limits.max_urls == 20
    assert plan.limits.concurrency == 1
    assert plan.limits.delay_seconds == 2.0
    assert plan.limits.retry_cap == 2
    assert plan.limits.max_total_attempts == 60
    assert plan.limits.timeout_seconds == 30
    assert plan.limits.max_redirects_per_url == 5
    assert plan.limits.per_file_min_bytes == 1024
    assert set(plan.limits.attempts_include) == {
        "robots",
        "initial_requests",
        "redirect_hops",
        "retries",
    }
    assert plan.dry_run.network_requests == 0
    assert plan.dry_run.dropbox_writes == 0
    assert all(target.expected_remote_sha256 is None for target in plan.targets)
    assert all(target.existing_local_sha256 for target in plan.targets)
    uncertain = {
        target.report_number: set(target.uncertainty_codes)
        for target in plan.targets
        if target.association_status == "unresolved_association"
    }
    assert uncertain == {
        261: {"opaque_filename", "unresolved_association"},
        263: {"opaque_filename", "unresolved_association"},
    }
    assert plan.baseline_receipt_path == "docs/source_integrity_receipt_m1_02.md"
    assert plan.baseline_receipt_git_commit == ("85a91ebba407610931e7e37b21b0ddddc15edbd1")


def test_local_baseline_hash_is_not_mislabeled_as_an_expected_remote_hash() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)
    payload = plan.model_dump()
    payload["targets"][0]["expected_remote_sha256"] = payload["targets"][0]["existing_local_sha256"]

    with pytest.raises(ValidationError, match="unknown before authorized retrieval"):
        PilotAcquisitionPlan.model_validate(payload)


def test_pilot_plan_rejects_non_authoritative_or_noncontiguous_targets() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)
    payload = plan.model_dump()
    payload["targets"][0]["direct_download_url"] = "https://mirror.example.org/report.pdf"
    with pytest.raises(ValidationError, match="approved authoritative host"):
        PilotAcquisitionPlan.model_validate(payload)

    payload = plan.model_dump()
    payload["approved_hosts"] = ("mirror.example.org", "www.defensoria.gob.pe")
    payload["targets"][0]["direct_download_url"] = "https://mirror.example.org/report.pdf"
    with pytest.raises(ValidationError, match="exact reviewed authoritative hosts"):
        PilotAcquisitionPlan.model_validate(payload)

    payload = plan.model_dump()
    payload["targets"][0]["direct_download_url"] = payload["targets"][0][
        "direct_download_url"
    ].replace("https://", "http://")
    with pytest.raises(ValidationError, match="HTTPS"):
        PilotAcquisitionPlan.model_validate(payload)

    payload = plan.model_dump()
    payload["targets"] = payload["targets"][:-1]
    with pytest.raises(ValidationError, match="exactly reports 260 through 269"):
        PilotAcquisitionPlan.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("candidate_reference_period", "2025-09"),
        ("publication_date_original", "15/11/2025"),
        ("landing_page_url", "https://www.defensoria.gob.pe/documentos/wrong/"),
        (
            "direct_download_url",
            "https://www.defensoria.gob.pe/wp-content/uploads/wrong.pdf",
        ),
        ("existing_local_relative_path", "01_raw/reports/2025/wrong.pdf"),
        ("existing_local_byte_count", 2721479),
        (
            "existing_local_sha256",
            "0" * 64,
        ),
    ],
)
def test_every_reviewed_target_field_is_pinned(field: str, replacement: object) -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)
    payload = plan.model_dump()
    payload["targets"][0][field] = replacement

    with pytest.raises(ValidationError, match="reviewed target-set fingerprint"):
        PilotAcquisitionPlan.model_validate(payload)


def test_opaque_targets_require_both_structured_uncertainties() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)
    payload = plan.model_dump()
    target_261 = next(item for item in payload["targets"] if item["report_number"] == 261)
    target_261["uncertainty_codes"] = ("opaque_filename",)

    with pytest.raises(ValidationError, match="both uncertainty codes"):
        PilotAcquisitionPlan.model_validate(payload)


def test_pilot_limits_reject_weakened_timeout_size_and_attempt_semantics() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)
    for field, value in (
        ("timeout_seconds", 31),
        ("per_file_min_bytes", 1023),
        ("max_redirects_per_url", 6),
        ("attempts_include", ("initial_requests", "retries")),
    ):
        payload = plan.model_dump()
        payload["limits"][field] = value
        with pytest.raises(ValidationError):
            PilotAcquisitionPlan.model_validate(payload)


def test_promotion_contract_closes_preflight_stream_comparison_and_atomic_staging() -> None:
    plan = load_pilot_acquisition_plan(PLAN_PATH)

    assert plan.promotion_policy.pre_network_validation_order[-1] == ("existing_path_size_sha256")
    assert plan.promotion_policy.response_validation_order[-1] == "sha256"
    assert plan.promotion_policy.disposition_order[0] == "compare_to_existing_sha256"
    assert plan.promotion_policy.same_filesystem_staging_location.startswith(
        "conflict_data_root/01_raw/.staging/"
    )
    assert plan.promotion_policy.staging_behavior == ("copy_stream_rehash_then_atomic_rename")
