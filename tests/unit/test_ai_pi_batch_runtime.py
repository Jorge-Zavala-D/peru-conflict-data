"""Source-only packet and mechanical representation regressions."""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn, TypedDict, cast

import pytest
from test_ai_pi_batch import envelope as original_envelope

from peru_conflicts.execution import ai_pi_batch_runtime as runtime
from peru_conflicts.execution.ai_pi_batch import (
    ALLOWED_PAGES,
    SOURCE_SHA256,
    BatchEnvelope,
    MachineCandidate,
    ResourceIdentity,
    ToolIdentity,
)
from peru_conflicts.execution.ai_pi_batch_runtime import (
    compare_initial_outputs,
    parse_layout_xml,
    source_first_html,
    source_first_template,
)
from peru_conflicts.hashing import canonical_json_bytes, sha256_file


@pytest.fixture(name="envelope")
def runtime_envelope(tmp_path: Path) -> BatchEnvelope:
    factory = cast(Callable[[Path], BatchEnvelope], original_envelope.__wrapped__)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    return factory(tmp_path)


class PreparationArgs(TypedDict):
    fixed_draw: tuple[int, ...]
    context_pages: tuple[int, ...]
    neutral_codebook: str
    reference_config: Mapping[str, object]
    expected_data_root: Path
    expected_source_path: Path
    expected_tool: ToolIdentity
    expected_resource: ResourceIdentity
    expected_owner_instruction_id: str
    started_at: datetime
    deadline: datetime


def preparation_args(envelope: BatchEnvelope) -> tuple[BatchEnvelope, PreparationArgs]:
    draw = (1, 2, 3, 35, 36, 83, 84, 100)
    now = datetime.now(UTC)
    codebook = envelope.resource.path.read_text(encoding="utf-8")
    resource = envelope.resource.model_copy(
        update={
            "packet_configuration_sha256": runtime.sha256(
                canonical_json_bytes(runtime.packet_configuration(draw, context_pages=(1,)))
            ),
        }
    )
    tool = envelope.tool.model_copy(
        update={
            "configuration_sha256": runtime.sha256(canonical_json_bytes(runtime.REFERENCE_CONFIG)),
        }
    )
    bound = envelope.model_copy(update={"resource": resource, "tool": tool})
    return bound, {
        "fixed_draw": draw,
        "context_pages": (1,),
        "neutral_codebook": codebook,
        "reference_config": runtime.REFERENCE_CONFIG,
        "expected_data_root": bound.data_root,
        "expected_source_path": bound.source_path,
        "expected_tool": tool,
        "expected_resource": resource,
        "expected_owner_instruction_id": bound.owner_instruction_id,
        "started_at": now,
        "deadline": now + timedelta(minutes=5),
    }


def fake_preflight(monkeypatch: pytest.MonkeyPatch, envelope: BatchEnvelope) -> None:
    envelope.source_path.parent.mkdir(parents=True, exist_ok=True)
    envelope.source_path.write_bytes(b"S" * envelope.source_size_bytes)

    def synthetic_hash(path: Path) -> str:
        return SOURCE_SHA256 if path == envelope.source_path else sha256_file(path)

    def synthetic_git(root: Path, *args: str) -> str:
        evidence: dict[tuple[str, ...], str] = {
            ("status", "--porcelain=v1", "--untracked-files=all"): "",
            ("rev-parse", "HEAD"): envelope.resource.implementation_git_commit,
            ("rev-parse", "HEAD^{tree}"): envelope.resource.implementation_git_tree,
        }
        return evidence[args]

    monkeypatch.setattr(runtime, "sha256_file", synthetic_hash)
    monkeypatch.setattr(runtime, "_git", synthetic_git)


def test_prepare_requires_independent_identity_before_source_or_output(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound, args = preparation_args(envelope)
    args["expected_owner_instruction_id"] = "different-owner"

    def deny(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("native read before identity")

    monkeypatch.setattr(runtime, "_run_native", deny)
    with pytest.raises(ValueError, match="independently"):
        runtime.prepare_batch(bound, **args)
    assert not bound.output_root.exists()


def test_prepare_freezes_source_first_before_native_text_and_never_replaces(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound, args = preparation_args(envelope)
    fake_preflight(monkeypatch, bound)
    rendered: list[int] = []
    extracted: list[int] = []

    def run_native(command: list[str], *, deadline: datetime) -> bytes:
        if command[0] == str(bound.tool.native_tools[0].path) and "-v" in command:
            return b"synthetic"
        if "-png" in command:
            page = int(command[command.index("-f") + 1])
            frozen = bound.output_root / "pi_source_first" / "PACKET_MANIFEST.json"
            assert frozen.exists() == (page not in (*args["fixed_draw"], *args["context_pages"]))
            rendered.append(page)
            assert int(command[command.index("-l") + 1]) == page
            return b"\x89PNG\r\n\x1a\nsynthetic"
        if "-bbox-layout" in command or "-layout" in command:
            assert (bound.output_root / "pi_source_first" / "PACKET_MANIFEST.json").is_file()
            assert sorted(rendered) == list(ALLOWED_PAGES)
            page = int(command[command.index("-f") + 1])
            extracted.append(page)
            if "-bbox-layout" in command:
                return (
                    b'<doc><page width="10" height="20"><line><word xMin="0" yMin="0" '
                    b'xMax="1" yMax="1">literal</word></line></page></doc>'
                )
            return b"literal\n"
        return b"Pages: 104\nTitle: embedded title only\n"

    monkeypatch.setattr(runtime, "_run_native", run_native)
    result = runtime.prepare_batch(bound, **args)
    assert sorted(rendered) == list(ALLOWED_PAGES)
    assert len(rendered) == 30
    assert set(extracted) == set(ALLOWED_PAGES)
    assert len(cast(tuple[object, ...], result["units"])) == 30
    frame = json.loads((bound.output_root / "manifest" / "source_unit_frame.json").read_bytes())
    assert frame["case_boundary_status"] == "unresolved; no full-case completeness claim"
    packet = (bound.output_root / "pi_source_first" / "source_first_packet.html").read_text(
        encoding="utf-8"
    )
    assert "page-018.png" not in packet
    assert "February" not in packet
    with pytest.raises(FileExistsError):
        runtime.prepare_batch(bound, **args)


def test_prepare_rejects_hash_drift_before_any_pdf_tool_read(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound, args = preparation_args(envelope)
    fake_preflight(monkeypatch, bound)
    monkeypatch.setattr(runtime, "sha256_file", sha256_file)

    def deny(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("source mismatch must precede PDF tool invocation")

    monkeypatch.setattr(runtime, "_run_native", deny)
    with pytest.raises(ValueError, match="source hash/size"):
        runtime.prepare_batch(bound, **args)
    assert not bound.output_root.exists()


def test_initial_finalization_retains_all_raw_before_parse_and_reports_missing_units(
    envelope: BatchEnvelope, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_ai_pi_batch import unit

    from peru_conflicts.execution.ai_pi_batch import prepare_output_root

    prepare_output_root(envelope)
    units = (unit((1,), "p001"), unit((2,), "p002"))
    payload = {
        "candidate_id": "one",
        "batch_id": envelope.batch_id,
        "envelope_sha256": envelope.fingerprint,
        "raw_response_sha256": "a" * 64,
        "processed_unit_ids": ["p001"],
    }
    raw = [("good", json.dumps(payload).encode()), ("bad", b"{invalid")]
    original = runtime.MachineCandidate.model_validate_json

    def validate(value: bytes) -> MachineCandidate:
        assert all(
            (envelope.output_root / "raw_responses" / f"candidate-{name}.txt").exists()
            for name, _ in raw
        )
        return original(value)

    monkeypatch.setattr(runtime.MachineCandidate, "model_validate_json", validate)
    result = runtime.finalize_initial_pass(
        envelope, "candidate", raw, units=units, reference_pages={}
    )
    coverage = cast(dict[str, str], result["coverage"])
    errors = cast(list[dict[str, object]], result["errors"])
    assert coverage["p001"] == "machine_empty_unverified"
    assert coverage["p002"] == "unprocessed"
    assert errors[0]["response_id"] == "bad"
    assert (envelope.output_root / "initial_candidates" / "initial_candidate.json").exists()


def test_comparison_preserves_duplicate_objects_and_current_relationships() -> None:
    obj: dict[str, object] = {
        "object_id": "o1",
        "unit_id": "p001",
        "domain_object_type": "conflict_case",
        "evidence_anchors": [],
    }
    second = obj | {"object_id": "o2"}
    relationship = {"relationship_id": "r1", "from_object_id": "o1", "to_object_id": "o2"}
    result = compare_initial_outputs(
        {"objects": [obj, second], "relationships": [relationship]},
        {"objects": [], "relationships": []},
    )
    assert result["unmatched_initial_a"] == [obj, second]
    assert result["initial_relationships_a"] == [relationship]
    duplicates = cast(list[dict[str, object]], result["duplicate_initial_a"])
    assert len(cast(list[object], duplicates[0]["objects"])) == 2


def test_comparison_reads_retained_pass_fragments_and_never_defaults_missing_inventory() -> None:
    obj = {
        "object_id": "local",
        "unit_id": "p001",
        "domain_object_type": "conflict_case",
        "evidence_anchors": [],
        "field_values": [{"raw_value_json": "1"}],
    }
    a = {
        "candidates": [
            {
                "candidate_id": "fragment-a",
                "objects": [obj],
                "relationships": [{"relationship_original": "continued"}],
            }
        ]
    }
    b = {
        "candidates": [
            {
                "candidate_id": "fragment-b",
                "objects": [obj | {"field_values": [{"raw_value_json": "2"}]}],
                "relationships": [],
            }
        ]
    }
    compared = compare_initial_outputs(a, b)
    assert compared["field_or_support_disagreements"]
    assert compared["relationship_outputs_equal"] is False
    assert (
        cast(list[dict[str, object]], compared["initial_relationships_a"])[0][
            "candidate_fragment_id"
        ]
        == "fragment-a"
    )
    with pytest.raises(ValueError, match="inventory"):
        compare_initial_outputs({"errors": []}, b)
    empty = compare_initial_outputs({"candidates": []}, {"candidates": []})
    assert empty["relationship_outputs_equal"] is None


def test_comparison_retains_top_level_fields_and_report_context_support() -> None:
    fields = {
        "annotations": [{"field_name": "report.report_number", "raw_value_json": "264"}],
        "partial_fields": [{"field_name": "conflict_case.status", "raw_value_json": '"Activo"'}],
        "report_context_associations": [
            {
                "association_id": "local-a",
                "field_name": "report.reference_period",
                "raw_value_json": '"period-a"',
                "evidence": {"source_text": "period-a"},
            }
        ],
    }
    a: dict[str, object] = {
        "candidates": [{"candidate_id": "a", "objects": [], "relationships": [], **fields}]
    }
    b: dict[str, object] = {
        "candidates": [
            {
                "candidate_id": "b",
                "objects": [],
                "relationships": [],
                **fields,
                "annotations": [{"field_name": "report.report_number", "raw_value_json": "126"}],
                "report_context_associations": [
                    {
                        "association_id": "local-b",
                        "field_name": "report.reference_period",
                        "raw_value_json": '"period-b"',
                        "evidence": {"source_text": "period-b"},
                    }
                ],
            }
        ]
    }
    compared = compare_initial_outputs(a, b)
    disagreements = cast(list[dict[str, object]], compared["field_or_support_disagreements"])
    assert {item["container"] for item in disagreements} == {
        "annotations",
        "report_context_associations",
    }
    assert compared["top_level_candidate_fields_a"]
    assert compared["comparison_interpretation"] == "descriptive exact JSON; no semantic resolution"


def test_layout_keeps_literal_words_coordinates_and_physical_page() -> None:
    xml = (
        '<html><body><doc><page width="100" height="200"><flow><block><line>'
        '<word xMin="1" yMin="2" xMax="11" yMax="9">No</word>'
        '<word xMin="12" yMin="2" xMax="30" yMax="9">reportado</word>'
        "</line></block></flow></page></doc></body></html>"
    )
    result = parse_layout_xml(xml, physical_page=100)
    assert result["physical_page"] == 100
    assert result["text"] == "No reportado"
    assert cast(list[dict[str, object]], result["words"])[1] == {
        "text": "reportado",
        "bbox": [12.0, 2.0, 30.0, 9.0],
        "span": [3, 12],
    }


def test_representation_rejects_out_of_envelope_page() -> None:
    with pytest.raises(ValueError, match="envelope"):
        parse_layout_xml("<doc/>", physical_page=42)


def test_source_first_is_blank_source_only_and_escaped() -> None:
    fixture_draw = (1, 2, 3, 35, 36, 83, 84, 100)
    packet = source_first_html(
        fixture_draw, "<script>not an instruction</script>", fixed_pages=fixture_draw
    )
    assert "page-003.png" in packet
    assert "&lt;script&gt;" in packet
    assert "<script>" not in packet
    assert "candidate confidence" not in packet
    assert "candidate_id" not in source_first_template()
    assert "pi_local_temporary_object_label" in source_first_template()
    assert len(source_first_template().splitlines()) == 1


def test_source_first_cannot_substitute_page_or_redraw() -> None:
    with pytest.raises(ValueError, match="fixed"):
        source_first_html(
            (1, 2, 3, 4, 5, 6, 7, 8), "neutral", fixed_pages=(1, 2, 3, 35, 36, 83, 84, 100)
        )


def test_comparison_is_descriptive_does_not_create_pi_or_recall(tmp_path: Path) -> None:
    for dirname, payload in (
        ("a", {"objects": [], "relationships": [], "pages": [100]}),
        ("b", {"objects": [], "relationships": [], "pages": [100]}),
    ):
        folder = tmp_path / dirname
        folder.mkdir()
        (folder / "initial.json").write_text(json.dumps(payload), encoding="utf-8")
    result = compare_initial_outputs(
        {"objects": [], "relationships": [], "pages": [100]},
        {"objects": [], "relationships": [], "pages": [100]},
    )
    assert result["discovery_recall"] is None
    assert result["pi_decisions_created"] is False
    assert result["empty_output_certifies_absence"] is False
    assert result["matching_basis"] == "exact-source-evidence; unmatched is not a proven omission"
