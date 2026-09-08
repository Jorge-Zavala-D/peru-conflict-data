"""Package integrity and blinding tests use invented source references only."""

import json
from pathlib import Path

import pytest

from peru_conflicts.acquisition.fs_safety import DirectoryLeaseError
from peru_conflicts.execution import packages
from peru_conflicts.execution.references import build_manifest


def test_blank_package_is_equivalent_and_has_no_answer_or_partition_fields() -> None:
    pages = {1: b"Invented reference.\n"}
    manifest = build_manifest(260, "a" * 64, pages, "b" * 64)
    a = packages.build_package("synthetic-run", "annotator-a", [(manifest, pages)])
    b = packages.build_package("synthetic-run", "annotator-b", [(manifest, pages)])
    packages.verify_package(a)
    packages.assert_equivalent(a, b)
    metadata = json.loads(a["PACKAGE_MANIFEST.json"])
    assert metadata["role"] == "annotator-a"
    assert "partition_role" not in metadata
    assert all(len(a[name].splitlines()) == 1 for name in packages.FORM_HEADERS)
    for value in [
        b"partition_role",
        b"held_out_evaluation",
        b"NON_GOLD_MACHINE_REVIEW_AID",
        b"parser_results",
    ]:
        assert all(
            value not in content
            for name, content in a.items()
            if not name.startswith("references/")
        )


@pytest.mark.parametrize(
    "name", ["parser_results.json", "coordinator.json", "machine_suggestions.json"]
)
def test_extra_files_are_rejected(name: str) -> None:
    pages = {1: b"invented\n"}
    package = packages.build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    package[name] = b"{}"
    with pytest.raises(ValueError):
        packages.verify_package(package)


def test_prefilled_answers_and_corrupt_references_are_rejected() -> None:
    pages = {1: b"invented\n"}
    package = packages.build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    for name in ["annotations.csv", "references/260/0001.txt"]:
        changed = dict(package)
        changed[name] += b"answer"
        with pytest.raises(ValueError):
            packages.verify_package(changed)


def test_publication_is_write_new_and_confined_to_readiness(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-test"
    root.mkdir()
    packages.publish_new(root, "evidence.json", b"{}\n")
    with pytest.raises((ValueError, OSError, DirectoryLeaseError)):
        packages.publish_new(root, "evidence.json", b"changed")
    assert (root / "evidence.json").read_bytes() == b"{}\n"
    with pytest.raises(ValueError):
        packages.publish_new(Path.cwd(), "submission.json", b"{}")
    with pytest.raises(ValueError):
        packages.publish_new(root, "../escape", b"{}")
