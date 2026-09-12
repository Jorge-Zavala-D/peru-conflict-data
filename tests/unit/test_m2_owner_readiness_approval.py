"""Owner readiness closes decisions, never the independent launch gate."""

import hashlib
from pathlib import Path

import pytest
import yaml

from peru_conflicts.execution.contracts import active_annotation_contract
from peru_conflicts.execution.readiness_approval import OwnerReadinessApproval

APPROVAL = Path("config/benchmark/m2_02a_owner_readiness_approval_v1.yaml")


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "renamed", "scope", "launch", "dropbox", "parser", "m3"]
)
def test_owner_record_rejects_changed_decisions_or_authority(mutation: str) -> None:
    data = yaml.safe_load(APPROVAL.read_bytes())
    if mutation == "missing":
        data["decisions"].pop("HELDOUT-SEALING")
    elif mutation == "extra":
        data["decisions"]["INVENTED"] = data["decisions"]["HELDOUT-SEALING"]
    elif mutation == "renamed":
        data["decisions"]["RENAMED"] = data["decisions"].pop("HELDOUT-SEALING")
    elif mutation == "scope":
        data["decisions"]["LOCK-AND-SUPERSESSION"]["approved_scope"] = "production"
    else:
        field = {
            "launch": "annotation_launch_approved",
            "dropbox": "dropbox_writes_approved",
            "parser": "parser_work_approved",
            "m3": "m3_approved",
        }[mutation]
        data[field] = True
    with pytest.raises(ValueError):
        OwnerReadinessApproval.model_validate(data)


@pytest.mark.parametrize(
    "name",
    [
        "m2_02a_owner_readiness_approval_v1.yaml",
        "m2_02_annotation_run_v1.yaml",
        "m2_02a_readiness_v3.yaml",
    ],
)
def test_altered_owner_readiness_bytes_or_pins_reject_package(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from test_m2_issuance import package

    original = Path.read_bytes

    def changed(path: Path) -> bytes:
        data = original(path)
        if path.name != name:
            return data
        if name == APPROVAL.name:
            return data + b"\n"
        payload = yaml.safe_load(data)
        payload["owner_readiness_approval_sha256"] = "f" * 64
        return yaml.safe_dump(payload).encode()

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError):
        package("annotator-a")


def test_prereview_package_and_receipt_are_stale_but_launch_stays_disabled() -> None:
    import json

    from test_m2_issuance import attestation, package

    from peru_conflicts.execution import coordination as c
    from peru_conflicts.execution.packages import verify_package

    files = (package("annotator-a"), package("annotator-b"))
    people = (attestation("annotator-a", "invented-a"), attestation("annotator-b", "invented-b"))
    bindings = c.bind_eligibility_pair(people, files)
    receipt = c.issuance_receipt(bindings[0])
    manifest = json.loads(files[0]["PACKAGE_MANIFEST.json"])
    del manifest["contract_identity"]["owner_readiness_approval_sha256"]
    with pytest.raises(ValueError):
        verify_package(files[0] | {"PACKAGE_MANIFEST.json": json.dumps(manifest).encode()})
    old = receipt.model_dump(mode="json")
    del old["identity"]["contract_identity"]["owner_readiness_approval_sha256"]
    with pytest.raises(ValueError):
        c.PackageIssuanceReceipt.model_validate_json(json.dumps(old))
    with pytest.raises(ValueError):
        c.production_lock_preflight(
            people, files, bindings, (receipt, c.issuance_receipt(bindings[1]))
        )


def test_v5_records_readiness_without_launch_and_v4_stays_historical() -> None:
    from peru_conflicts.execution.evidence_index import validate_evidence_index

    old = validate_evidence_index(Path("docs/m2_02a_readiness_evidence_index_v4.yaml").read_bytes())
    assert old.owner_readiness_approved is False
    path = Path("docs/m2_02a_readiness_evidence_index_v5.yaml")
    assert path.exists(), "postapproval evidence index missing"
    new = validate_evidence_index(path.read_bytes())
    assert new.owner_readiness_approved is True
    assert new.annotation_launch_approved is False
    payload = new.model_dump(mode="json")
    payload["owner_readiness_approval_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        type(new).model_validate(payload)


def test_active_packages_bind_owner_readiness_approval() -> None:
    identity = active_annotation_contract().model_dump()
    assert "owner_readiness_approval_sha256" in identity
    approval = Path("config/benchmark/m2_02a_owner_readiness_approval_v1.yaml")
    assert (
        identity["owner_readiness_approval_sha256"]
        == hashlib.sha256(approval.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("name", ["m2_02_annotation_run_v1.yaml", "m2_02a_readiness_v3.yaml"])
def test_active_readiness_is_approved_without_launch(name: str) -> None:
    path = Path("config/benchmark") / name
    assert path.exists(), "owner-approved readiness successor is missing"
    data = yaml.safe_load(path.read_bytes())
    assert data.get("owner_readiness_approved") is True
    assert data["annotation_started"] is False
    assert data["human_gold_created"] is False
    assert data.get("launch_approved", data.get("annotation_launch_approved")) is False
