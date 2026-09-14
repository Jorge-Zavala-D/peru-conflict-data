"""Invented rehearsal evidence only; no real people, account tests or issuance."""

import importlib.util
import json
from pathlib import Path
from typing import Literal, TypedDict

import pytest

from peru_conflicts.execution import coordination as c
from peru_conflicts.execution import launch as l
from peru_conflicts.execution.contracts import active_annotation_contract
from peru_conflicts.execution.packages import build_package
from peru_conflicts.execution.references import build_manifest, sha256
from peru_conflicts.execution.runtime_build import build_neutral_view, build_runtime


class Rehearsal(TypedDict):
    candidate: l.LaunchCandidate
    expected_candidate_sha256: str
    identities: tuple[l.LaunchIdentity, ...]
    people: tuple[c.EligibilityAttestation, ...]
    packages: tuple[dict[str, bytes], ...]
    bindings: tuple[l.CompositeEligibilityBinding, ...]
    receipts: tuple[c.PackageIssuanceReceipt, ...]
    runtime_receipts: tuple[bytes, ...]
    runtime_receipt_sha256s: tuple[str, ...]
    access: tuple[l.AccessReceipt, ...]
    ceremony: l.CeremonyEvidence


def test_launch_without_owner_approval_is_denied() -> None:
    assert importlib.util.find_spec("peru_conflicts.execution.launch") is not None, (
        "draft launch preflight is missing"
    )
    from peru_conflicts.execution.launch import production_launch_preflight

    with pytest.raises(ValueError, match="unapproved"):
        production_launch_preflight()


def test_not_run_access_cannot_pass() -> None:
    assert importlib.util.find_spec("peru_conflicts.execution.launch") is not None, (
        "draft launch preflight is missing"
    )
    from peru_conflicts.execution.launch import AccessReceipt

    with pytest.raises(ValueError, match="real-account"):
        AccessReceipt(
            kind="REAL_ACCOUNT_ACCESS_TEST",
            check_id="a-read-own-issue",
            composite_pair_sha256="a" * 64,
            status="PASS",
        )


def test_production_lock_remains_denied_before_launch() -> None:
    assert importlib.util.find_spec("peru_conflicts.execution.launch") is not None, (
        "draft launch preflight is missing"
    )
    from peru_conflicts.execution.launch import RehearsalResult

    result = RehearsalResult(prerequisites_satisfied=True, failures=())
    assert result.annotation_launch_approved is False
    assert result.production_locking_enabled is False
    assert result.status == "SYNTHETIC_REHEARSAL_ONLY"


def person(role: Literal["annotator-a", "annotator-b"], token: str) -> c.EligibilityAttestation:
    return c.EligibilityAttestation(
        role=role,
        private_person_token=token,
        distinct_human_confirmed=True,
        machine_answers_seen=False,
        parser_predictions_seen=False,
        machine_prefill_seen=False,
        other_submission_seen=False,
        partition_labels_received=False,
    )


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory: pytest.TempPathFactory) -> Rehearsal:
    root = tmp_path_factory.mktemp("launch")
    runtime = build_runtime(root / "runtime")
    pages = {1: b"Invented evidence for launch rehearsal.\n"}
    refs = [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    packages = tuple(
        build_package("synthetic-run", role, refs) for role in ("annotator-a", "annotator-b")
    )
    views = tuple(build_neutral_view(files, root / str(i)) for i, files in enumerate(packages))
    identities = tuple(
        l.compose_identity(c.package_identity(files), view, runtime)
        for files, view in zip(packages, views, strict=True)
    )
    candidate = l.LaunchCandidate(
        protected_main_merge_sha="995b54115f94454fc81d4af36f138add43ba8614",
        protected_main_merge_tree="67284c356125d4f9758dc28a9e6c92a45cab3553",
        readiness_v3_sha256="b6fd726b2f7067cb38e8e04df51eb9f39d7f6928837775a747beb4b5e3dcc4a2",
        evidence_v5_sha256="5cd65a2d78884e9744ef2cc8c21bbbf9ef4bfe1342553c62c11f29156034f224",
        reference_manifest_sha256="060d6f166e35400ba53d563fb75dfae4c4872d22796b12762e35bd6d15f88202",
        contract_identity=active_annotation_contract(),
        identities=(identities[0], identities[1]),
    )
    people = (
        person("annotator-a", "synthetic-private-a"),
        person("annotator-b", "synthetic-private-b"),
    )
    bindings = l.bind_synthetic_eligibility(
        people,
        packages,
        identities,
        model_as_annotator=(False, False),
        held_out_labels_seen=(False, False),
    )
    access = tuple(
        l.AccessReceipt(
            kind="SYNTHETIC_ACCESS_REHEARSAL",
            check_id=check,
            composite_pair_sha256=l.pair_sha256(identities),
            status="PASS",
        )
        for check in l.ACCESS_CHECKS
    )
    ceremony = l.CeremonyEvidence(
        composite_pair_sha256=l.pair_sha256(identities), steps=l.CEREMONY_STEPS
    )
    runtime_receipts = tuple(
        json.dumps(
            {
                "kind": "UNISSUED_RUNTIME_REHEARSAL",
                "runtime_sha256": identity.runtime_sha256,
                "dependency_sha256": identity.dependency_sha256,
                "launcher_sha256": identity.launcher_sha256,
                "interpreter_sha256": identity.interpreter_sha256,
                "view_sha256": identity.view_sha256,
                "original_package_sha256": identity.original.manifest_sha256,
                "contract_sha256": identity.runtime_contract_sha256,
                "role": identity.original.role,
                "run_id": "synthetic-run",
            },
            sort_keys=True,
        ).encode()
        for identity in identities
    )
    return Rehearsal(
        candidate=candidate,
        expected_candidate_sha256=l.model_sha256(candidate),
        identities=identities,
        people=people,
        packages=packages,
        bindings=bindings,
        receipts=tuple(c.issuance_receipt(binding.original_binding) for binding in bindings),
        runtime_receipts=runtime_receipts,
        runtime_receipt_sha256s=tuple(sha256(raw) for raw in runtime_receipts),
        access=access,
        ceremony=ceremony,
    )


def test_complete_synthetic_prerequisites_never_authorize(rehearsal: Rehearsal) -> None:
    result = l.synthetic_launch_preflight(**rehearsal)
    assert result.prerequisites_satisfied is True
    assert result.failures == ()
    assert result.annotation_launch_approved is False
    assert result.production_locking_enabled is False
    originals = c.bind_eligibility_pair(rehearsal["people"], rehearsal["packages"])
    receipts = tuple(c.issuance_receipt(binding) for binding in originals)
    with pytest.raises(ValueError, match="disabled"):
        c.production_lock_preflight(rehearsal["people"], rehearsal["packages"], originals, receipts)


@pytest.mark.parametrize(
    "missing",
    [
        "launch_authority",
        "external_write_authority",
        "private_eligibility",
        "distinct_people",
        "real_access_tests",
        "external_paths_and_permissions",
        "independent_issued_bytes",
    ],
)
def test_missing_ceremony_step_denies(rehearsal: Rehearsal, missing: str) -> None:
    args = rehearsal.copy()
    ceremony = l.CeremonyEvidence(
        composite_pair_sha256=l.pair_sha256(args["identities"]),
        steps=tuple(step for step in l.CEREMONY_STEPS if step != missing),
    )
    args["ceremony"] = ceremony
    result = l.synthetic_launch_preflight(**args)
    assert not result.prerequisites_satisfied
    assert "ceremony_incomplete_or_out_of_order" in result.failures


@pytest.mark.parametrize("status", ["NOT RUN", "FAIL"])
def test_access_not_run_or_failed_blocks_rehearsal(rehearsal: Rehearsal, status: str) -> None:
    args = rehearsal.copy()
    access = tuple(args["access"])
    args["access"] = (access[0].model_copy(update={"status": status}), *access[1:])
    result = l.synthetic_launch_preflight(**args)
    assert not result.prerequisites_satisfied
    assert "access_checks_incomplete_or_failed" in result.failures


@pytest.mark.parametrize(
    "change",
    [
        "same_human",
        "role",
        "package",
        "runtime",
        "view",
        "binding",
        "machine",
        "held_out",
        "model",
        "access_identity",
        "access_route",
        "duplicate_access",
        "order",
        "candidate_substitution",
    ],
)
def test_identity_eligibility_and_routing_fail_closed(rehearsal: Rehearsal, change: str) -> None:
    args = rehearsal.copy()
    identities = tuple(args["identities"])
    people = tuple(args["people"])
    if change == "same_human":
        args["people"] = (people[0], person("annotator-b", "synthetic-private-a"))
    elif change == "role":
        args["people"] = people[::-1]
    elif change == "package":
        args["packages"] = tuple(args["packages"])[::-1]
    elif change in {"runtime", "view"}:
        field = "runtime_sha256" if change == "runtime" else "view_sha256"
        args["identities"] = (identities[0].model_copy(update={field: "f" * 64}), identities[1])
    elif change == "binding":
        args["bindings"] = tuple(args["bindings"])[::-1]
    elif change == "machine":
        args["people"] = (people[0].model_copy(update={"machine_answers_seen": True}), people[1])
    elif change in {"held_out", "model"}:
        bindings = tuple(args["bindings"])
        field = "held_out_labels_seen" if change == "held_out" else "model_as_annotator"
        args["bindings"] = (bindings[0].model_copy(update={field: True}), bindings[1])
    elif change in {"access_identity", "access_route", "duplicate_access"}:
        access = tuple(args["access"])
        if change == "duplicate_access":
            args["access"] = (access[1], *access[1:])
        else:
            field, value = (
                ("composite_pair_sha256", "f" * 64)
                if change == "access_identity"
                else ("check_id", "a-read-b-submission")
            )
            args["access"] = (access[0].model_copy(update={field: value}), *access[1:])
    elif change == "order":
        args["ceremony"] = args["ceremony"].model_copy(update={"steps": l.CEREMONY_STEPS[::-1]})
    else:
        args["candidate"] = args["candidate"].model_copy(
            update={"reference_manifest_sha256": "f" * 64}
        )
    result = l.synthetic_launch_preflight(**args)
    assert not result.prerequisites_satisfied
    assert result.annotation_launch_approved is False


def test_private_template_has_no_person_or_attestation() -> None:
    template = l.private_eligibility_template()
    assert template["kind"] == "BLANK_PRIVATE_ELIGIBILITY_TEMPLATE"
    assert all(value is None for name, value in template.items() if name != "kind")


def test_tracked_candidate_is_strict_non_authorizing() -> None:
    import yaml

    root = Path(__file__).resolve().parents[2]
    candidate = l.LaunchCandidate.model_validate_json(
        json.dumps(
            yaml.safe_load((root / "config/benchmark/m2_02_launch_candidate_v1.yaml").read_bytes())
        )
    )
    assert candidate.owner_readiness_approved is True
    assert candidate.status == "owner_review_draft"
    l.verify_candidate(candidate, l.model_sha256(candidate), candidate.identities)
    for field in l.DRAFT_FALSE_FLAGS:
        assert getattr(candidate, field) is False
        with pytest.raises(ValueError):
            l.LaunchCandidate.model_validate_json(
                candidate.model_copy(update={field: True}).model_dump_json()
            )


@pytest.mark.parametrize("value", [0, "false", None])
def test_literal_false_flags_reject_nonboolean_values(rehearsal: Rehearsal, value: object) -> None:
    with pytest.raises(ValueError):
        l.LaunchCandidate.model_validate_json(
            rehearsal["candidate"]
            .model_copy(update={"owner_launch_approved": value})
            .model_dump_json()
        )


def test_real_access_templates_remain_not_run(rehearsal: Rehearsal) -> None:
    receipts = l.real_access_test_template(rehearsal["identities"])
    assert receipts
    assert all(r.kind == "REAL_ACCOUNT_ACCESS_TEST" and r.status == "NOT RUN" for r in receipts)
    args = rehearsal.copy()
    args["access"] = receipts
    assert not l.synthetic_launch_preflight(**args).prerequisites_satisfied


@pytest.mark.parametrize("missing", ["people", "packages", "bindings", "access"])
def test_missing_private_custody_or_access_denies(rehearsal: Rehearsal, missing: str) -> None:
    args = rehearsal.copy()
    if missing == "people":
        args["people"] = ()
    elif missing == "packages":
        args["packages"] = ()
    elif missing == "bindings":
        args["bindings"] = ()
    else:
        args["access"] = ()
    assert not l.synthetic_launch_preflight(**args).prerequisites_satisfied


@pytest.mark.parametrize(
    "field", ["readiness_v3_sha256", "evidence_v5_sha256", "reference_manifest_sha256"]
)
def test_stale_governing_authority_denies_even_with_updated_candidate_pin(
    rehearsal: Rehearsal, field: str
) -> None:
    args = rehearsal.copy()
    args["candidate"] = args["candidate"].model_copy(update={field: "f" * 64})
    args["expected_candidate_sha256"] = l.model_sha256(args["candidate"])
    assert not l.synthetic_launch_preflight(**args).prerequisites_satisfied


def test_composite_rejects_wrong_original_view_lineage(tmp_path: Path) -> None:
    pages = {1: b"Invented line.\n"}
    refs = [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    a = build_package("synthetic-run", "annotator-a", refs)
    b = build_package("synthetic-run", "annotator-b", refs)
    runtime = build_runtime(tmp_path / "runtime")
    view = build_neutral_view(b, tmp_path / "view")
    with pytest.raises(ValueError, match="lineage"):
        l.compose_identity(c.package_identity(a), view, runtime)
    with pytest.raises(ValueError, match="runtime"):
        l.compose_identity(
            c.package_identity(b), view, runtime.model_copy(update={"runtime_sha256": "f" * 64})
        )


def test_access_routes_encode_denials_not_just_pass_labels() -> None:
    assert l.ACCESS_CHECKS["a-list-other-issue"] == (
        "annotator-a",
        "list",
        "annotator-b/issue",
        "deny",
    )
    assert l.ACCESS_CHECKS["b-read-other-submission"] == (
        "annotator-b",
        "read",
        "annotator-a/submission",
        "deny",
    )
    assert l.ACCESS_CHECKS["a-read-held-out-sealed"] == (
        "annotator-a",
        "read",
        "coordinator/held-out-sealed",
        "deny",
    )
    assert l.ACCESS_CHECKS["coordinator-read-custody"] == (
        "coordinator",
        "read",
        "coordinator/custody",
        "allow",
    )


@pytest.mark.parametrize("field", ["model_as_annotator", "held_out_labels_seen"])
def test_prohibited_exposure_cannot_create_synthetic_binding(
    rehearsal: Rehearsal, field: str
) -> None:
    with pytest.raises(ValueError, match="prohibited"):
        l.bind_synthetic_eligibility(
            rehearsal["people"],
            rehearsal["packages"],
            rehearsal["identities"],
            model_as_annotator=(field == "model_as_annotator", False),
            held_out_labels_seen=(field == "held_out_labels_seen", False),
        )


@pytest.mark.parametrize(
    "change",
    [
        "missing_original",
        "original_role",
        "missing_runtime",
        "runtime_role",
        "runtime_pin",
        "self_consistent_runtime",
        "runtime_extra",
    ],
)
def test_missing_or_substituted_receipts_deny(rehearsal: Rehearsal, change: str) -> None:
    args = rehearsal.copy()
    if change == "missing_original":
        args["receipts"] = ()
    elif change == "original_role":
        args["receipts"] = args["receipts"][::-1]
    elif change == "missing_runtime":
        args["runtime_receipts"] = ()
    elif change == "runtime_role":
        args["runtime_receipts"] = args["runtime_receipts"][::-1]
    elif change == "runtime_pin":
        args["runtime_receipt_sha256s"] = ("f" * 64, "f" * 64)
    else:
        raw = json.loads(args["runtime_receipts"][0])
        if change == "runtime_extra":
            raw["issued"] = True
        else:
            raw["runtime_sha256"] = "f" * 64
        replacement = json.dumps(raw).encode()
        args["runtime_receipts"] = (replacement, args["runtime_receipts"][1])
        args["runtime_receipt_sha256s"] = (sha256(replacement), args["runtime_receipt_sha256s"][1])
    assert not l.synthetic_launch_preflight(**args).prerequisites_satisfied


@pytest.mark.parametrize(
    "field",
    [
        "parser_predictions_seen",
        "machine_prefill_seen",
        "other_submission_seen",
        "partition_labels_received",
    ],
)
def test_existing_exposure_rules_preserved(rehearsal: Rehearsal, field: str) -> None:
    args = rehearsal.copy()
    args["people"] = (args["people"][0].model_copy(update={field: True}), args["people"][1])
    assert not l.synthetic_launch_preflight(**args).prerequisites_satisfied
