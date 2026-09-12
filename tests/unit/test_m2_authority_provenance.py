"""Authority changes cannot silently mint a newly trusted readiness package."""

import argparse
import hashlib
import shlex
from pathlib import Path

import pytest
import yaml
from test_m2_issuance import package

from peru_conflicts.execution import contracts, packages, readiness_cli


def test_v4_evidence_cannot_claim_readiness_or_accept_an_old_contract() -> None:
    from peru_conflicts.execution.evidence_index import validate_evidence_index

    path = Path("docs/m2_02a_readiness_evidence_index_v4.yaml")
    index = validate_evidence_index(path.read_bytes())
    assert index.owner_readiness_approved is False
    payload = index.model_dump(mode="json")
    for field, value in [("owner_readiness_approved", True), ("source_answers", "forbidden")]:
        with pytest.raises(ValueError):
            validate_evidence_index(yaml.safe_dump(payload | {field: value}).encode())
    del payload["contract_identity"]["date_pair_interpretation_approval_sha256"]
    with pytest.raises(ValueError):
        validate_evidence_index(yaml.safe_dump(payload).encode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("interpretation_document_sha256", "f" * 64),
        ("owner", "Invented owner"),
        ("owner_readiness_approved", True),
        ("recorded_at", "2026-09-12T10:00:00"),
    ],
)
def test_altered_ratification_rejected_even_if_run_hash_is_recomputed(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    original = Path.read_bytes
    approval_name = "m2_02_date_pair_interpretation_approval_v1.yaml"
    payload = yaml.safe_load(original(Path("config/benchmark") / approval_name))
    payload[field] = value
    replacement = yaml.safe_dump(payload).encode()

    def changed(path: Path) -> bytes:
        if path.name == approval_name:
            return replacement
        data = original(path)
        if path.name == "m2_02_annotation_run_v1.yaml":
            run = yaml.safe_load(data)
            run["date_pair_interpretation_approval_sha256"] = hashlib.sha256(
                replacement
            ).hexdigest()
            return yaml.safe_dump(run).encode()
        return data

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError):
        package("annotator-a")


def test_changed_approval_record_rejected_by_run_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.read_bytes

    def changed(path: Path) -> bytes:
        data = original(path)
        return (
            data + b"\n" if path.name == "m2_02_date_pair_interpretation_approval_v1.yaml" else data
        )

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="run/readiness"):
        package("annotator-a")


def test_pre_ratification_package_and_receipt_cannot_be_used() -> None:
    import json

    from test_m2_issuance import attestation

    from peru_conflicts.execution import coordination as c

    files = (package("annotator-a"), package("annotator-b"))
    people = (attestation("annotator-a", "invented-a"), attestation("annotator-b", "invented-b"))
    binding = c.bind_eligibility_pair(people, files)
    receipts = tuple(c.issuance_receipt(b) for b in binding)
    manifest = json.loads(files[0]["PACKAGE_MANIFEST.json"])
    del manifest["contract_identity"]["date_pair_interpretation_approval_sha256"]
    with pytest.raises(ValueError):
        packages.verify_package(files[0] | {"PACKAGE_MANIFEST.json": json.dumps(manifest).encode()})
    receipt = receipts[0].model_dump(mode="json")
    del receipt["identity"]["contract_identity"]["date_pair_interpretation_approval_sha256"]
    with pytest.raises(ValueError):
        c.PackageIssuanceReceipt.model_validate_json(json.dumps(receipt))


@pytest.mark.parametrize(
    "name", ["m2_critical_fields_v1.yaml", "m2_02_date_pair_interpretation_v1.md"]
)
def test_changed_authority_bytes_cannot_build_fresh_package(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    original = Path.read_bytes

    def changed(path: Path) -> bytes:
        data = original(path)
        if path.name == name:
            # Same 40 fields, but different configured set; no real file mutation.
            return (
                data.replace(b"case_month.stock_status_original", b"case_month.invented_status")
                if name.endswith("yaml")
                else data + b"\nUnapproved interpretation\n"
            )
        return data

    assert (
        changed(Path("config/benchmark") / name) != original(Path("config/benchmark") / name)
        if name.endswith("yaml")
        else True
    )
    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError):
        package("annotator-a")


def test_run_pins_separate_owner_ratification_and_critical_set() -> None:
    run = yaml.safe_load(Path("config/benchmark/m2_02_annotation_run_v1.yaml").read_bytes())
    assert "date_pair_interpretation_approval_sha256" in run
    assert "critical_field_set_sha256" in run
    approval = Path("config/benchmark/m2_02_date_pair_interpretation_approval_v1.yaml")
    assert (
        run["date_pair_interpretation_approval_sha256"]
        == hashlib.sha256(approval.read_bytes()).hexdigest()
    )
    assert (
        contracts.active_annotation_contract().model_dump()[
            "date_pair_interpretation_approval_sha256"
        ]
        == run["date_pair_interpretation_approval_sha256"]
    )


@pytest.mark.parametrize("source", ["protocol", "guide"])
def test_documented_commands_parse_with_all_required_trust_arguments(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    text = (
        Path("docs/m2_02_annotation_execution_protocol.md").read_text(encoding="utf-8")
        if source == "protocol"
        else packages.FORM_GUIDE.decode()
    )
    commands = [
        line.strip().split("scripts/prepare_m2_annotation.py ", 1)[1]
        for line in text.splitlines()
        if "uv run python scripts/prepare_m2_annotation.py " in line
    ]
    parsed: list[argparse.Namespace] = []
    original = argparse.ArgumentParser.parse_args

    class Parsed(Exception):
        pass

    def parse(
        parser: argparse.ArgumentParser,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        result = original(parser, args, namespace)
        assert result is not None
        parsed.append(result)
        raise Parsed

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", parse)
    for command in commands:
        with pytest.raises(Parsed):
            readiness_cli.main(shlex.split(command))
    assert {p.command for p in parsed} == {
        "page",
        "position",
        "slots",
        "inspection-template",
        "validate",
    }
    assert all(
        str(p.issuance) == "COORDINATOR_RECEIPT" and p.issuance_sha256 == "TRUSTED_COORDINATOR_PIN"
        for p in parsed
    )
