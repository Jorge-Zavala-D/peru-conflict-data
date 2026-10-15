"""Synthetic checks for the specifically authorized report-264 first batch."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from peru_conflicts.benchmark.models import AnnotationState, EvidenceAnchor, EvidenceGranularity
from peru_conflicts.execution.ai_pi import PIDecision, SourceUnit
from peru_conflicts.execution.ai_pi_batch import (
    ALLOWED_PAGES,
    SOURCE_SHA256,
    BatchEnvelope,
    BatchUsage,
    MachineCandidate,
    NativeToolIdentity,
    PartialFieldCandidate,
    ReportContextAssociation,
    ResourceIdentity,
    SourceFirstPacket,
    ToolIdentity,
    coverage_state,
    freeze_initial_candidate,
    freeze_raw_response,
    freeze_then_normalize,
    make_worker_packet,
    prepare_output_root,
    require_budget,
    require_continuation_pages,
    schema_bytes,
    source_first_input,
    validate_machine_candidate,
    validate_report_context,
    verify_envelope,
    verify_source_identity,
    write_json,
)
from peru_conflicts.models.common import SourceSpan


@pytest.fixture
def envelope(tmp_path: Path) -> BatchEnvelope:
    data_root = tmp_path / "data"
    data_root.mkdir()
    tool = tmp_path / "tool.py"
    tool.write_bytes(b"synthetic tool")
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"synthetic interpreter")
    resource = tmp_path / "prompt.txt"
    resource.write_bytes(b"synthetic neutral prompt")
    return BatchEnvelope(
        batch_id="report-264-batch-001",
        owner_instruction_id="owner-test-instruction",
        report_id="report-264",
        source_path=data_root / "01_raw" / "report-264.pdf",
        data_root=data_root,
        output_root=data_root
        / "06_validation"
        / "ai_pi_reconstruction"
        / "development"
        / "report-264"
        / "batch-001",
        tool=ToolIdentity(
            tool_id="synthetic-offline-test",
            tool_path=tool,
            tool_sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
            interpreter_path=interpreter,
            interpreter_sha256=hashlib.sha256(interpreter.read_bytes()).hexdigest(),
            configuration_sha256="a" * 64,
            native_tools=tuple(
                NativeToolIdentity(
                    tool_name=name,
                    path=tool,
                    sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
                    version="synthetic",
                )
                for name in ("pdfinfo", "pdftotext", "pdftoppm")
            ),
        ),
        resource=ResourceIdentity(
            resource_id="neutral-prompt-v1",
            path=resource,
            sha256=hashlib.sha256(resource.read_bytes()).hexdigest(),
            implementation_git_commit="a" * 40,
            implementation_git_tree="b" * 40,
            repository_root=tmp_path / "repository",
            packet_configuration_sha256="c" * 64,
            output_root=data_root
            / "06_validation"
            / "ai_pi_reconstruction"
            / "development"
            / "report-264"
            / "batch-001",
        ),
    )


def unit(pages: tuple[int, ...] = (2,), unit_id: str = "case-unit") -> SourceUnit:
    return SourceUnit(
        unit_id=unit_id,
        report_id="report-264",
        report_number=264,
        source_sha256=SOURCE_SHA256,
        pages=pages,
        sections=("synthetic-section",),
    )


def association(field: str = "report.report_number") -> dict[str, object]:
    return {
        "association_id": "context-1",
        "field_name": field,
        "raw_value_json": "264",
        "context_source_unit_id": "cover-unit",
        "target_unit_id": "case-unit",
        "target_report_id": "report-264",
        "report_id": "report-264",
        "report_number": 264,
        "source_sha256": SOURCE_SHA256,
        "evidence": EvidenceAnchor(
            report_id="report-264",
            report_number=264,
            source_sha256=SOURCE_SHA256,
            page=1,
            section="synthetic-section",
            granularity=EvidenceGranularity.SPAN,
            source_span=SourceSpan(start=0, end=3),
            source_text="264",
        ).model_dump(mode="json"),
    }


def test_exact_source_size_pages_and_scope(envelope: BatchEnvelope) -> None:
    verify_source_identity(envelope, sha256=SOURCE_SHA256, size_bytes=4539029, page_count=104)
    assert len(ALLOWED_PAGES) == 30
    for change in (
        {"source_sha256": "b" * 64},
        {"source_size_bytes": 1},
        {"source_page_count": 103},
        {"physical_pages": (1, 2)},
        {"max_pages": 31},
        {"max_packets": 9},
        {"max_tasks": 21},
        {"max_wall_seconds": 14401},
        {"max_pi_review_minutes": 181},
        {"max_external_spend": 1.0},
    ):
        with pytest.raises(ValidationError):
            BatchEnvelope.model_validate(envelope.model_dump() | change)


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "b" * 64},
        {"size_bytes": 4539028},
        {"page_count": 103},
    ],
)
def test_stale_metadata_cannot_override_pin(
    envelope: BatchEnvelope, change: dict[str, object]
) -> None:
    values = {"sha256": SOURCE_SHA256, "size_bytes": 4539029, "page_count": 104} | change
    with pytest.raises(ValueError):
        verify_source_identity(envelope, **values)  # type: ignore[arg-type]


def test_continuation_stops_at_envelope(envelope: BatchEnvelope) -> None:
    require_continuation_pages(envelope, unit(), (2, 3))
    with pytest.raises(ValueError, match="STOP"):
        require_continuation_pages(envelope, unit(), (2, 19))


def test_exact_authorized_retained_source_can_be_outside_raw(
    envelope: BatchEnvelope,
    tmp_path: Path,
) -> None:
    source = tmp_path / "technical" / "retained" / "report-264.pdf"
    retained = BatchEnvelope.model_validate(envelope.model_dump() | {"source_path": source})
    verify_envelope(
        retained,
        expected_data_root=retained.data_root,
        expected_source_path=source,
        expected_tool=retained.tool,
        expected_resource=retained.resource,
        expected_owner_instruction_id=retained.owner_instruction_id,
    )
    for forbidden in (
        retained.output_root / "report-264.pdf",
        retained.resource.repository_root / "report-264.pdf",
    ):
        with pytest.raises(ValidationError):
            BatchEnvelope.model_validate(retained.model_dump() | {"source_path": forbidden})


def test_exporter_includes_additive_batch_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_schemas.py"
    main = cast(Callable[[], int], runpy.run_path(str(script))["main"])
    output = tmp_path / "schemas"
    monkeypatch.setattr(sys, "argv", [str(script), "--output", str(output)])
    assert main() == 0
    generated = output / "execution" / "report264_batch1_v1.json"
    assert generated.read_bytes() == schema_bytes()
    monkeypatch.setattr(sys, "argv", [str(script), "--check", "--output", str(output)])
    assert main() == 0
    generated.write_bytes(b"stale synthetic schema")
    assert main() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"physical_pages": (*ALLOWED_PAGES, 19)},
        {"packets": 9},
        {"tasks": 21},
        {"wall_seconds": 14401},
        {"pi_review_minutes": 181},
        {"external_spend": 1.0},
    ],
)
def test_runtime_budget_stops_before_next_operation(
    envelope: BatchEnvelope,
    change: dict[str, object],
) -> None:
    require_budget(envelope, BatchUsage())
    with pytest.raises(ValueError, match="STOP"):
        require_budget(envelope, BatchUsage.model_validate(change))


@pytest.mark.parametrize("field", ["report.report_number", "report.reference_period"])
def test_report_context_only_two_fields(envelope: BatchEnvelope, field: str) -> None:
    context = ReportContextAssociation.model_validate_json(json.dumps(association(field)))
    validate_report_context(
        context, envelope, (unit(), unit((1,), "cover-unit")), {("cover-unit", 1): b"264"}
    )


@pytest.mark.parametrize(
    "change",
    [
        {"field_name": "case_snapshot.case_status"},
        {"report_id": "other-report"},
        {"report_number": 269},
        {"source_sha256": "b" * 64},
        {"target_report_id": "other-report"},
        {"context_source_unit_id": "unknown-unit"},
    ],
)
def test_context_wrong_field_report_hash_or_unit_rejected(
    envelope: BatchEnvelope,
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        context = ReportContextAssociation.model_validate_json(json.dumps(association() | change))
        validate_report_context(
            context, envelope, (unit(), unit((1,), "cover-unit")), {("cover-unit", 1): b"264"}
        )


def test_context_span_must_match_preserved_quote(envelope: BatchEnvelope) -> None:
    context = ReportContextAssociation.model_validate_json(json.dumps(association()))
    with pytest.raises(ValueError, match="span/text"):
        validate_report_context(
            context, envelope, (unit(), unit((1,), "cover-unit")), {("cover-unit", 1): b"269"}
        )


def test_raw_is_frozen_before_normalization_and_initial_preserved(envelope: BatchEnvelope) -> None:
    prepare_output_root(envelope)
    raw = b'{"literal":" Octubre 2026 ","unknown":null}'

    def normalize(response: bytes) -> MachineCandidate:
        assert (envelope.output_root / "raw_responses" / "response-1.txt").read_bytes() == raw
        return MachineCandidate(
            candidate_id="initial-1",
            batch_id=envelope.batch_id,
            envelope_sha256=envelope.fingerprint,
            raw_response_sha256=hashlib.sha256(response).hexdigest(),
            partial_fields=(
                PartialFieldCandidate(
                    unit_id="case-unit",
                    domain_object_type="report",
                    field_name="report.reference_period",
                    raw_value_json='" Octubre 2026 "',
                    state=AnnotationState.ANNOTATION_UNCERTAIN,
                    unresolved=True,
                ),
            ),
        )

    candidate = freeze_then_normalize(envelope, "response-1", raw, normalize)
    freeze_initial_candidate(envelope, candidate, response_id="response-1")
    first = (envelope.output_root / "initial_candidates.json").read_bytes()
    assert json.loads(first)["partial_fields"][0]["raw_value_json"] == '" Octubre 2026 "'
    with pytest.raises(FileExistsError):
        freeze_then_normalize(envelope, "response-1", b"changed", normalize)
    with pytest.raises(FileExistsError):
        freeze_initial_candidate(envelope, candidate, response_id="response-1")
    assert (envelope.output_root / "initial_candidates.json").read_bytes() == first
    assert (envelope.output_root / "raw_responses" / "response-1.txt").read_bytes() == raw


def test_no_replace_or_canonical_release_output(envelope: BatchEnvelope) -> None:
    prepare_output_root(envelope)
    write_json(envelope, "issues.json", {"unknown": None})
    with pytest.raises(FileExistsError):
        write_json(envelope, "issues.json", {"unknown": 0})
    with pytest.raises(FileExistsError):
        prepare_output_root(envelope)
    for filename in (
        "../05_database/canonical.json",
        "../07_releases/release.json",
        "data.parquet",
        "issues.json:other.json",
        "CON.json",
        "bad?.json",
        "bad<name.json",
        "control\x01.json",
        "trailing./new.json",
        "nested /normal.json",
        "trailing. /new.json",
    ):
        with pytest.raises(ValueError):
            write_json(envelope, filename, {})
    for root in (
        envelope.data_root / "05_database",
        envelope.data_root / "07_releases",
        envelope.data_root / "01_raw" / "manifests",
    ):
        with pytest.raises(ValidationError):
            BatchEnvelope.model_validate(envelope.model_dump() | {"output_root": root})


@pytest.mark.parametrize(
    "filename",
    (
        "CON.json",
        "con.json",
        "PRN.json",
        "AUX.json",
        "NUL.json",
        "COM1.json",
        "LPT9.json",
        "CONIN$.json",
        "CONOUT$.json",
        "con .json",
        "COM¹.json",
        "COM².json",
        "COM³.json",
        "LPT¹.json",
        "LPT².json",
        "LPT³.json",
        "nested/CON.json",
        "CON/normal.json",
    ),
)
def test_reserved_windows_json_names_rejected_before_write(
    envelope: BatchEnvelope, filename: str
) -> None:
    prepare_output_root(envelope)
    with pytest.raises(ValueError, match="unsafe Windows filename"):
        write_json(envelope, filename, {})
    assert tuple(envelope.output_root.iterdir()) == ()


@pytest.mark.parametrize("response_id", ("CON", "con ", "LPT¹"))
def test_reserved_windows_raw_names_rejected_before_write(
    envelope: BatchEnvelope, response_id: str
) -> None:
    prepare_output_root(envelope)
    with pytest.raises(ValueError, match="unsafe Windows filename"):
        freeze_raw_response(envelope, response_id, b"synthetic raw response")
    assert tuple(envelope.output_root.iterdir()) == ()


@pytest.mark.filterwarnings("error::DeprecationWarning")
@pytest.mark.parametrize("stem", ("ordinary", "CONSOLE", "COM10"))
def test_valid_json_and_raw_writes_without_deprecated_path_calls(
    envelope: BatchEnvelope, stem: str
) -> None:
    prepare_output_root(envelope)
    path = write_json(envelope, f"{stem}.json", {"unknown": None})
    assert path == envelope.output_root / f"{stem}.json"
    assert json.loads(path.read_bytes()) == {"unknown": None}
    raw = b"synthetic unnormalized response\n"
    receipt = freeze_raw_response(envelope, stem, raw)
    assert receipt.path == envelope.output_root / "raw_responses" / f"{stem}.txt"
    assert receipt.path.read_bytes() == raw
    assert receipt.response_id == stem
    assert receipt.sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.size_bytes == len(raw)


def test_unknown_raw_response_is_retained_when_parsing_fails(envelope: BatchEnvelope) -> None:
    prepare_output_root(envelope)

    def invalid(_response: bytes) -> MachineCandidate:
        raise ValueError("invalid model response")

    with pytest.raises(ValueError, match="invalid model response"):
        freeze_then_normalize(envelope, "invalid-response", b"unparseable original", invalid)
    assert (envelope.output_root / "raw_responses" / "invalid-response.txt").read_bytes() == (
        b"unparseable original"
    )
    assert not (envelope.output_root / "initial_candidates.json").exists()


def test_unprocessed_and_empty_never_mean_absence(envelope: BatchEnvelope) -> None:
    candidate = MachineCandidate(
        candidate_id="empty",
        batch_id=envelope.batch_id,
        envelope_sha256=envelope.fingerprint,
        raw_response_sha256=hashlib.sha256(b"").hexdigest(),
    )
    assert coverage_state(candidate, "case-unit") == "unprocessed"
    processed = candidate.model_copy(update={"processed_unit_ids": ("case-unit",)})
    assert coverage_state(processed, "case-unit") == "machine_empty_unverified"
    assert "absence" not in json.dumps(processed.model_dump(mode="json"))
    partial = PartialFieldCandidate(
        unit_id="case-unit",
        domain_object_type="event",
        field_name="event.deaths",
    )
    assert partial.raw_value_json is None
    with pytest.raises(ValidationError):
        PartialFieldCandidate.model_validate(partial.model_dump() | {"unresolved": False})


@pytest.mark.parametrize(
    "forbidden",
    [
        "audit_ids",
        "expected_answers",
        "candidate_annotations",
        "pi_decisions",
        "holdout_labels",
        "candidate_answers",
    ],
)
def test_worker_packet_forbids_answer_and_audit_fields(
    envelope: BatchEnvelope,
    forbidden: str,
) -> None:
    packet = make_worker_packet(envelope, "packet-1", (unit(),))
    with pytest.raises(ValidationError):
        type(packet).model_validate(packet.model_dump() | {forbidden: ("private",)})
    assert set(packet.model_dump()) == {
        "packet_id",
        "batch_id",
        "envelope_sha256",
        "source_path",
        "source_sha256",
        "units",
        "neutral_rules",
    }


def test_independent_reader_rejects_candidates_output_and_pi(envelope: BatchEnvelope) -> None:
    packet = make_worker_packet(envelope, "packet-1", (unit(),))
    source = SourceFirstPacket.model_validate(packet.model_dump())
    assert source_first_input(source, envelope) == source
    for change in (
        {"candidate_annotations": ()},
        {"pi_decisions": ()},
        {"source_path": envelope.output_root / "initial_candidates.json"},
        {"source_path": envelope.data_root / "pi_decisions.json"},
    ):
        with pytest.raises(ValueError):
            source_first_input(source.model_dump() | change, envelope)


def test_machine_candidate_cannot_be_pi_decision(envelope: BatchEnvelope) -> None:
    candidate = MachineCandidate(
        candidate_id="empty",
        batch_id=envelope.batch_id,
        envelope_sha256=envelope.fingerprint,
        raw_response_sha256="a" * 64,
    )
    with pytest.raises(ValidationError):
        MachineCandidate.model_validate(candidate.model_dump() | {"origin": "pi_reviewed"})
    with pytest.raises(ValidationError):
        PIDecision.model_validate(candidate.model_dump())
    assert candidate.release == "internal_draft"


def test_actual_envelope_requires_independent_tool_resource_root_identities(
    envelope: BatchEnvelope,
    tmp_path: Path,
) -> None:
    expected = {
        "expected_data_root": envelope.data_root,
        "expected_source_path": envelope.source_path,
        "expected_tool": envelope.tool,
        "expected_resource": envelope.resource,
        "expected_owner_instruction_id": envelope.owner_instruction_id,
    }
    verify_envelope(envelope, **expected)  # type: ignore[arg-type]
    for key, value in (
        ("expected_data_root", tmp_path),
        ("expected_source_path", tmp_path / "other.pdf"),
        ("expected_tool", envelope.tool.model_copy(update={"configuration_sha256": "b" * 64})),
        ("expected_resource", envelope.resource.model_copy(update={"sha256": "b" * 64})),
        ("expected_owner_instruction_id", "other-instruction"),
    ):
        with pytest.raises(ValueError):
            verify_envelope(envelope, **(expected | {key: value}))  # type: ignore[arg-type]
    for change in (
        {"source_path": Path("relative.pdf")},
        {"data_root": Path("relative")},
        {"owner_instruction_id": ""},
    ):
        with pytest.raises(ValidationError):
            BatchEnvelope.model_validate(envelope.model_dump() | change)
    envelope.resource.path.write_bytes(b"changed resource")
    with pytest.raises(ValueError, match="resource"):
        verify_envelope(envelope, **expected)  # type: ignore[arg-type]


def test_regular_annotations_do_not_gain_context_privilege(envelope: BatchEnvelope) -> None:
    from peru_conflicts.benchmark.models import FieldAnnotation

    context = ReportContextAssociation.model_validate_json(json.dumps(association()))
    annotation = FieldAnnotation(
        annotation_id="field-1",
        unit_id="case-unit",
        annotator_id="machine",
        domain_object_type="report",
        field_name="report.report_number",
        state=AnnotationState.OBSERVED,
        raw_value_json="264",
        evidence_anchors=(context.evidence,),
    )
    candidate = MachineCandidate(
        candidate_id="initial-1",
        batch_id=envelope.batch_id,
        envelope_sha256=envelope.fingerprint,
        raw_response_sha256="a" * 64,
        annotations=(annotation,),
        processed_unit_ids=("case-unit",),
    )
    with pytest.raises(ValueError, match="outside source boundary"):
        validate_machine_candidate(
            candidate, envelope, (unit(), unit((1,), "cover-unit")), {("cover-unit", 1): b"264"}
        )
