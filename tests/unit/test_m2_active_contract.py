"""Active custody contracts and owner-confirmed date pairs; invented evidence only."""

import json
from pathlib import Path

import pytest
import yaml
from test_m2_issuance import package

from peru_conflicts.benchmark.models import FieldAnnotation
from peru_conflicts.execution.coordination import package_identity
from peru_conflicts.execution.source_dates import validate_date_pair


@pytest.mark.parametrize(
    "field,value",
    [
        ("scientific_schema_version", "0.3.0"),
        ("scientific_schema_digest", "f" * 64),
        ("benchmark_schema_version", "0.1.0"),
        ("benchmark_schema_digest", "f" * 64),
        ("date_correction_approval_sha256", "f" * 64),
        ("metric_contract_version", "0.1.0"),
        ("evaluator_sha256", "f" * 64),
        ("critical_field_set_sha256", "f" * 64),
        ("discovery_policy_approval_sha256", "f" * 64),
        ("date_pair_interpretation_sha256", "f" * 64),
    ],
)
def test_contract_mutation_rejects_package_and_trusted_receipt(field: str, value: str) -> None:
    from test_m2_issuance import attestation

    from peru_conflicts.execution import coordination as c
    from peru_conflicts.execution.packages import verify_package

    files = (package("annotator-a"), package("annotator-b"))
    people = (attestation("annotator-a", "invented-a"), attestation("annotator-b", "invented-b"))
    bindings = c.bind_eligibility_pair(people, files)
    receipts = tuple(c.issuance_receipt(b) for b in bindings)
    payload = json.loads(files[0]["PACKAGE_MANIFEST.json"])
    payload["contract_identity"][field] = value
    changed = files[0] | {"PACKAGE_MANIFEST.json": json.dumps(payload).encode()}
    with pytest.raises(ValueError):
        verify_package(changed)
    with pytest.raises(ValueError):
        c.verify_trusted_package(changed, receipts[0])
    contract = receipts[0].identity.contract_identity.model_copy(update={field: value})
    identity = receipts[0].identity.model_copy(update={"contract_identity": contract})
    stale = receipts[0].model_copy(update={"identity": identity})
    with pytest.raises(ValueError):
        c.verify_trusted_package(files[0], stale)
    with pytest.raises(ValueError):
        c.verify_issuance_pair(people, files, bindings, (stale, receipts[1]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("scientific_schema_version", "0.3.0"),
        ("benchmark_schema_version", "0.1.0"),
        ("date_correction_approval_sha256", "f" * 64),
        ("metric_contract_version", "0.1.0"),
    ],
)
def test_run_drift_rejected_before_building_package(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    original = Path.read_bytes

    def changed(path: Path) -> bytes:
        data = original(path)
        if path.name == "m2_02_annotation_run_v1.yaml":
            payload = yaml.safe_load(data)
            payload[field] = value
            return yaml.safe_dump(payload).encode()
        return data

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="run/readiness"):
        package("annotator-a")


def test_contract_changes_package_id_and_rejects_prebinding_manifest() -> None:
    import hashlib

    from peru_conflicts.execution.packages import verify_package
    from peru_conflicts.hashing import canonical_json_bytes

    files = package("annotator-a")
    payload = json.loads(files["PACKAGE_MANIFEST.json"])
    old_id = hashlib.sha256(
        canonical_json_bytes(
            [
                payload["run_id"],
                payload["role"],
                [m.snapshot_sha256 for m in verify_package(files).references],
            ]
        )
    ).hexdigest()
    assert payload["package_id"] != old_id
    del payload["contract_identity"]
    with pytest.raises(ValueError):
        verify_package(files | {"PACKAGE_MANIFEST.json": json.dumps(payload).encode()})


def test_unlaunched_run_uses_active_readiness_versions() -> None:
    run = yaml.safe_load(Path("config/benchmark/m2_02_annotation_run_v1.yaml").read_bytes())
    ready = yaml.safe_load(Path("config/benchmark/m2_02a_readiness_v2.yaml").read_bytes())
    assert run["scientific_schema_version"] == ready["scientific_schema"].removeprefix("v")
    assert run["benchmark_schema_version"] == ready["benchmark_schema"].removeprefix("v")


def test_package_and_issuance_explicitly_bind_active_contract() -> None:
    files = package("annotator-a")
    manifest = json.loads(files["PACKAGE_MANIFEST.json"])
    identity = package_identity(files).model_dump(mode="json")
    assert "contract_identity" in manifest
    assert "contract_identity" in identity
    assert manifest["contract_identity"] == identity["contract_identity"]
    assert identity["contract_identity"]["scientific_schema_version"] == "0.3.1"
    assert identity["contract_identity"]["benchmark_schema_version"] == "0.1.1"


def test_issuance_has_its_own_explicit_contract_binding() -> None:
    assert "contract_identity" in package_identity(package("annotator-a")).model_dump()


def test_cross_layer_validator_exists() -> None:
    from peru_conflicts.execution import packages

    assert callable(getattr(packages, "validate_annotation_contract_alignment", None))


def test_contract_index_rejects_authority_and_payload_expansion() -> None:
    from peru_conflicts.execution.evidence_index import validate_evidence_index

    path = Path("docs/m2_02a_readiness_evidence_index_v3.yaml")
    assert path.exists()
    index = validate_evidence_index(path.read_bytes())
    assert index.owner_readiness_approved is False
    payload = index.model_dump(mode="json")
    for extra in ({"owner_readiness_approved": True}, {"source_text": "not allowed"}):
        with pytest.raises(ValueError):
            validate_evidence_index(yaml.safe_dump(payload | extra, sort_keys=False).encode())


def date_slot(family: str, prefix: str, precision: bool, state: str) -> FieldAnnotation:
    field = f"{prefix}_date_{'precision_original' if precision else 'original'}"
    return FieldAnnotation.model_validate_json(
        json.dumps(
            {
                "annotation_id": f"invented-{field}",
                "unit_id": "invented-unit",
                "annotator_id": "invented-person",
                "domain_object_type": family,
                "field_name": field,
                "state": state,
                "raw_value_json": json.dumps("month" if precision else "enero de 2026")
                if state == "observed"
                else "0"
                if state == "explicit_zero"
                else None,
                "uncertainty_comment": "Invented unresolved evidence"
                if state in {"source_ambiguous", "annotation_uncertain"}
                else None,
                "evidence_anchors": [
                    {
                        "report_id": "invented",
                        "report_number": 260,
                        "source_sha256": "a" * 64,
                        "page": 1,
                        "section": "invented",
                        "granularity": "page_only",
                        "page_only_rationale": "Synthetic diagnostic",
                    }
                ],
            }
        )
    )


@pytest.mark.parametrize("family,prefix", [("dp_action", "action"), ("alert", "alert")])
@pytest.mark.parametrize(
    "date_state,precision_state,valid",
    [
        ("observed", "observed", True),
        ("observed", "not_reported", False),
        ("not_reported", "observed", False),
        ("not_reported", "not_reported", True),
        ("observed", "source_ambiguous", True),
        ("observed", "annotation_uncertain", True),
        ("observed", "illegible_uninspectable", True),
        ("explicit_zero", "not_reported", False),
    ],
)
def test_resolved_date_pair_requires_both_observed_without_resolving_uncertainty(
    family: str, prefix: str, date_state: str, precision_state: str, valid: bool
) -> None:
    slots = {
        f"{family}.{s.field_name}": s
        for s in (
            date_slot(family, prefix, False, date_state),
            date_slot(family, prefix, True, precision_state),
        )
    }
    before = {k: v.model_dump_json() for k, v in slots.items()}
    if valid:
        validate_date_pair(slots, family)
    else:
        with pytest.raises(ValueError):
            validate_date_pair(slots, family)
    assert {k: v.model_dump_json() for k, v in slots.items()} == before
