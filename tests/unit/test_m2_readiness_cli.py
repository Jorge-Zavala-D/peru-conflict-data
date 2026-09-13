"""Human operation uses line/column and CSV, never handwritten canonical model JSON."""

from pathlib import Path

import pytest

from peru_conflicts.execution import readiness_cli
from peru_conflicts.execution.coordination import (
    EligibilityAttestation,
    bind_eligibility_pair,
    issuance_receipt,
)
from peru_conflicts.execution.packages import build_package, publish_new
from peru_conflicts.execution.references import build_manifest, sha256
from peru_conflicts.hashing import canonical_json_bytes


def test_reader_rejects_self_consistent_package_without_trusted_issuance(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-unbound"
    root.mkdir()
    pages = {1: b"Invented replacement.\n"}
    package = build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    for name, data in package.items():
        publish_new(root, name, data)
    with pytest.raises(ValueError, match="issuance"):
        readiness_cli.load_package(root)


def test_position_helper_and_blank_validation_are_neutral(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "m2-readiness-human-package"
    root.mkdir()
    pages = {1: "Árbol 😀\nSecond invented line.\n".encode()}
    package = build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    for name, data in package.items():
        publish_new(root, name, data)
    people = tuple(
        EligibilityAttestation(
            role=role,
            private_person_token="synthetic-" + role,
            distinct_human_confirmed=True,
            machine_answers_seen=False,
            parser_predictions_seen=False,
            machine_prefill_seen=False,
            other_submission_seen=False,
            partition_labels_received=False,
        )
        for role in ("annotator-a", "annotator-b")
    )
    other = build_package(
        "synthetic-run", "annotator-b", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    receipt = issuance_receipt(bind_eligibility_pair(people, (package, other))[0])
    receipt_bytes = canonical_json_bytes(receipt.model_dump(mode="json")) + b"\n"
    receipt_path = tmp_path / "trusted-receipt.json"
    receipt_path.write_bytes(receipt_bytes)

    def run(args: list[str]) -> int:
        return readiness_cli.main(
            [*args, "--issuance", str(receipt_path), "--issuance-sha256", sha256(receipt_bytes)]
        )

    assert (
        run(
            [
                "position",
                str(root),
                "--report",
                "260",
                "--page",
                "1",
                "--line",
                "1",
                "--column",
                "7",
            ]
        )
        == 0
    )
    selected = capsys.readouterr().out
    assert '"offset":6' in selected and "😀" in selected
    assert "not a scientific start recommendation" in selected
    assert run(["validate", str(root)]) == 0
    status = capsys.readouterr().out
    assert '"complete":false' in status
    assert "partition" not in status and "locked" not in status
    assert run(["slots", str(root)]) == 0
    assert capsys.readouterr().out.count("\n") == 1
    (root / "unexpected.csv").write_bytes(b"machine suggestion")
    assert run(["validate", str(root)]) == 2
    assert "unapproved" in capsys.readouterr().err
