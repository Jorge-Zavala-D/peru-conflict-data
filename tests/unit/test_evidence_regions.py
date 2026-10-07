"""Invented region fixtures; no report text or machine findings."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from test_ai_pi_batch import envelope as original_envelope

from peru_conflicts.benchmark.models import EvidenceAnchor, EvidenceGranularity
from peru_conflicts.execution.ai_pi import SourceUnit
from peru_conflicts.execution.ai_pi_batch import (
    SOURCE_SHA256,
    BatchEnvelope,
    MachineCandidate,
    PartialFieldCandidate,
    validate_machine_candidate,
)
from peru_conflicts.execution.references import sha256
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import SourceBBox


@pytest.fixture(name="envelope")
def region_envelope(tmp_path: Path) -> BatchEnvelope:
    factory = cast(Callable[[Path], BatchEnvelope], original_envelope.__wrapped__)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    return factory(tmp_path)


def inputs(envelope: BatchEnvelope, quote: str = "Invented claim 17") -> tuple[Any, ...]:
    unit = SourceUnit(
        unit_id="invented-unit",
        report_id="report-264",
        report_number=264,
        source_sha256=SOURCE_SHA256,
        pages=(2,),
        sections=("invented",),
    )
    anchor = EvidenceAnchor(
        report_id=unit.report_id,
        report_number=264,
        source_sha256=SOURCE_SHA256,
        page=2,
        section="invented",
        granularity=EvidenceGranularity.BOUNDING_BOX,
        source_bbox=SourceBBox(x0=0, y0=0, x1=80, y1=20),
        source_text=quote,
    )
    words = [
        {"text": "Invented", "bbox": [1, 1, 20, 10], "span": [0, 8]},
        {"text": "outside", "bbox": [90, 1, 99, 10], "span": [9, 16]},
        {"text": "claim", "bbox": [21, 1, 40, 10], "span": [17, 22]},
        {"text": "17", "bbox": [41, 1, 50, 10], "span": [23, 25]},
    ]
    reference = b"Invented outside claim 17\n"
    xml = (
        b'<doc><page width="100" height="100"><line>'
        b'<word xMin="1" yMin="1" xMax="20" yMax="10">Invented</word>'
        b'<word xMin="90" yMin="1" xMax="99" yMax="10">outside</word>'
        b'<word xMin="21" yMin="1" xMax="40" yMax="10">claim</word>'
        b'<word xMin="41" yMin="1" xMax="50" yMax="10">17</word>'
        b"</line></page></doc>"
    )
    layout = canonical_json_bytes(
        {
            "physical_page": 2,
            "width": 100,
            "height": 100,
            "text": "Invented outside claim 17",
            "words": words,
            "layout_lines": [{"words": words}],
            "representation_status": "native_text_present",
            "table_structure": "invented",
            "reference_sha256": sha256(reference),
            "span_reference": "invented retained order",
        }
    )
    pin = {
        "report_id": unit.report_id,
        "report_number": 264,
        "source_sha256": SOURCE_SHA256,
        "physical_page": 2,
        "unit_id": unit.unit_id,
        "reference_sha256": sha256(reference),
        "layout_sha256": sha256(layout),
        "bbox_xml_sha256": sha256(xml),
        "engine": {
            "path": str(envelope.tool.native_tools[1].path),
            "sha256": envelope.tool.native_tools[1].sha256,
            "version": envelope.tool.native_tools[1].version,
        },
        "extraction_options": ["-bbox-layout", "-enc", "UTF-8", "-eol", "unix"],
        "coordinate_policy": "top_left_pdf_points_unrotated_media_crop_zero_v1",
        "media_box": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
        "crop_box": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
        "rotation": 0,
        "region_policy": "fully_contained_words_retained_order_v1",
    }
    assert anchor.source_bbox is not None
    method = {
        "method_id": "native_bbox_words_v1",
        "unit_id": unit.unit_id,
        "anchor_sha256": sha256(canonical_json_bytes(anchor.model_dump(mode="json"))),
        "raw_response_sha256": "a" * 64,
        "original_bbox": anchor.source_bbox.model_dump(),
        "layout": pin,
        "whitespace_policy": "ascii_space_lf_v1",
    }
    candidate = MachineCandidate(
        candidate_id="invented-candidate",
        batch_id=envelope.batch_id,
        envelope_sha256=envelope.fingerprint,
        raw_response_sha256="a" * 64,
        partial_fields=(
            PartialFieldCandidate(
                unit_id=unit.unit_id,
                domain_object_type="report",
                field_name="report.notes",
                state=None,
                evidence_anchors=(anchor,),
            ),
        ),
        processed_unit_ids=(unit.unit_id,),
    )
    return unit, anchor, reference, layout, xml, method, candidate


def qualified(envelope: BatchEnvelope, quote: str = "Invented claim 17") -> tuple[Any, ...]:
    unit, anchor, reference, layout, xml, method, candidate = inputs(envelope, quote)
    candidate = MachineCandidate.model_validate_json(
        json.dumps(candidate.model_dump(mode="json") | {"region_evidence_methods": [method]})
    )
    from peru_conflicts.execution.evidence_regions import RegionResource

    return candidate, unit, anchor, reference, {sha256(layout): RegionResource(layout, xml)}


def test_explicit_region_route_matches_when_strict_route_rejects(envelope: BatchEnvelope) -> None:
    unit, _anchor, reference, _layout, _xml, _method, strict = inputs(envelope)
    with pytest.raises(ValueError, match="quote/reference mismatch"):
        validate_machine_candidate(strict, envelope, (unit,), {(unit.unit_id, 2): reference})
    candidate, unit, _anchor, reference, resources = qualified(envelope)
    issues = validate_machine_candidate(
        candidate, envelope, (unit,), {(unit.unit_id, 2): reference}, region_resources=resources
    )
    assert any(issue.startswith("region_match:raw_exact:") for issue in issues)
    assert candidate.partial_fields[0].evidence_anchors[0].source_text == "Invented claim 17"


def test_only_declared_ascii_whitespace_can_match(envelope: BatchEnvelope) -> None:
    candidate, unit, _anchor, reference, resources = qualified(envelope, "Invented\nclaim 17")
    issues = validate_machine_candidate(
        candidate, envelope, (unit,), {(unit.unit_id, 2): reference}, region_resources=resources
    )
    assert any(issue.startswith("region_match:qualified_whitespace:") for issue in issues)
    assert candidate.partial_fields[0].evidence_anchors[0].source_text == "Invented\nclaim 17"


@pytest.mark.parametrize(
    "quote",
    [
        "Invented claim 18",
        "invented claim 17",
        "Invented claim, 17",
        "Invénted claim 17",
        "Inventedclaim 17",
        "Invented\u00a0claim 17",
        "Invented\tclaim 17",
        "Invented\rclaim 17",
    ],
)
def test_substantive_or_unsupported_transforms_refused(envelope: BatchEnvelope, quote: str) -> None:
    candidate, unit, _anchor, reference, resources = qualified(envelope, quote)
    with pytest.raises(ValueError):
        validate_machine_candidate(
            candidate, envelope, (unit,), {(unit.unit_id, 2): reference}, region_resources=resources
        )


@pytest.mark.parametrize(
    "change",
    [
        {"unit_id": "wrong-unit"},
        {"raw_response_sha256": "b" * 64},
        {"anchor_sha256": "b" * 64},
        {"original_bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100}},
    ],
)
def test_declaration_cannot_move_or_reuse_anchor(
    envelope: BatchEnvelope, change: dict[str, Any]
) -> None:
    candidate, unit, _anchor, reference, resources = qualified(envelope)
    payload = candidate.model_dump(mode="json")
    payload["region_evidence_methods"][0].update(change)
    with pytest.raises(ValueError):
        changed = MachineCandidate.model_validate_json(json.dumps(payload))
        validate_machine_candidate(
            changed, envelope, (unit,), {(unit.unit_id, 2): reference}, region_resources=resources
        )


@pytest.mark.parametrize(
    "change",
    [
        {"physical_page": 3},
        {"source_sha256": "b" * 64},
        {"report_id": "wrong-report"},
        {"reference_sha256": "b" * 64},
        {"layout_sha256": "b" * 64},
        {"bbox_xml_sha256": "b" * 64},
        {"rotation": 90},
        {"crop_box": {"x0": 1, "y0": 0, "x1": 100, "y1": 100}},
        {"coordinate_policy": "unsupported"},
        {"extraction_options": ["-raw"]},
    ],
)
def test_wrong_source_geometry_or_representation_refused(
    envelope: BatchEnvelope, change: dict[str, Any]
) -> None:
    candidate, unit, _anchor, reference, resources = qualified(envelope)
    payload = candidate.model_dump(mode="json")
    payload["region_evidence_methods"][0]["layout"].update(change)
    with pytest.raises(ValueError):
        changed = MachineCandidate.model_validate_json(json.dumps(payload))
        validate_machine_candidate(
            changed, envelope, (unit,), {(unit.unit_id, 2): reference}, region_resources=resources
        )


def test_missing_or_duplicate_region_declaration_is_not_fallback(envelope: BatchEnvelope) -> None:
    candidate, unit, _anchor, reference, _resources = qualified(envelope)
    with pytest.raises(ValueError):
        validate_machine_candidate(candidate, envelope, (unit,), {(unit.unit_id, 2): reference})
    payload = candidate.model_dump(mode="json")
    payload["region_evidence_methods"] *= 2
    with pytest.raises(ValueError):
        MachineCandidate.model_validate_json(json.dumps(payload))


def test_numeric_group_whitespace_is_not_collapsed() -> None:
    from peru_conflicts.execution.evidence_regions import qualified_whitespace

    with pytest.raises(ValueError, match="numeric"):
        qualified_whitespace("12\n345")
    assert qualified_whitespace("Invented\nclaim") == "Invented claim"


def test_region_repeated_quote_and_out_of_bounds_stay_incomplete(envelope: BatchEnvelope) -> None:
    from peru_conflicts.execution.evidence_regions import RegionResource

    candidate, unit, anchor, reference, resources = qualified(envelope)
    payload = candidate.model_dump(mode="json")
    pin = payload["region_evidence_methods"][0]["layout"]
    original = resources[pin["layout_sha256"]]
    layout = json.loads(original.layout_json)
    layout["words"].append({"text": "Invented claim 17", "bbox": [1, 11, 70, 19], "span": [26, 43]})
    layout["layout_lines"][0]["words"].append(layout["words"][-1])
    layout["text"] += " Invented claim 17"
    raw = canonical_json_bytes(layout)
    duplicate_xml = original.bbox_xml.replace(
        b"</line>", b'<word xMin="1" yMin="11" xMax="70" yMax="19">Invented claim 17</word></line>'
    )
    pin["layout_sha256"] = sha256(raw)
    pin["bbox_xml_sha256"] = sha256(duplicate_xml)
    duplicate = MachineCandidate.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError, match="ambiguous"):
        validate_machine_candidate(
            duplicate,
            envelope,
            (unit,),
            {(unit.unit_id, 2): reference},
            region_resources={sha256(raw): RegionResource(raw, duplicate_xml)},
        )
    for bad in (SourceBBox(x0=-1, y0=0, x1=80, y1=20), SourceBBox(x0=0, y0=0, x1=101, y1=20)):
        changed_anchor = anchor.model_copy(update={"source_bbox": bad})
        data = candidate.model_dump(mode="json")
        data["partial_fields"][0]["evidence_anchors"][0] = changed_anchor.model_dump(mode="json")
        data["region_evidence_methods"][0].update(
            {
                "original_bbox": bad.model_dump(),
                "anchor_sha256": sha256(
                    canonical_json_bytes(changed_anchor.model_dump(mode="json"))
                ),
            }
        )
        changed = MachineCandidate.model_validate_json(json.dumps(data))
        with pytest.raises(ValueError, match="outside page"):
            validate_machine_candidate(
                changed,
                envelope,
                (unit,),
                {(unit.unit_id, 2): reference},
                region_resources=resources,
            )


def test_followup_preserves_rejected_payload_and_does_not_replace_initial(
    envelope: BatchEnvelope,
) -> None:
    from peru_conflicts.execution.ai_pi_batch_runtime import finalize_initial_pass

    envelope.output_root.mkdir(parents=True)
    initial = envelope.output_root / "independent_discovery/initial_discovery.json"
    initial.parent.mkdir()
    initial.write_bytes(b"invented immutable original")
    unit, _anchor, reference, _layout, _xml, _method, strict = inputs(envelope)
    raw = canonical_json_bytes(strict.model_dump(mode="json"))
    result = finalize_initial_pass(
        envelope,
        "discovery",
        [("invented", raw)],
        units=(unit,),
        reference_pages={(unit.unit_id, 2): reference},
        output_prefix="normalization_followups/b-region-v1-invented",
    )
    assert result["status"] == "incomplete"
    assert cast(list[dict[str, Any]], result["rejected_responses"])[0]["original_payload"][
        "partial_fields"
    ]
    assert initial.read_bytes() == b"invented immutable original"
    assert cast(dict[str, str], result["coverage"])[unit.unit_id] == "unprocessed"
    with pytest.raises(ValueError, match="exists"):
        finalize_initial_pass(
            envelope,
            "discovery",
            [("invented", raw)],
            units=(unit,),
            reference_pages={(unit.unit_id, 2): reference},
            output_prefix="normalization_followups/b-region-v1-invented",
        )


def test_layout_cannot_contradict_its_pinned_native_xml(envelope: BatchEnvelope) -> None:
    from peru_conflicts.execution.evidence_regions import RegionResource

    candidate, unit, _anchor, reference, resources = qualified(envelope)
    payload = candidate.model_dump(mode="json")
    pin = payload["region_evidence_methods"][0]["layout"]
    resource = resources[pin["layout_sha256"]]
    changed_xml = resource.bbox_xml.replace(b">17<", b">18<")
    pin["bbox_xml_sha256"] = sha256(changed_xml)
    changed = MachineCandidate.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError, match="conversion"):
        validate_machine_candidate(
            changed,
            envelope,
            (unit,),
            {(unit.unit_id, 2): reference},
            region_resources={
                pin["layout_sha256"]: RegionResource(resource.layout_json, changed_xml)
            },
        )


@pytest.mark.parametrize(
    ("number", "quote", "accepted"),
    [
        ("17,5", "Invented claim 17", False),
        ("17.000", "Invented claim 17", False),
        ("17,5", "5", False),
        ("17.000", "000", False),
        ("17,5", "Invented claim 17,5", True),
        ("17.000", "Invented claim 17.000", True),
        ("17", "Invented claim 17", True),
    ],
)
def test_region_cannot_truncate_numeric_token(
    envelope: BatchEnvelope, number: str, quote: str, accepted: bool
) -> None:
    from peru_conflicts.execution.ai_pi_batch_runtime import parse_layout_xml
    from peru_conflicts.execution.evidence_regions import RegionResource

    candidate, unit, _anchor, _reference, resources = qualified(envelope, quote)
    payload = candidate.model_dump(mode="json")
    pin = payload["region_evidence_methods"][0]["layout"]
    original = resources[pin["layout_sha256"]]
    xml = original.bbox_xml.replace(b">17<", f">{number}<".encode())
    reference = f"Invented outside claim {number}\n".encode()
    layout = json.loads(original.layout_json)
    layout.update(parse_layout_xml(xml.decode(), physical_page=2))
    layout["reference_sha256"] = sha256(reference)
    raw = canonical_json_bytes(layout)
    pin.update(
        reference_sha256=sha256(reference), layout_sha256=sha256(raw), bbox_xml_sha256=sha256(xml)
    )
    changed = MachineCandidate.model_validate_json(json.dumps(payload))
    bound_resources = {sha256(raw): RegionResource(raw, xml)}
    if accepted:
        issues = validate_machine_candidate(
            changed,
            envelope,
            (unit,),
            {(unit.unit_id, 2): reference},
            region_resources=bound_resources,
        )
        assert any(issue.startswith("region_match:raw_exact:") for issue in issues)
    else:
        with pytest.raises(ValueError, match="unsupported or ambiguous"):
            validate_machine_candidate(
                changed,
                envelope,
                (unit,),
                {(unit.unit_id, 2): reference},
                region_resources=bound_resources,
            )


@pytest.mark.parametrize("write_fails", [False, True])
def test_followup_admission_requires_successful_normalized_persistence(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch, write_fails: bool
) -> None:
    from peru_conflicts.execution import ai_pi_batch_runtime as runtime
    from peru_conflicts.execution.evidence_regions import RegionEvidenceMethod

    envelope.output_root.mkdir(parents=True)
    candidate, unit, _anchor, reference, resources = qualified(envelope)
    payload = candidate.model_dump(mode="json")
    method = payload.pop("region_evidence_methods")[0]
    raw = canonical_json_bytes(payload)
    method["raw_response_sha256"] = sha256(raw)
    declaration = RegionEvidenceMethod.model_validate_json(json.dumps(method))
    actual_write = runtime.write_json

    def fail_normalized_write(bound: BatchEnvelope, name: str, value: object) -> Path:
        if "normalized_responses/" in name:
            raise OSError("invented normalized write failure")
        return actual_write(bound, name, value)

    if write_fails:
        monkeypatch.setattr(runtime, "write_json", fail_normalized_write)
    result = runtime.finalize_initial_pass(
        envelope,
        "discovery",
        [("invented", raw)],
        units=(unit,),
        reference_pages={(unit.unit_id, 2): reference},
        output_prefix="normalization_followups/b-region-v1-persistence",
        region_methods={"invented": (declaration,)},
        region_resources=resources,
    )
    matches = cast(list[dict[str, Any]], result["region_evidence_matches"])
    coverage = cast(dict[str, str], result["coverage"])
    if write_fails:
        assert result["candidates"] == []
        assert result["issues"] == []
        assert result["status"] == "incomplete"
        assert coverage[unit.unit_id] == "unprocessed"
        rejected = cast(list[dict[str, Any]], result["rejected_responses"])[0]
        assert rejected["original_payload"]["partial_fields"]
        assert "OSError" in rejected["new_followup_traceback"]
    else:
        admitted = cast(list[dict[str, Any]], result["candidates"])[0]
        assert (
            admitted["partial_fields"][0]["evidence_anchors"][0]["source_text"]
            == "Invented claim 17"
        )
        assert coverage[unit.unit_id] == "machine_candidate_present"
        assert result["rejected_responses"] == []
    assert matches[0]["normalization_status"] == ("rejected" if write_fails else "admitted")


def test_raw_copy_readback_failure_stops_before_typed_normalization(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.execution import ai_pi_batch as batch
    from peru_conflicts.execution.ai_pi_batch_runtime import finalize_initial_pass

    envelope.output_root.mkdir(parents=True)
    actual_write = batch._write_new  # pyright: ignore[reportPrivateUsage]

    def corrupted_copy(target: Path, data: bytes) -> Path:
        return actual_write(target, b"invented incorrect bytes")

    monkeypatch.setattr(batch, "_write_new", corrupted_copy)
    prefix = "normalization_followups/b-region-v1-rb"
    with pytest.raises(ValueError, match="readback"):
        finalize_initial_pass(
            envelope,
            "discovery",
            [("1", '{"invented":"árbol"}'.encode())],
            units=(),
            reference_pages={},
            output_prefix=prefix,
        )
    destination = envelope.output_root / prefix
    assert (
        destination / "raw_responses/discovery-1.txt"
    ).read_bytes() == b"invented incorrect bytes"
    assert not (destination / "normalized_responses").exists()
    assert not (destination / "independent_discovery/initial_discovery.json").exists()


def test_partial_raw_write_is_preserved_without_completion_record(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.execution import ai_pi_batch as batch
    from peru_conflicts.execution.ai_pi_batch_runtime import finalize_initial_pass

    envelope.output_root.mkdir(parents=True)
    actual_write = batch._write_new  # pyright: ignore[reportPrivateUsage]

    def interrupted_copy(target: Path, data: bytes) -> Path:
        actual_write(target, data[:7])
        raise OSError("invented interruption after partial bytes")

    monkeypatch.setattr(batch, "_write_new", interrupted_copy)
    prefix = "normalization_followups/b-region-v1-part"
    raw = b"Invented Unicode and CRLF preservation\r\n"
    with pytest.raises(OSError, match="interruption"):
        finalize_initial_pass(
            envelope,
            "discovery",
            [("1", raw)],
            units=(),
            reference_pages={},
            output_prefix=prefix,
        )
    destination = envelope.output_root / prefix
    partial = destination / "raw_responses/discovery-1.txt"
    assert partial.read_bytes() == raw[:7]
    assert not (destination / "independent_discovery/initial_discovery.json").exists()
    monkeypatch.setattr(batch, "_write_new", actual_write)
    with pytest.raises(FileExistsError):
        batch.freeze_raw_response(envelope, "discovery-1", raw, output_prefix=prefix)
    assert partial.read_bytes() == raw[:7]
