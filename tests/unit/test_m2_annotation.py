"""Synthetic forms: no real report values, humans, or gold."""

import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest

from peru_conflicts.acquisition.fs_safety import DirectoryLeaseError
from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES, PartitionRole
from peru_conflicts.execution import annotation
from peru_conflicts.execution.packages import FORM_HEADERS, build_package, verify_package
from peru_conflicts.execution.references import build_manifest


def validate(
    package: dict[str, bytes],
    partitions: dict[int, PartitionRole],
    *,
    require_complete: bool = False,
    expected_package: object = None,
) -> annotation.ValidatedDraft:
    from peru_conflicts.execution.packages import PackageManifest

    expected = (
        expected_package
        if isinstance(expected_package, PackageManifest)
        else PackageManifest.model_validate_json(package["PACKAGE_MANIFEST.json"])
    )
    return annotation.validate_forms(
        package, partitions, expected_package=expected, require_complete=require_complete
    )


def lock(
    root: Path,
    draft: annotation.ValidatedDraft,
    lock_id: str,
    locked_at: datetime,
    *,
    confirmed: bool,
    supersedes: str | None = None,
) -> str:
    return annotation.lock_synthetic(
        root,
        draft,
        lock_id,
        locked_at,
        expected_package=draft.package,
        confirmed=confirmed,
        supersedes=supersedes,
    )


def form(name: str, rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FORM_HEADERS[name].split(","), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def blank(role: str = "annotator-a") -> dict[str, bytes]:
    from typing import Literal, cast

    pages = {
        1: b"Same name. First invented block.\nSame name. Second invented block.\n",
        2: b"Continued invented block.\n",
    }
    return build_package(
        "synthetic-run",
        cast(Literal["annotator-a", "annotator-b"], role),
        [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)],
    )


def complete(package: dict[str, bytes], count: int = 0) -> None:
    package["inspection.csv"] = form(
        "inspection.csv",
        [
            {
                "report_number": "260",
                "object_family": family,
                "inspection_complete": "true",
                "zero_discoveries_confirmed": "false"
                if family == "case_observation" and count
                else "true",
                "comment": "synthetic certification",
            }
            for family in sorted(BENCHMARK_OBJECT_TYPES)
        ],
    )


def discovered(
    role: str = "annotator-a", start_line: str = "1", end_page: str = "1"
) -> dict[str, bytes]:
    package = blank(role)
    package["discoveries.csv"] = form(
        "discoveries.csv",
        [
            {
                "discovery_id": "local-1",
                "report_number": "260",
                "object_family": "case_observation",
                "unit_type": "case_observation",
                "cardinality_index": "0",
                "start_page": "1",
                "start_line": start_line,
                "start_column": "1",
                "end_page": end_page,
                "end_line": start_line if end_page == "1" else "1",
                "end_column": "10",
                "section": "synthetic-section",
                "unresolved": "false",
                "note": "human-simulated source start",
            }
        ],
    )
    return package


def populated(
    role: str = "annotator-a", start_line: str = "1", end_page: str = "1"
) -> dict[str, bytes]:
    package = discovered(role, start_line, end_page)
    slots = annotation.empty_slots(package)
    assert slots
    for slot in slots:
        assert not slot["original_value"] and not slot["state"]
        slot.update(state="not_reported", evidence_id="e1")
    package["annotations.csv"] = form("annotations.csv", slots)
    package["evidence.csv"] = form(
        "evidence.csv",
        [
            {
                "evidence_id": "e1",
                "report_number": "260",
                "page": "1",
                "section": "synthetic-section",
                "granularity": "page_only",
                "rationale": "Synthetic whole-page absence inspection",
            }
        ],
    )
    complete(package, 1)
    return package


def test_empty_is_not_completed_zero_and_draft_never_locks() -> None:
    package = blank()
    with pytest.raises(ValueError, match="inspection"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT})
    assert not draft.complete
    complete(package)
    zero = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    assert zero.complete and not zero.submissions


def test_forged_completion_flag_cannot_publish(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-forgery"
    root.mkdir()
    draft = validate(blank(), {260: PartitionRole.PROTOCOL_PILOT})
    forged = draft.model_copy(update={"complete": True})
    with pytest.raises(ValueError):
        lock(root, forged, "fake", datetime.now(UTC), confirmed=True)
    assert list(root.iterdir()) == []


def test_supersession_requires_existing_parent(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-parent"
    root.mkdir()
    draft = validate(populated(), {260: PartitionRole.PROTOCOL_PILOT})
    with pytest.raises(ValueError, match="parent"):
        lock(root, draft, "new", datetime.now(UTC), confirmed=True, supersedes="f" * 64)


@pytest.mark.parametrize("state", ["source_ambiguous", "annotation_uncertain"])
def test_uncertainty_requires_comment(state: str) -> None:
    package = populated()
    values = annotation.rows(package, "annotations.csv")
    values[0]["state"] = state
    package["annotations.csv"] = form("annotations.csv", values)
    with pytest.raises(ValueError, match="comment"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT})


def test_blank_state_cannot_silently_discard_entered_value() -> None:
    package = populated()
    values = annotation.rows(package, "annotations.csv")
    values[0].update(state="", original_value="must not disappear")
    package["annotations.csv"] = form("annotations.csv", values)
    with pytest.raises(ValueError, match="state"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT})


def test_package_history_cannot_fork_without_supersession(tmp_path: Path) -> None:
    root = tmp_path / "m2-readiness-fork"
    root.mkdir()
    draft = validate(populated(), {260: PartitionRole.PROTOCOL_PILOT})
    lock(root, draft, "one", datetime.now(UTC), confirmed=True)
    with pytest.raises(ValueError, match="supersession"):
        lock(root, draft, "two", datetime.now(UTC), confirmed=True)


def test_declared_units_expand_blank_slots_and_require_all_before_lock() -> None:
    package = discovered()
    complete(package, 1)
    with pytest.raises(ValueError, match="slot"):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    validated = validate(populated(), {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    assert validated.complete and len(validated.submissions) == 1
    assert validated.submissions[0].partition_role == PartitionRole.PROTOCOL_PILOT
    assert validated.submissions[0].status.value == "draft"


def test_case_slots_do_not_invent_repeated_object_instances() -> None:
    fields = annotation.required_fields("case_observation")
    assert "case_month.case_description_original" in fields
    assert not any(f.startswith("violence_event.") for f in fields)
    assert "case_reported_indicator.value" in annotation.required_fields("case_reported_indicator")


def test_explicit_unanchorable_discovery_is_preserved_not_counted_as_zero() -> None:
    package = discovered()
    values = annotation.rows(package, "discoveries.csv")
    values[0].update(unresolved="true", note="Source start cannot be anchored; requires review")
    package["discoveries.csv"] = form("discoveries.csv", values)
    complete(package, 1)
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    assert len(draft.unresolved) == 1 and not draft.discoveries and not draft.submissions


@pytest.mark.parametrize(
    "field,value", [("unit_type", "invalid"), ("cardinality_index", "-8"), ("section", "")]
)
def test_unresolved_still_requires_valid_common_fields(field: str, value: str) -> None:
    package = discovered()
    values = annotation.rows(package, "discoveries.csv")
    values[0].update(unresolved="true", note="Unanchorable")
    values[0][field] = value
    package["discoveries.csv"] = form("discoveries.csv", values)
    complete(package, 1)
    with pytest.raises(ValueError):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


def test_coordinator_rejects_self_consistent_replaced_reference_package() -> None:
    original = verify_package(blank())
    pages = {1: b"Different source reading\n", 2: b"More replaced bytes\n"}
    replacement = build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    with pytest.raises(ValueError, match="coordinator"):
        validate(replacement, {260: PartitionRole.PROTOCOL_PILOT}, expected_package=original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_column", "999"),
        ("end_column", "0"),
        ("report_number", "261"),
        ("unresolved", "true"),
    ],
)
def test_bad_or_unresolved_positions_cannot_be_locked(field: str, value: str) -> None:
    package = discovered()
    rows = list(csv.DictReader(io.StringIO(package["discoveries.csv"].decode())))
    rows[0][field] = value
    package["discoveries.csv"] = form("discoveries.csv", rows)
    with pytest.raises(ValueError):
        validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)


def test_synthetic_lock_is_new_only_hash_verified_and_supersession_preserves_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "m2-readiness-locks"
    root.mkdir()
    package = populated()
    validated = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    with pytest.raises(ValueError, match="confirm"):
        lock(root, validated, "a-1", datetime.now(UTC), confirmed=False)
    first = lock(root, validated, "a-1", datetime.now(UTC), confirmed=True)
    with pytest.raises(ValueError, match="already published"):
        lock(root, validated, "a-1", datetime.now(UTC), confirmed=True)
    second = lock(root, validated, "a-2", datetime.now(UTC), confirmed=True, supersedes=first)
    assert annotation.read_locked(root, first).lock_id == "a-1"
    assert annotation.read_locked(root, second).supersedes == first
    (root / first / "payload.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        annotation.read_locked(root, first)


def test_comparison_requires_distinct_current_locks_and_preserves_boundaries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "m2-readiness-comparison"
    root.mkdir()
    a = validate(populated(), {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True)
    b = validate(
        populated("annotator-b", end_page="2"),
        {260: PartitionRole.PROTOCOL_PILOT},
        require_complete=True,
    )
    left = lock(root, a, "a-1", datetime.now(UTC), confirmed=True)
    right = lock(root, b, "b-1", datetime.now(UTC), confirmed=True)
    with pytest.raises(ValueError):
        annotation.compare_locked(root, left, left)
    result = annotation.compare_locked(root, left, right)
    assert len(result[260].boundary_disagreements) == 1
    lock(root, a, "a-2", datetime.now(UTC), confirmed=True, supersedes=left)
    with pytest.raises(ValueError, match="superseded"):
        annotation.compare_locked(root, left, right)


def test_independent_multiscenario_rehearsal_in_separate_roots(tmp_path: Path) -> None:
    """All names/values are invented; no source report or real human is represented."""
    roots = [tmp_path / f"m2-readiness-{role}" for role in ("a", "b")]
    for root in roots:
        root.mkdir()
    drafts: list[annotation.ValidatedDraft] = []
    for role, starts in (("annotator-a", [2, 3]), ("annotator-b", [1, 2, 4])):
        pages = {
            1: b"Same name first.\nSame name second.\nA unique.\nB unique.\n",
            2: b"Cross page continuation.\n",
        }
        package = build_package(
            "synthetic-run",
            cast(Literal["annotator-a", "annotator-b"], role),
            [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)],
        )
        discoveries: list[dict[str, str]] = []
        for index, line in enumerate(starts):
            discoveries.append(
                {
                    "discovery_id": f"local-{index}",
                    "report_number": "260",
                    "object_family": "case_observation",
                    "unit_type": "case_observation",
                    "cardinality_index": str(index),
                    "start_page": "1",
                    "start_line": str(line),
                    "start_column": "1",
                    "end_page": "2" if line == 2 and role == "annotator-b" else "1",
                    "end_line": "1" if line == 2 and role == "annotator-b" else str(line),
                    "end_column": "5",
                    "section": "synthetic-section",
                    "unresolved": "false",
                    "note": "simulated independent selection",
                }
            )
        package["discoveries.csv"] = form("discoveries.csv", discoveries)
        slots = annotation.empty_slots(package)
        for index, slot in enumerate(slots):
            state = ["explicit_zero", "not_reported", "source_ambiguous", "annotation_uncertain"][
                index % 4
            ]
            slot.update(state=state, evidence_id=f"e{index % 4}")
            if state == "explicit_zero":
                slot.update(value_type="number", original_value="0")
            if state in {"source_ambiguous", "annotation_uncertain"}:
                slot["comment"] = "Invented conflicting reading; preserve uncertainty"
        package["annotations.csv"] = form("annotations.csv", slots)
        anchors: list[dict[str, str]] = []
        for index, granularity in enumerate(("span", "table_cell", "bounding_box", "page_only")):
            anchors.append(
                {
                    "evidence_id": f"e{index}",
                    "report_number": "260",
                    "page": "1",
                    "section": "synthetic-section",
                    "granularity": granularity,
                    "start_line": "1",
                    "start_column": "1",
                    "end_line": "1",
                    "end_column": "5",
                    "table": "invented-table",
                    "row": "invented-row",
                    "column": "invented-column",
                    "x0": "1",
                    "y0": "1",
                    "x1": "2",
                    "y1": "2",
                    "rationale": "Invented whole-page absence inspection",
                }
            )
        package["evidence.csv"] = form("evidence.csv", anchors)
        complete(package, len(starts))
        drafts.append(validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=True))
    a = lock(roots[0], drafts[0], "a-first", datetime.now(UTC), confirmed=True)
    with pytest.raises(ValueError, match="two published"):
        annotation.compare_locked(roots[0], a, "f" * 64, right_root=roots[1])
    b = lock(roots[1], drafts[1], "b-first", datetime.now(UTC), confirmed=True)
    a2 = lock(roots[0], drafts[0], "a-correction", datetime.now(UTC), confirmed=True, supersedes=a)
    result = annotation.compare_locked(roots[0], a2, b, right_root=roots[1])[260]
    assert len(result.boundary_disagreements) == 1
    assert len(result.a_only) == 1 and len(result.b_only) == 2
    assert annotation.read_locked(roots[0], a).lock_id == "a-first"


def test_comparison_holds_both_publication_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    left_root, right_root = (tmp_path / "m2-readiness-left", tmp_path / "m2-readiness-right")
    left_root.mkdir()
    right_root.mkdir()
    a = validate(populated(), {260: PartitionRole.PROTOCOL_PILOT})
    b = validate(populated("annotator-b"), {260: PartitionRole.PROTOCOL_PILOT})
    left = lock(left_root, a, "a1", datetime.now(UTC), confirmed=True)
    right = lock(right_root, b, "b1", datetime.now(UTC), confirmed=True)
    real_history = annotation._history  # pyright: ignore[reportPrivateUsage]
    attempted = False

    def interleaved(root: Path) -> dict[str, annotation.SyntheticLock]:
        nonlocal attempted
        result = real_history(root)
        if root == left_root and not attempted:
            attempted = True
            with pytest.raises(DirectoryLeaseError):
                lock(left_root, a, "a2", datetime.now(UTC), confirmed=True, supersedes=left)
        return result

    monkeypatch.setattr(annotation, "_history", interleaved)
    annotation.compare_locked(left_root, left, right, right_root=right_root)
    assert attempted
