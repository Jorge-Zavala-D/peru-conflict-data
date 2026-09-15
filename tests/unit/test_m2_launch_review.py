"""Review packets use invented evidence and never authorize operational actions."""

import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from peru_conflicts.execution.access_policy import ACCESS_POLICY_V2, ACCESS_POLICY_V2_SHA256
from peru_conflicts.execution.coordination import package_identity
from peru_conflicts.execution.launch import LaunchCandidate, compose_identity, model_sha256
from peru_conflicts.execution.packages import build_package
from peru_conflicts.execution.references import build_manifest, sha256
from peru_conflicts.execution.runtime_build import (
    RuntimeManifest,
    build_neutral_view,
    build_runtime,
)
from peru_conflicts.hashing import canonical_json_bytes


def review_module() -> Any:
    name = "peru_conflicts.execution.launch_review"
    assert importlib.util.find_spec(name) is not None, "review packet generator missing"
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def material(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("review-inputs")
    runtime = build_runtime(root / "runtime")
    pages = {1: b"Invented review evidence.\n"}
    references = [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    packages = [
        build_package("synthetic-run", role, references) for role in ("annotator-a", "annotator-b")
    ]
    views = [build_neutral_view(files, root / str(i)) for i, files in enumerate(packages)]
    identities = [
        compose_identity(package_identity(files), view, runtime)
        for files, view in zip(packages, views, strict=True)
    ]
    candidate_path = (
        Path(__file__).resolve().parents[2] / "config/benchmark/m2_02_launch_candidate_v1.yaml"
    )
    payload = yaml.safe_load(candidate_path.read_text())
    payload["identities"] = [identity.model_dump(mode="json") for identity in identities]
    candidate = LaunchCandidate.model_validate_json(json.dumps(payload))
    candidate_file = root / "candidate.json"
    candidate_file.write_text(candidate.model_dump_json(), encoding="utf-8")

    def pin(path: Path) -> dict[str, str]:
        return {"path": str(path), "sha256": sha256(path.read_bytes())}

    return {
        "candidate": pin(candidate_file),
        "candidate_model_sha256": model_sha256(candidate),
        "runtime": pin(root / "runtime/RUNTIME_MANIFEST.json"),
        "views": [pin(root / f"{i}/NEUTRAL_VIEW.json") for i in range(2)],
        "evidence": {},
    }


def test_packet_preserves_unresolved_launch_and_real_access(
    tmp_path: Path, material: dict[str, Any]
) -> None:
    module = review_module()
    result = module.prepare_review(tmp_path, "first", module.ReviewInputs.model_validate(material))
    dossier = json.loads((result / "owner_launch_decision_dossier.json").read_text())
    assert len(dossier["decisions"]) == 16
    assert all(row["response"] is None for row in dossier["decisions"])
    assert sum(row["can_decide_in_m2_02b1"] for row in dossier["decisions"]) == 9
    assert all(
        row["question"] and row["evidence_required"] and row["rejection_consequence"]
        for row in dossier["decisions"]
    )
    access = json.loads((result / "launch_access_test_protocol_receipt.json").read_text())
    assert access["protocol_version"] == "m2-02-real-access-tests-v2"
    assert access["access_policy_sha256"] == ACCESS_POLICY_V2_SHA256
    assert access["acl_check_count"] == len(ACCESS_POLICY_V2.acl_expectations)
    assert len(access["checks"]) == len(ACCESS_POLICY_V2.acl_expectations)
    assert {row["status"] for row in access["checks"]} == {"NOT RUN"}
    assert {row["control_layer"] for row in access["checks"]} == {"ACL"}
    assert {row["expected_outcome"] for row in access["checks"]} == {"ALLOW", "DENY"}
    assert len({row["check_id"] for row in access["checks"]}) == len(access["checks"])
    assert access["application_controls"] == [
        row.model_dump(mode="json") for row in ACCESS_POLICY_V2.application_controls
    ]
    topology = json.loads((result / "proposed_external_topology.json").read_text())
    assert isinstance(topology["areas"], list) and len(topology["areas"]) == 12
    assert topology["access_policy_version"] == ACCESS_POLICY_V2.policy_version
    assert topology["access_policy_sha256"] == ACCESS_POLICY_V2_SHA256
    assert all(len(area["acl_expectations"]) == 9 for area in topology["areas"])
    assert not (tmp_path / "06_validation").exists()
    packet = json.loads((result / "final_m2_02b1_packet.json").read_text())
    assert packet["completion_gates_satisfied"] is False
    assert packet["launch_authority"] is False
    assert packet["candidate_file_sha256"] == material["candidate"]["sha256"]
    for name, identity in packet["artifacts"].items():
        data = (result / name).read_bytes()
        assert identity == {"bytes": len(data), "sha256": sha256(data)}


def test_supplied_receipt_is_byte_pinned_and_missing_stage_is_not_success(
    tmp_path: Path, material: dict[str, Any]
) -> None:
    module = review_module()
    receipt = tmp_path / "measured.json"
    receipt.write_bytes(b'{"kind":"invented-measurement","exit_code":0}\n')
    values = {
        **material,
        "evidence": {
            "runtime_equivalence_receipt.json": {
                "path": str(receipt),
                "sha256": sha256(receipt.read_bytes()),
            }
        },
    }
    result = module.prepare_review(tmp_path, "measured", module.ReviewInputs.model_validate(values))
    assert (result / "runtime_equivalence_receipt.json").read_bytes() == receipt.read_bytes()
    missing = json.loads((result / "principal_review_receipt.json").read_text())
    assert missing["status"] == "NOT RUN"
    receipt.write_bytes(b'{"kind":"replacement"}')
    with pytest.raises(ValueError, match="hash"):
        module.prepare_review(tmp_path, "changed", module.ReviewInputs.model_validate(values))
    assert not (tmp_path / ".cache/m2-02b1/changed").exists()


@pytest.mark.parametrize("change", ["file_pin", "model_pin", "runtime", "view", "output_escape"])
def test_stale_or_escaping_inputs_fail_before_output(
    tmp_path: Path, material: dict[str, Any], change: str
) -> None:
    module = review_module()
    values = json.loads(json.dumps(material))
    name = "invalid"
    if change == "file_pin":
        values["candidate"]["sha256"] = "0" * 64
    elif change == "model_pin":
        values["candidate_model_sha256"] = "0" * 64
    elif change == "runtime":
        values["runtime"] = values["views"][0]
    elif change == "view":
        values["views"].reverse()
    else:
        name = "../../external"
    with pytest.raises(ValueError):
        module.prepare_review(tmp_path, name, module.ReviewInputs.model_validate(values))
    assert not (tmp_path / ".cache").exists()


def test_existing_snapshot_is_immutable(tmp_path: Path, material: dict[str, Any]) -> None:
    module = review_module()
    inputs = module.ReviewInputs.model_validate(material)
    result = module.prepare_review(tmp_path, "immutable", inputs)
    original = (result / "final_m2_02b1_packet.json").read_bytes()
    with pytest.raises(ValueError, match="exists"):
        module.prepare_review(tmp_path, "immutable", inputs)
    assert (result / "final_m2_02b1_packet.json").read_bytes() == original


def test_complete_mode_rejects_absent_or_self_asserted_success(
    tmp_path: Path, material: dict[str, Any]
) -> None:
    module = review_module()
    with pytest.raises(ValueError, match="completion"):
        module.prepare_review(
            tmp_path, "absent", module.ReviewInputs.model_validate(material), require_complete=True
        )
    receipt = tmp_path / "claimed.json"
    receipt.write_bytes(b'{"status":"PASS"}')
    values = {
        **material,
        "evidence": {
            "completion_gates.json": {"path": str(receipt), "sha256": sha256(receipt.read_bytes())}
        },
    }
    with pytest.raises(ValueError):
        module.prepare_review(
            tmp_path, "claimed", module.ReviewInputs.model_validate(values), require_complete=True
        )
    assert not (tmp_path / ".cache").exists()


def test_raw_measurement_output_is_preserved_and_pinned(
    tmp_path: Path, material: dict[str, Any]
) -> None:
    module = review_module()
    raw = tmp_path / "pytest.xml"
    raw.write_bytes(b'<testsuite tests="1" failures="0"/>\n')
    values = {
        **material,
        "raw_evidence": {"pytest.xml": {"path": str(raw), "sha256": sha256(raw.read_bytes())}},
    }
    result = module.prepare_review(tmp_path, "raw", module.ReviewInputs.model_validate(values))
    assert (result / "raw_evidence/pytest.xml").read_bytes() == raw.read_bytes()
    packet = json.loads((result / "final_m2_02b1_packet.json").read_text())
    assert packet["artifacts"]["raw_evidence/pytest.xml"]["sha256"] == sha256(raw.read_bytes())


@pytest.fixture
def complete_inputs(tmp_path: Path, material: dict[str, Any]) -> dict[str, Any]:
    inventory: dict[str, str] = {}
    for name in (
        "src/reviewed.py",
        "src/peru_conflicts/execution/runtime_build.py",
        "src/peru_conflicts/execution/runtime_cli.py",
        "src/peru_conflicts/execution/neutral_forms.py",
        "src/peru_conflicts/execution/launch.py",
        "tests/unit/test_m2_isolated_runtime.py",
        "tests/unit/test_m2_launch_preflight.py",
    ):
        source = tmp_path / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"invented source snapshot\n")
        inventory[name] = sha256(source.read_bytes())
    snapshot = sha256(canonical_json_bytes(inventory))
    gates = (
        "new_m2",
        "all_m2",
        "benchmark",
        "scientific",
        "guards_acquisition",
        "full_pytest",
        "ruff_format",
        "ruff_lint",
        "pyright_windows",
        "pyright_linux",
        "schema_drift",
        "data_policy",
        "staged_byte_policy",
    )
    gate_receipt: dict[str, Any] = {
        "kind": "M2_02B1_MEASURED_COMPLETION_GATES",
        "source_files": inventory,
        "source_snapshot_sha256": snapshot,
        "checks": [
            {
                "gate": gate,
                "command": f"invented-measured-command {gate}",
                "exit_code": 0,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "source_snapshot_sha256": snapshot,
            }
            for gate in gates
        ],
        "review": {
            "source_snapshot_sha256": snapshot,
            "review_range": "invented-base..invented-source-snapshot",
            "critical": 0,
            "important": 0,
            "minor_findings": [],
        },
        "ci": {
            "head_sha": "1" * 40,
            "merge_ref_sha": "2" * 40,
            "source_snapshot_sha256": snapshot,
            "new_m2_safety_skips": 0,
            "contexts": [
                {
                    "name": name,
                    "conclusion": "success",
                    "head_sha": "1" * 40,
                    "merge_ref_sha": "2" * 40,
                    "run_id": "invented-run",
                }
                for name in ("quality (3.12)", "quality (3.13)", "windows-acquisition-safety")
            ],
        },
    }
    path = tmp_path / "completion.json"
    path.write_bytes(canonical_json_bytes(gate_receipt))
    candidate = json.loads(Path(material["candidate"]["path"]).read_text())
    runtime = json.loads(Path(material["runtime"]["path"]).read_text())
    baseline = {
        key: candidate[key]
        for key in (
            "protected_main_merge_sha",
            "protected_main_merge_tree",
            "readiness_v3_sha256",
            "evidence_v5_sha256",
            "reference_manifest_sha256",
        )
    }
    runtime_binding = {
        **baseline,
        "source_snapshot_sha256": snapshot,
        "runtime_sha256": runtime["runtime_sha256"],
        "view_sha256s": [item["view_sha256"] for item in candidate["identities"]],
    }
    contexts = ["quality (3.12)", "quality (3.13)", "windows-acquisition-safety"]
    postmerge = {
        "merge": baseline["protected_main_merge_sha"],
        "tree": baseline["protected_main_merge_tree"],
        "recovery_pr": 15,
        "original_feature_preserved": True,
        "status": "POSTMERGE_VERIFIED_DESIGN_REVIEW_PENDING",
        "parents": [
            "cffe543c85738266c9bdd71bd011c5fe329d5481",
            "2ab5eb92d4c732d73a198e3b64690a7356f0ac2b",
        ],
    }
    historical_ci = {
        "head_sha": baseline["protected_main_merge_sha"],
        "status": "completed",
        "conclusion": "success",
        "jobs": [{"name": name, "conclusion": "success"} for name in contexts],
    }
    ruleset = {
        "ruleset": {
            "id": 21658925,
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "pull_request", "parameters": {"required_review_thread_resolution": True}},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [{"context": name} for name in contexts],
                    },
                },
            ],
        }
    }
    custody = {
        "merge_sha": baseline["protected_main_merge_sha"],
        "merge_tree": baseline["protected_main_merge_tree"],
        "readiness_sha256": baseline["readiness_v3_sha256"],
        "evidence_v5_sha256": baseline["evidence_v5_sha256"],
        "owner_readiness_approved": True,
        "annotation_launch_approved": False,
        "approval_sha256": candidate["contract_identity"]["owner_readiness_approval_sha256"],
    }
    core = {
        "kind": "MEASURED_LOCAL_TEST_EXECUTION",
        "command": (
            "uv run pytest tests/unit/test_m2_isolated_runtime.py "
            "tests/unit/test_m2_launch_preflight.py"
        ),
        "exit_code": 0,
        "passed": 2,
        "skipped": 0,
        "files": [{"path": name, "sha256": digest} for name, digest in inventory.items()],
        "annotation_started": False,
        "real_packages_issued": False,
        "human_gold_created": False,
    }
    dropbox = {
        "dropbox_writes": 0,
        "m2_external_root_absent": True,
        "verified_hashes": [{"path": "invented/source.pdf", "sha256": "a" * 64}],
    }
    observation_pairs = {
        "postmerge_verification_receipt.json": (postmerge, {"merge_verified": True}, baseline),
        "protected_main_ci_receipt.json": (
            historical_ci,
            {"required_contexts": sorted(contexts), "conclusion": "success"},
            baseline,
        ),
        "ruleset_receipt.json": (
            ruleset,
            {"ruleset_id": 21658925, "protected_main_enforced": True},
            baseline,
        ),
        "owner_readiness_custody_receipt.json": (
            custody,
            {"owner_readiness_approved": True, "annotation_launch_approved": False},
            baseline,
        ),
        "isolated_runtime_neutrality_receipt.json": (
            core,
            {"synthetic_test_coverage_passed": True, "real_annotation_performed": False},
            runtime_binding,
        ),
        "runtime_equivalence_receipt.json": (
            core,
            {"synthetic_test_coverage_passed": True, "real_annotation_performed": False},
            runtime_binding,
        ),
        "synthetic_launch_rehearsal_receipt.json": (
            core,
            {"synthetic_test_coverage_passed": True, "real_annotation_performed": False},
            runtime_binding,
        ),
        "dropbox_readonly_receipt.json": (
            dropbox,
            {"dropbox_writes": 0, "m2_external_root_absent": True, "preserved_baseline_files": 1},
            baseline,
        ),
        "principal_review_receipt.json": (
            {"kind": "MEASURED_INDEPENDENT_PRINCIPAL_REVIEW", "review": gate_receipt["review"]},
            gate_receipt["review"],
            {**baseline, "source_snapshot_sha256": snapshot},
        ),
        "final_ci_receipt.json": (
            {"kind": "MEASURED_FINAL_BRANCH_CI", "ci": gate_receipt["ci"]},
            gate_receipt["ci"],
            {**baseline, "source_snapshot_sha256": snapshot},
        ),
    }
    evidence: dict[str, Any] = {}
    raw_evidence: dict[str, Any] = {}
    for name, (raw, observations, bindings) in observation_pairs.items():
        raw_name = "original-" + name
        raw_path = tmp_path / raw_name
        raw_path.write_bytes(canonical_json_bytes(raw))
        raw_evidence[raw_name] = {"path": str(raw_path), "sha256": sha256(raw_path.read_bytes())}
        sources = {
            "observation": {
                "artifact": "raw_evidence/" + raw_name,
                "sha256": sha256(raw_path.read_bytes()),
            }
        }
        if name == "dropbox_readonly_receipt.json":
            baseline_path = tmp_path / "baseline-dropbox.json"
            baseline_path.write_bytes(canonical_json_bytes(dropbox))
            raw_evidence["baseline-dropbox.json"] = {
                "path": str(baseline_path),
                "sha256": sha256(baseline_path.read_bytes()),
            }
            sources["baseline"] = {
                "artifact": "raw_evidence/baseline-dropbox.json",
                "sha256": sha256(baseline_path.read_bytes()),
            }
        normalized = {
            "kind": "M2_02B1_MEASURED_TECHNICAL_STAGE",
            "stage": name,
            "status": "MEASURED_PASS",
            "bindings": bindings,
            "observations": observations,
            "sources": sources,
        }
        stage_path = tmp_path / name
        stage_path.write_bytes(canonical_json_bytes(normalized))
        evidence[name] = {"path": str(stage_path), "sha256": sha256(stage_path.read_bytes())}
    evidence["completion_gates.json"] = {"path": str(path), "sha256": sha256(path.read_bytes())}
    return {
        **material,
        "evidence": evidence,
        "raw_evidence": raw_evidence,
        "expected_source_snapshot_sha256": snapshot,
        "expected_final_head_sha": "1" * 40,
        "expected_merge_ref_sha": "2" * 40,
    }


def with_hardening_receipts(tmp_path: Path, values: dict[str, Any]) -> dict[str, Any]:
    module = review_module()
    candidate = LaunchCandidate.model_validate_json(Path(values["candidate"]["path"]).read_bytes())
    runtime = RuntimeManifest.model_validate_json(Path(values["runtime"]["path"]).read_bytes())
    evidence = dict(values["evidence"])
    for name, body in module.hardening_receipt_documents(candidate, runtime).items():
        path = tmp_path / name
        path.write_bytes(canonical_json_bytes(body))
        evidence[name] = {"path": str(path), "sha256": sha256(path.read_bytes())}
    return {**values, "evidence": evidence}


@pytest.mark.parametrize(
    "receipt",
    [
        "access_policy_v2_receipt.json",
        "python_environment_trust_receipt.json",
        "runtime_identity_receipt.json",
    ],
)
def test_hardening_completion_requires_new_receipts(
    tmp_path: Path, complete_inputs: dict[str, Any], receipt: str
) -> None:
    module = review_module()
    values = with_hardening_receipts(tmp_path, complete_inputs)
    del values["evidence"][receipt]
    with pytest.raises(ValueError, match=r"hardening.*receipt"):
        module.prepare_review(
            tmp_path,
            "hardening-missing",
            module.ReviewInputs.model_validate(values),
            require_complete=True,
            cache_namespace="m2-02b1b",
        )
    assert not (tmp_path / ".cache/m2-02b1b/hardening-missing").exists()


@pytest.mark.parametrize(
    "receipt,field,replacement",
    [
        ("access_policy_v2_receipt.json", "access_policy_sha256", "0" * 64),
        ("access_policy_v2_receipt.json", "acl_check_count", 48),
        ("access_policy_v2_receipt.json", "real_account_test_status", "PASS"),
        ("python_environment_trust_receipt.json", "python_environment_sha256", "0" * 64),
        ("python_environment_trust_receipt.json", "python_environment_manifest_sha256", "0" * 64),
        ("python_environment_trust_receipt.json", "production_approved", True),
        ("runtime_identity_receipt.json", "runtime_sha256", "0" * 64),
    ],
)
def test_hardening_rejects_stale_receipts_even_in_incomplete_mode(
    tmp_path: Path, material: dict[str, Any], receipt: str, field: str, replacement: object
) -> None:
    module = review_module()
    values = with_hardening_receipts(tmp_path, material)
    path = Path(values["evidence"][receipt]["path"])
    body = json.loads(path.read_bytes())
    body[field] = replacement
    path.write_bytes(canonical_json_bytes(body))
    values["evidence"][receipt]["sha256"] = sha256(path.read_bytes())
    with pytest.raises(ValueError, match="hardening receipt is stale"):
        module.prepare_review(
            tmp_path,
            "stale",
            module.ReviewInputs.model_validate(values),
            cache_namespace="m2-02b1b",
        )
    assert not (tmp_path / ".cache/m2-02b1b/stale").exists()


def test_new_hardening_snapshot_is_incomplete_and_preserves_historical_bytes(
    tmp_path: Path, material: dict[str, Any]
) -> None:
    module = review_module()
    old = module.prepare_review(tmp_path, "old", module.ReviewInputs.model_validate(material))
    before = {path.name: path.read_bytes() for path in old.iterdir()}
    values = with_hardening_receipts(tmp_path, material)
    new = module.prepare_review(
        tmp_path, "initial", module.ReviewInputs.model_validate(values), cache_namespace="m2-02b1b"
    )
    packet = json.loads((new / "final_m2_02b1_packet.json").read_bytes())
    assert packet["hardening_review_status"] == "INCOMPLETE"
    assert packet["completion_gates_satisfied"] is False
    assert "final_ci_receipt.json" in packet["missing_measured_receipts"]
    assert "principal_review_receipt.json" in packet["missing_measured_receipts"]
    assert before == {path.name: path.read_bytes() for path in old.iterdir()}


def test_hardening_cache_namespace_is_validated(tmp_path: Path, material: dict[str, Any]) -> None:
    module = review_module()
    with pytest.raises(ValueError, match="cache namespace"):
        module.prepare_review(
            tmp_path,
            "escape",
            module.ReviewInputs.model_validate(material),
            cache_namespace="../elsewhere",
        )


@pytest.mark.parametrize("cache_namespace", ["m2-02b1", "m2-02b1b"])
def test_complete_evidence_remains_preparation_without_launch(
    tmp_path: Path, complete_inputs: dict[str, Any], cache_namespace: str
) -> None:
    module = review_module()
    if cache_namespace == "m2-02b1b":
        complete_inputs = with_hardening_receipts(tmp_path, complete_inputs)
    result = module.prepare_review(
        tmp_path,
        "complete",
        module.ReviewInputs.model_validate(complete_inputs),
        require_complete=True,
        cache_namespace=cache_namespace,
    )
    packet = json.loads((result / "final_m2_02b1_packet.json").read_text())
    assert packet["completion_gates_satisfied"] is True
    assert packet["launch_authority"] is False
    assert packet["annotation_started"] is False


def test_completion_cannot_omit_unreviewed_source_file(
    tmp_path: Path, complete_inputs: dict[str, Any]
) -> None:
    module = review_module()
    (tmp_path / "src/unreviewed.py").write_bytes(b"changed implementation omitted from receipt\n")
    with pytest.raises(ValueError, match="inventory"):
        module.prepare_review(
            tmp_path,
            "omitted",
            module.ReviewInputs.model_validate(complete_inputs),
            require_complete=True,
        )
    assert not (tmp_path / ".cache").exists()


@pytest.mark.parametrize(
    "breakage",
    [
        "source",
        "missing_check",
        "check_failure",
        "empty_tests",
        "new_safety_skip",
        "review",
        "review_snapshot",
        "ci_context",
        "ci_head",
        "ci_merge",
        "ci_safety_skip",
    ],
)
def test_complete_mode_rejects_unmeasured_or_mismatched_gates(
    tmp_path: Path, complete_inputs: dict[str, Any], breakage: str
) -> None:
    module = review_module()
    path = Path(complete_inputs["evidence"]["completion_gates.json"]["path"])
    receipt = json.loads(path.read_text())
    if breakage == "source":
        (tmp_path / "src/reviewed.py").write_bytes(b"changed bytes")
    elif breakage == "missing_check":
        receipt["checks"].pop()
    elif breakage == "check_failure":
        receipt["checks"][0]["exit_code"] = 1
    elif breakage == "empty_tests":
        receipt["checks"][0]["passed"] = 0
    elif breakage == "new_safety_skip":
        receipt["checks"][0]["skipped"] = 1
    elif breakage == "review":
        receipt["review"]["important"] = 1
    elif breakage == "review_snapshot":
        receipt["review"]["source_snapshot_sha256"] = "f" * 64
    elif breakage == "ci_context":
        receipt["ci"]["contexts"].pop()
    elif breakage == "ci_head":
        receipt["ci"]["contexts"][0]["head_sha"] = "3" * 40
    elif breakage == "ci_merge":
        receipt["ci"]["merge_ref_sha"] = "3" * 40
    else:
        receipt["ci"]["new_m2_safety_skips"] = 1
    path.write_bytes(canonical_json_bytes(receipt))
    complete_inputs["evidence"]["completion_gates.json"]["sha256"] = sha256(path.read_bytes())
    with pytest.raises(ValueError):
        module.prepare_review(
            tmp_path,
            "invalid-complete",
            module.ReviewInputs.model_validate(complete_inputs),
            require_complete=True,
        )
    assert not (tmp_path / ".cache").exists()


@pytest.mark.parametrize(
    "stage",
    [
        "postmerge_verification_receipt.json",
        "protected_main_ci_receipt.json",
        "ruleset_receipt.json",
        "owner_readiness_custody_receipt.json",
        "isolated_runtime_neutrality_receipt.json",
        "runtime_equivalence_receipt.json",
        "synthetic_launch_rehearsal_receipt.json",
        "dropbox_readonly_receipt.json",
        "principal_review_receipt.json",
        "final_ci_receipt.json",
    ],
)
@pytest.mark.parametrize(
    "breakage",
    [
        "wrong_kind",
        "not_run",
        "wrong_stage",
        "stale_identity",
        "contradictory_source",
        "raw_status_not_run",
        "raw_identity_or_outcome",
    ],
)
def test_complete_rejects_unrelated_or_unmeasured_stage(
    tmp_path: Path, complete_inputs: dict[str, Any], stage: str, breakage: str
) -> None:
    module = review_module()
    pin = complete_inputs["evidence"][stage]
    path = Path(pin["path"])
    receipt = json.loads(path.read_text())
    if breakage == "wrong_kind":
        receipt = json.loads(
            Path(complete_inputs["evidence"]["completion_gates.json"]["path"]).read_text()
        )
    elif breakage == "not_run":
        receipt["status"] = "NOT RUN"
    elif breakage == "wrong_stage":
        receipt["stage"] = "unrelated-stage"
    elif breakage == "stale_identity":
        receipt["bindings"]["protected_main_merge_sha"] = "f" * 40
    else:
        source = receipt["sources"]["observation"]
        raw_name = source["artifact"].removeprefix("raw_evidence/")
        raw_pin = complete_inputs["raw_evidence"][raw_name]
        raw_path = Path(raw_pin["path"])
        raw = json.loads(raw_path.read_text())
        if breakage == "contradictory_source":
            raw = {"kind": "UNMEASURED_REVIEW_STAGE", "status": "NOT RUN"}
        elif breakage == "raw_status_not_run":
            raw["status"] = "NOT RUN"
        elif stage == "postmerge_verification_receipt.json":
            raw["merge"] = "f" * 40
        elif stage == "protected_main_ci_receipt.json":
            raw["jobs"][0]["conclusion"] = "failure"
        elif stage == "ruleset_receipt.json":
            raw["ruleset"]["enforcement"] = "disabled"
        elif stage == "owner_readiness_custody_receipt.json":
            raw["owner_readiness_approved"] = False
        elif stage in (
            "isolated_runtime_neutrality_receipt.json",
            "runtime_equivalence_receipt.json",
            "synthetic_launch_rehearsal_receipt.json",
        ):
            raw["files"][0]["sha256"] = "f" * 64
        elif stage == "dropbox_readonly_receipt.json":
            raw["verified_hashes"][0]["sha256"] = "f" * 64
        elif stage == "principal_review_receipt.json":
            raw["review"]["important"] = 1
        else:
            raw["ci"]["head_sha"] = "f" * 40
        raw_path.write_bytes(canonical_json_bytes(raw))
        raw_pin["sha256"] = sha256(raw_path.read_bytes())
        source["sha256"] = raw_pin["sha256"]
    path.write_bytes(canonical_json_bytes(receipt))
    pin["sha256"] = sha256(path.read_bytes())
    with pytest.raises(ValueError):
        module.prepare_review(
            tmp_path,
            "invalid-stage",
            module.ReviewInputs.model_validate(complete_inputs),
            require_complete=True,
        )
    assert not (tmp_path / ".cache").exists()


@pytest.mark.parametrize(
    "stage",
    [
        "isolated_runtime_neutrality_receipt.json",
        "runtime_equivalence_receipt.json",
        "synthetic_launch_rehearsal_receipt.json",
    ],
)
def test_runtime_stage_rejects_reported_failed_tests(
    tmp_path: Path, complete_inputs: dict[str, Any], stage: str
) -> None:
    module = review_module()
    pin = complete_inputs["evidence"][stage]
    path = Path(pin["path"])
    normalized = json.loads(path.read_text())
    source = normalized["sources"]["observation"]
    raw_pin = complete_inputs["raw_evidence"][source["artifact"].removeprefix("raw_evidence/")]
    raw_path = Path(raw_pin["path"])
    raw = json.loads(raw_path.read_text())
    raw["failed"] = 1
    raw_path.write_bytes(canonical_json_bytes(raw))
    raw_pin["sha256"] = sha256(raw_path.read_bytes())
    source["sha256"] = raw_pin["sha256"]
    path.write_bytes(canonical_json_bytes(normalized))
    pin["sha256"] = sha256(path.read_bytes())
    with pytest.raises(ValueError):
        module.prepare_review(
            tmp_path,
            "failed-stage",
            module.ReviewInputs.model_validate(complete_inputs),
            require_complete=True,
        )
    assert not (tmp_path / ".cache").exists()


@pytest.mark.parametrize(
    "stage",
    [
        "ruleset_receipt.json",
        "owner_readiness_custody_receipt.json",
        "postmerge_verification_receipt.json",
    ],
)
def test_historical_evidence_cannot_contradict_baseline_details(
    tmp_path: Path, complete_inputs: dict[str, Any], stage: str
) -> None:
    module = review_module()
    pin = complete_inputs["evidence"][stage]
    path = Path(pin["path"])
    normalized = json.loads(path.read_text())
    source = normalized["sources"]["observation"]
    raw_pin = complete_inputs["raw_evidence"][source["artifact"].removeprefix("raw_evidence/")]
    raw_path = Path(raw_pin["path"])
    raw = json.loads(raw_path.read_text())
    if stage == "ruleset_receipt.json":
        raw["ruleset"]["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
    elif stage == "owner_readiness_custody_receipt.json":
        raw["approval_sha256"] = "f" * 64
    else:
        raw["parents"] = ["f" * 40]
    raw_path.write_bytes(canonical_json_bytes(raw))
    raw_pin["sha256"] = sha256(raw_path.read_bytes())
    source["sha256"] = raw_pin["sha256"]
    path.write_bytes(canonical_json_bytes(normalized))
    pin["sha256"] = sha256(path.read_bytes())
    with pytest.raises(ValueError):
        module.prepare_review(
            tmp_path,
            "contradictory-history",
            module.ReviewInputs.model_validate(complete_inputs),
            require_complete=True,
        )
    assert not (tmp_path / ".cache").exists()
