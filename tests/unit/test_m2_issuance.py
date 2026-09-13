"""Invented identities and references only; no real attestation or issuance."""

import json
from typing import Literal

import pytest

from peru_conflicts.execution import coordination as c
from peru_conflicts.execution.packages import build_package
from peru_conflicts.execution.references import build_manifest


def attestation(
    role: Literal["annotator-a", "annotator-b"], token: str
) -> c.EligibilityAttestation:
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


def package(
    role: Literal["annotator-a", "annotator-b"], text: bytes = b"Invented source.\n"
) -> dict[str, bytes]:
    pages = {1: text}
    return build_package(
        "synthetic-run", role, [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )


def test_binding_is_required_and_remains_non_authorizing() -> None:
    people = (
        attestation("annotator-a", "synthetic-private-a"),
        attestation("annotator-b", "synthetic-private-b"),
    )
    files = (package("annotator-a"), package("annotator-b"))
    bindings = c.bind_eligibility_pair(people, files)
    receipts = tuple(c.issuance_receipt(b) for b in bindings)
    c.verify_issuance_pair(people, files, bindings, receipts)
    for receipt in receipts:
        raw = receipt.model_dump_json()
        assert "synthetic-private" not in raw and "partition" not in raw
        assert "person_token" not in raw
        assert receipt.annotation_launch_approved is False
    with pytest.raises(ValueError, match="disabled"):
        c.production_lock_preflight(people, files, bindings, receipts)


def test_same_human_or_wrong_role_cannot_bind_pair() -> None:
    files = (package("annotator-a"), package("annotator-b"))
    a = attestation("annotator-a", "synthetic-one")
    with pytest.raises(ValueError):
        c.bind_eligibility_pair((a, attestation("annotator-b", "synthetic-one")), files)
    with pytest.raises(ValueError):
        c.bind_eligibility_pair((a, attestation("annotator-b", "synthetic-two")), files[::-1])


@pytest.mark.parametrize(
    "mutation",
    [
        "attestation",
        "replacement",
        "reference",
        "manifest",
        "role",
        "package_id",
        "reference_aggregate",
        "binding",
        "launch",
    ],
)
def test_mutations_break_issuance_chain(mutation: str) -> None:
    people = (attestation("annotator-a", "synthetic-a"), attestation("annotator-b", "synthetic-b"))
    files = (package("annotator-a"), package("annotator-b"))
    bindings = c.bind_eligibility_pair(people, files)
    receipts = tuple(c.issuance_receipt(b) for b in bindings)
    if mutation == "attestation":
        people = (people[0].model_copy(update={"machine_answers_seen": True}), people[1])
    elif mutation == "replacement":
        files = (package("annotator-a", b"Different invented replacement.\n"), files[1])
    elif mutation == "reference":
        files[0]["references/260/0001.txt"] = b"Changed\n"
    elif mutation == "manifest":
        files[0]["PACKAGE_MANIFEST.json"] += b" "
    elif mutation in {"role", "package_id"}:
        payload = json.loads(files[0]["PACKAGE_MANIFEST.json"])
        payload[mutation] = "annotator-b" if mutation == "role" else "f" * 64
        files[0]["PACKAGE_MANIFEST.json"] = json.dumps(payload).encode()
    elif mutation == "reference_aggregate":
        identity = receipts[0].identity.model_copy(update={"reference_aggregate_sha256": "f" * 64})
        receipts = (receipts[0].model_copy(update={"identity": identity}), receipts[1])
    elif mutation == "binding":
        bindings = (bindings[0].model_copy(update={"attestation_sha256": "f" * 64}), bindings[1])
    else:
        receipts = (
            receipts[0].model_copy(update={"annotation_launch_approved": True}),
            receipts[1],
        )
    with pytest.raises(ValueError):
        c.verify_issuance_pair(people, files, bindings, receipts)


def test_neutral_reader_rejects_replacement_and_other_role() -> None:
    people = (attestation("annotator-a", "synthetic-a"), attestation("annotator-b", "synthetic-b"))
    files = (package("annotator-a"), package("annotator-b"))
    receipt = c.issuance_receipt(c.bind_eligibility_pair(people, files)[0])
    for replacement in (files[1], package("annotator-a", b"Self-consistent replacement.\n")):
        with pytest.raises(ValueError, match="issuance"):
            c.verify_trusted_package(replacement, receipt)
