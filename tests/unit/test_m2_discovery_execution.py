"""Synthetic compatibility proof only: no benchmark report answers or human submissions."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from peru_conflicts.benchmark.metrics import multiset_object_metrics
from peru_conflicts.benchmark.models import (
    AnnotationObjectInstance,
    AnnotationState,
    AnnotationUnit,
    AnnotationUnitType,
    AnnotatorSubmission,
    EvidenceAnchor,
    EvidenceGranularity,
    FieldAnnotation,
    PartitionRole,
    SubmissionStatus,
    validate_independent_submissions,
)
from peru_conflicts.execution.discovery import (
    DiscoveredObject,
    DiscoveryWindow,
    compare_discoveries,
    position_from_reference,
)
from peru_conflicts.models.common import SourceSpan

REFERENCE = b"SYNTHETIC ONLY\nBlock same label\nBlock same label\nEnd\n"


def window() -> DiscoveryWindow:
    return DiscoveryWindow(
        report_number=999,
        source_sha256="a" * 64,
        partition_role=PartitionRole.PROTOCOL_PILOT,
        page_count=3,
    )


def discovery(
    annotator: str, offset: int = 15, *, end_page: int = 1, index: int = 0
) -> DiscoveredObject:
    return DiscoveredObject(
        window=window(),
        annotator_id=annotator,
        domain_object_type="case_observation",
        unit_type=AnnotationUnitType.CASE_OBSERVATION,
        local_index=index,
        start=position_from_reference(page=1, offset=offset, reference=REFERENCE),
        end=position_from_reference(page=end_page, offset=49, reference=REFERENCE),
        section="synthetic-section",
    )


@pytest.mark.parametrize(
    "field",
    [
        "case_name",
        "case_code",
        "case_count",
        "actors",
        "demands",
        "events",
        "unit_id",
        "parser_result",
        "source_reading",
        "pages",
        "section",
        "window_id",
    ],
)
def test_blank_window_rejects_answer_and_boundary_fields(field: str) -> None:
    payload = window().model_dump()
    payload[field] = "forbidden"
    with pytest.raises(ValidationError):
        DiscoveryWindow.model_validate(payload)


def test_shared_window_has_only_whole_report_context() -> None:
    a = window()
    b = DiscoveryWindow.model_validate_json(a.model_dump_json())
    assert a == b and a.window_id == b.window_id
    assert a.pages == (1, 2, 3)
    assert set(a.model_dump()) == {
        "execution_policy_version",
        "report_number",
        "source_sha256",
        "partition_role",
        "page_count",
    }
    assert "discovery_window" not in {member.value for member in AnnotationUnitType}


def test_same_start_matches_without_names_codes_or_local_indexes() -> None:
    a, b = discovery("synthetic-a", index=0), discovery("synthetic-b", index=4)
    assert a.detection_key == b.detection_key
    assert a.to_annotation_unit() == b.to_annotation_unit()
    assert a.detection_key != a.window.window_id
    other = discovery("synthetic-b", 32)
    assert other.detection_key != a.detection_key


def test_cardinality_shift_and_unmatched_discovery_survive() -> None:
    a = discovery("synthetic-a", 32, index=0)
    b0, b1 = discovery("synthetic-b", 15, index=0), discovery("synthetic-b", 32, index=1)
    result = compare_discoveries(window(), "synthetic-a", "synthetic-b", (a,), (b0, b1))
    assert result.matched == ((a, b1),)
    assert result.b_only == (b0,) and result.a_only == ()
    # Ordinal matching would incorrectly pair the missed earlier block with the later one.
    assert a.local_index == b0.local_index and a.detection_key != b0.detection_key


def test_shared_window_as_case_key_falsely_scores_equal_counts() -> None:
    a, b = discovery("synthetic-a", 15), discovery("synthetic-b", 32)
    wrong = multiset_object_metrics(
        [{"unit_id": a.window.window_id}],
        [{"unit_id": b.window.window_id}],
        match_fields=("unit_id",),
    )
    assert wrong.true_positive == 1  # Demonstration of the forbidden projection, not its use.
    result = compare_discoveries(window(), "synthetic-a", "synthetic-b", (a,), (b,))
    assert result.matched == () and result.a_only == (a,) and result.b_only == (b,)


def test_boundary_disagreement_is_not_forced_into_same_unit() -> None:
    a, b = discovery("synthetic-a"), discovery("synthetic-b", end_page=2)
    assert a.detection_key == b.detection_key
    assert a.to_annotation_unit().pages != b.to_annotation_unit().pages
    assert a.to_annotation_unit().unit_id != b.to_annotation_unit().unit_id
    result = compare_discoveries(window(), "synthetic-a", "synthetic-b", (a,), (b,))
    assert result.boundary_disagreements == ((a, b),) and result.matched == ()


def test_same_page_different_end_still_preserves_boundary_disagreement() -> None:
    a = discovery("synthetic-a")
    payload = discovery("synthetic-b").model_dump()
    payload["end"] = position_from_reference(page=1, offset=48, reference=REFERENCE)
    b = DiscoveredObject.model_validate(payload)
    assert a.detection_key == b.detection_key
    assert a.to_annotation_unit().unit_id != b.to_annotation_unit().unit_id
    assert compare_discoveries(
        window(), "synthetic-a", "synthetic-b", (a,), (b,)
    ).boundary_disagreements


def synthetic_submission(d: DiscoveredObject) -> AnnotatorSubmission:
    unit = d.to_annotation_unit()
    anchor = EvidenceAnchor(
        report_id=unit.report_id,
        report_number=unit.report_number,
        source_sha256=unit.source_sha256,
        page=1,
        section=d.section,
        granularity=EvidenceGranularity.SPAN,
        source_span=SourceSpan(start=15, end=20),
    )
    return AnnotatorSubmission(
        submission_id="synthetic-" + d.annotator_id,
        annotator_id=d.annotator_id,
        unit_id=unit.unit_id,
        partition_role=d.window.partition_role,
        status=SubmissionStatus.LOCKED,
        locked_at=datetime(2020, 1, 1, tzinfo=UTC),
        object_inventory=(
            AnnotationObjectInstance(
                unit_id=unit.unit_id,
                domain_object_type="case_observation",
                cardinality_index=0,
                required_field_names=("synthetic_field",),
            ),
        ),
        annotations=(
            FieldAnnotation(
                annotation_id="synthetic-value-" + d.annotator_id,
                unit_id=unit.unit_id,
                annotator_id=d.annotator_id,
                domain_object_type="case_observation",
                field_name="synthetic_field",
                state=AnnotationState.OBSERVED,
                raw_value_json='"SYNTHETIC"',
                evidence_anchors=(anchor,),
            ),
        ),
    )


def test_existing_frozen_units_and_current_independent_validator() -> None:
    a, b = discovery("synthetic-a"), discovery("synthetic-b")
    assert (
        AnnotationUnit.model_validate_json(a.to_annotation_unit().model_dump_json())
        == a.to_annotation_unit()
    )
    sa, sb = synthetic_submission(a), synthetic_submission(b)
    assert validate_independent_submissions(sa, sb, submission_history=(sa, sb)) == ()
    different = synthetic_submission(discovery("synthetic-b", end_page=2))
    with pytest.raises(ValueError, match="same annotation unit"):
        validate_independent_submissions(sa, different, submission_history=(sa, different))


@pytest.mark.parametrize(
    "family",
    ["protest_event", "violence_event", "dp_action", "alert", "agreement", "mediation_observation"],
)
def test_repeated_source_only_or_annex_objects_remain_independently_discovered(family: str) -> None:
    payload = discovery("synthetic-a").model_dump()
    payload.update(domain_object_type=family, unit_type=AnnotationUnitType.SOURCE_ONLY_OBJECT)
    item = DiscoveredObject.model_validate(payload)
    assert item.to_annotation_unit().unit_type is AnnotationUnitType.SOURCE_ONLY_OBJECT
    assert item.detection_key != discovery("synthetic-a").detection_key


def test_ambiguous_or_malformed_discovery_is_not_silently_collapsed() -> None:
    a = discovery("synthetic-a")
    with pytest.raises(ValueError, match="duplicate"):
        compare_discoveries(window(), "synthetic-a", "synthetic-b", (a, a), ())
    with pytest.raises(ValueError, match="annotator"):
        compare_discoveries(window(), "synthetic-a", "synthetic-a", (), ())
    with pytest.raises(ValueError, match="assignment"):
        compare_discoveries(window(), "synthetic-a", "synthetic-b", (), (a,))
    empty = compare_discoveries(window(), "synthetic-a", "synthetic-b", (), ())
    assert empty.matched == empty.a_only == empty.b_only == ()


@pytest.mark.parametrize(
    "reference,offset", [(b"a\r\nb", 0), (b"a\fb", 0), (b"\xff", 0), (b"ab", 3)]
)
def test_reference_coordinates_fail_closed(reference: bytes, offset: int) -> None:
    with pytest.raises(ValueError):
        position_from_reference(page=1, offset=offset, reference=reference)


def test_unicode_location_and_reference_drift_are_explicit() -> None:
    ref = "a\U0001f642e\u0301\n".encode()
    p = position_from_reference(page=1, offset=2, reference=ref)
    assert p.codepoint_offset == 2  # Not UTF-8 byte or UTF-16 code-unit index.
    assert p.reference_sha256 == hashlib.sha256(ref).hexdigest()
    assert p != position_from_reference(page=1, offset=2, reference="a\U0001f642é\n".encode())


def test_reference_drift_is_custody_failure_not_discovery_disagreement() -> None:
    a = discovery("synthetic-a")
    payload = discovery("synthetic-b").model_dump()
    changed = REFERENCE.replace(b"same", b"else")
    payload["start"] = position_from_reference(page=1, offset=15, reference=changed)
    payload["end"] = position_from_reference(page=1, offset=49, reference=changed)
    b = DiscoveredObject.model_validate(payload)
    with pytest.raises(ValueError, match="reference custody"):
        compare_discoveries(window(), "synthetic-a", "synthetic-b", (a,), (b,))


def test_frozen_authority_and_policy_status() -> None:
    root = Path(__file__).parents[2]
    expected = {
        "schemas/benchmark/v0.1.0": (
            19,
            "23a5ee953541c93b9e51898872901f8b9432588f8c9ea03758ea85a5a1ff28fa",
        ),
        "schemas/v0.3.0": (26, "cd5bdea78e6314242685ea89d43850f8ff42e639ba74606aba3d929b2e81444d"),
    }
    for folder, (count, digest) in expected.items():
        directory = root / folder
        files = sorted(p for p in directory.rglob("*") if p.is_file())
        rows = [
            p.relative_to(directory).as_posix() + ":" + hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        ]
        assert len(files) == count
        assert hashlib.sha256("\n".join(rows).encode()).hexdigest() == digest
    owner = (root / "config/benchmark/m2_01_owner_approval_v1.yaml").read_bytes()
    assert (
        hashlib.sha256(owner).hexdigest()
        == "e338944f504c4bcce1c8312758121330b9487e4f996bf66fd8623c1eeae29ce5"
    )
    gate = yaml.safe_load((root / "config/benchmark/m3_acceptance_gates_v1.yaml").read_bytes())
    assert gate["policy_status"] == "owner_review_draft" and gate["owner_approved"] is False
    assert gate["object_metric_thresholds"] == []
    policy = yaml.safe_load((root / "config/benchmark/m2_02_execution_policy_v1.yaml").read_bytes())
    assert policy["owner_approved"] is False and policy["annotation_started"] is False
    assert policy["human_gold_created"] is False
    assert policy["status"] == "owner_review_draft"
