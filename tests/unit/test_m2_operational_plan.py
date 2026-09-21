"""Operational preparation cannot grant real-world authority."""

import importlib
import importlib.util
import json
from pathlib import Path

import pytest
from test_m2_launch_preflight import Rehearsal
from test_m2_launch_preflight import rehearsal as rehearsal


def test_cache_builder_is_exclusive_and_rejects_external_paths(tmp_path: Path) -> None:
    c = contract()
    assert hasattr(c, "write_operational_proposal")
    for unsafe in ("../external", "C:/Dropbox", "/outside", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            c.write_operational_proposal(tmp_path, unsafe)
    assert not (tmp_path / ".cache").exists()
    output = c.write_operational_proposal(tmp_path, "synthetic")
    assert output.is_relative_to(tmp_path / ".cache/m2-02b2")
    with pytest.raises(ValueError):
        c.write_operational_proposal(tmp_path, "synthetic")
    files = {p.name for p in output.iterdir()}
    assert "mapped_108_acl_checks.json" in files
    private = json.loads((output / "eligibility_workflow_receipt.json").read_bytes())
    assert private["real_attestation_created"] is False
    assert private["template"]["private_name_and_contact"] is None


def test_tracked_candidates_match_current_source_neutral_models() -> None:
    c = contract()
    root = Path(__file__).resolve().parents[2] / "config/benchmark"
    import yaml

    assert yaml.safe_load(
        (root / "m2_02_operational_launch_candidate_v1.yaml").read_text()
    ) == c.make_candidate().model_dump(mode="json")
    assert yaml.safe_load(
        (root / "m2_02_annotation_launch_candidate_v1.yaml").read_text()
    ) == c.make_annotation_launch_candidate(c.make_candidate()).model_dump(mode="json")


def test_operational_rehearsal_never_grants_real_authority(rehearsal: Rehearsal) -> None:
    c = contract()
    assert hasattr(c, "rehearse_operational_plan")
    result = c.rehearse_operational_plan(
        c.make_candidate(), rehearsal, synthetic_external_write=True
    )
    assert result.prerequisites_satisfied
    assert result.status == "SYNTHETIC_REHEARSAL_ONLY"
    assert not result.annotation_launch_approved
    assert not result.production_locking_enabled


@pytest.mark.parametrize(
    "failure",
    ["external_write", "missing_person", "same_person", "access", "issuance", "stale_runtime"],
)
def test_operational_rehearsal_rejects_incomplete_evidence(
    rehearsal: Rehearsal, failure: str
) -> None:
    c = contract()
    assert hasattr(c, "rehearse_operational_plan")
    scenario = dict(rehearsal)
    if failure == "missing_person":
        scenario["people"] = ()
    elif failure == "same_person":
        scenario["people"] = (rehearsal["people"][0], rehearsal["people"][0])
    elif failure == "access":
        scenario["access"] = rehearsal["access"][:-1]
    elif failure == "issuance":
        scenario["receipts"] = ()
    elif failure == "stale_runtime":
        scenario["runtime_receipt_sha256s"] = ("0" * 64, "0" * 64)
    result = c.rehearse_operational_plan(
        c.make_candidate(), scenario, synthetic_external_write=failure != "external_write"
    )
    assert not result.prerequisites_satisfied
    assert not result.annotation_launch_approved


def test_parent_paths_and_permissions_are_explicit() -> None:
    c = contract()
    plan = c.build_operational_plan(c.make_candidate())
    assert "parents" in plan["topology"]
    parents = plan["topology"]["parents"]
    assert any(p["path"].endswith("coordinator/locked") for p in parents)
    for parent in parents:
        assert parent["share_with_annotators"] is False
        assert parent["allow_inheritance"] is False
    for area in plan["topology"]["areas"]:
        assert len(area["permissions"]) == 3
        assert "rollback" in area
        assert area["allow_inheritance"] is False


def test_operational_dossier_is_exact_and_not_an_approval() -> None:
    c = contract()
    assert hasattr(c, "operational_dossier")
    dossier = c.operational_dossier(c.make_candidate())
    assert tuple(d["decision_id"] for d in dossier["decisions"]) == c.OPERATIONAL_DECISIONS
    for row in dossier["decisions"]:
        assert row["response"] is None and row["status"] == "UNRESOLVED"
        for key in (
            "question",
            "evidence_required",
            "available",
            "missing",
            "dependencies",
            "conditional_recommendation",
            "authority",
            "non_authorities",
            "reversibility",
            "containment",
            "failure_state",
        ):
            assert row[key]
    packet = dossier["external_write_packet"]
    assert packet["response"] is None
    assert "research_package_issuance" in packet["excluded"]
    assert len(packet["allowed_future_scope"]) == 6


def test_annotation_launch_candidate_requires_all_six_decisions() -> None:
    c = contract()
    assert hasattr(c, "make_annotation_launch_candidate")
    candidate = c.make_annotation_launch_candidate(c.make_candidate())
    assert candidate.annotation_launch_approved is False
    assert candidate.annotation_started is False
    assert candidate.production_environment_approved is False
    assert candidate.prerequisite_decisions == c.OPERATIONAL_DECISIONS[:-1]
    for index in range(6):
        payload = candidate.model_dump(mode="json")
        payload["prerequisite_decisions"].pop(index)
        with pytest.raises(ValueError):
            c.AnnotationLaunchCandidate.model_validate(payload)


@pytest.mark.parametrize("field", ["operational_candidate_sha256", "required_evidence"])
def test_annotation_launch_candidate_rejects_stale_or_missing_evidence(field: str) -> None:
    c = contract()
    assert hasattr(c, "make_annotation_launch_candidate")
    candidate = c.make_annotation_launch_candidate(c.make_candidate())
    payload = candidate.model_dump(mode="json")
    payload[field] = "0" * 64 if field.endswith("sha256") else []
    with pytest.raises(ValueError):
        c.AnnotationLaunchCandidate.model_validate(payload)


def contract():
    assert importlib.util.find_spec("peru_conflicts.execution.operational_plan"), (
        "operational preparation contract missing"
    )
    return importlib.import_module("peru_conflicts.execution.operational_plan")


def test_blank_role_specific_issuance_templates_reject_real_or_stale_claims() -> None:
    c = contract()
    assert hasattr(c, "issuance_templates")
    candidate = c.make_candidate()
    templates = c.issuance_templates(candidate)
    assert len(templates) == 2
    assert templates[0]["role"] == "annotator-a"
    assert templates[1]["role"] == "annotator-b"
    for template in templates:
        assert template["recipient_token"] is None
        assert template["issued_at"] is None
        assert template["independent_delivered_byte_verification"] is None
        assert template["real_receipt_created"] is False
        assert template["delivery_path"].endswith(template["role"] + "/issue")
        for key in (
            "operational_candidate_sha256",
            "package_manifest_sha256",
            "reference_manifest_sha256",
            "view_sha256",
            "runtime_sha256",
            "python_environment_manifest_sha256",
            "dependency_sha256",
            "launcher_sha256",
        ):
            assert len(template[key]) == 64
    for key, value in (
        ("role", "annotator-b"),
        ("delivery_path", "elsewhere"),
        ("recipient_token", "invented-real-claim"),
        ("issued_at", "2026-09-21T00:00:00Z"),
        ("runtime_sha256", "0" * 64),
    ):
        changed = [dict(t) for t in templates]
        changed[0][key] = value
        with pytest.raises(ValueError):
            c.validate_issuance_templates(changed, candidate)


def test_candidate_preserves_seven_unresolved_and_rejects_missing_merge() -> None:
    c = contract()
    candidate = c.make_candidate()
    assert len(candidate.decisions) == 7
    assert all(d.response is None and d.status == "UNRESOLVED" for d in candidate.decisions)
    payload = candidate.model_dump(mode="json")
    payload["protected_main_merge_sha"] = "0" * 40
    with pytest.raises(ValueError):
        c.OperationalCandidate.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["annotation_started", "owner_launch_approved", "real_access_tests_passed"]
)
@pytest.mark.parametrize("value", [True, 1, 0, "false", None])
def test_candidate_rejects_authority_coercion(field: str, value: object) -> None:
    c = contract()
    payload = c.make_candidate().model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValueError):
        c.OperationalCandidate.model_validate(payload)


@pytest.mark.parametrize("change", ["design", "pin", "decision", "readiness"])
def test_candidate_rejects_replaced_authority(change: str) -> None:
    c = contract()
    payload = c.make_candidate().model_dump(mode="json")
    if change == "design":
        payload["launch_design_approval_sha256"] = "0" * 64
    elif change == "pin":
        payload["bindings"]["runtime_sha256"] = "0" * 64
    elif change == "decision":
        payload["decisions"][0]["response"] = "APPROVE"
    else:
        payload["owner_readiness_approved"] = False
    with pytest.raises(ValueError):
        c.OperationalCandidate.model_validate(payload)


def test_external_pin_is_required_even_for_self_consistent_bytes() -> None:
    c = contract()
    raw = json.dumps(c.make_candidate().model_dump(mode="json")).encode()
    with pytest.raises(ValueError):
        c.validate_operational_candidate(
            raw,
            expected_sha256="0" * 64,
            merge_sha="e33acf9350701f2c0141bf2d3f697c1bb69d2080",
            merge_tree="8c7970063362f6b07029c7cd0d46a15c94bf2a5d",
        )


def test_plan_maps_108_checks_without_running_them() -> None:
    c = contract()
    plan = c.build_operational_plan(c.make_candidate())
    rows = plan["checks"]
    assert len(rows) == 108
    assert len({(r["actor"], r["resource"], r["operation"]) for r in rows}) == 108
    assert all(r["status"] == "NOT RUN" for r in rows)
    row = next(r for r in rows if r["check_id"] == "a-write-own-issue")
    assert row["expected_outcome"] == "DENY"
    assert row["path"].endswith("annotator-a/issue")
    assert len(plan["application_controls"]) == 2
    c.validate_operational_plan(plan, c.make_candidate())


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "expectation", "pass", "path", "inheritance"]
)
def test_mapped_access_plan_cannot_claim_unperformed_or_changed_checks(change: str) -> None:
    c = contract()
    candidate = c.make_candidate()
    plan = c.build_operational_plan(candidate)
    if change == "missing":
        plan["checks"].pop()
    elif change == "duplicate":
        plan["checks"].append(plan["checks"][0])
    elif change == "inheritance":
        plan["topology"]["share_root_with_annotators"] = True
    else:
        key, value = {
            "expectation": ("expected_outcome", "INVALID"),
            "pass": ("status", "PASS"),
            "path": ("path", "../../outside"),
        }[change]
        plan["checks"][0][key] = value
    with pytest.raises(ValueError):
        c.validate_operational_plan(plan, candidate)


def test_scientific_contract_is_bound_not_merely_named() -> None:
    c = contract()
    payload = c.make_candidate().model_dump(mode="json")
    assert "contract_identity" in payload
    payload["contract_identity"]["evaluator_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        c.OperationalCandidate.model_validate(payload)
