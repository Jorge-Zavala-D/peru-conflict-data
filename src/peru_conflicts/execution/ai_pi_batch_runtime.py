"""Bounded native representations and answer-free PI packaging; no model dispatch."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import subprocess
import traceback
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from xml.etree import ElementTree

from peru_conflicts.acquisition.authorization import _git  # pyright: ignore[reportPrivateUsage]
from peru_conflicts.hashing import canonical_json_bytes, sha256_file

from .ai_pi import SourceUnit
from .ai_pi_batch import (
    ALLOWED_PAGES,
    BatchEnvelope,
    BatchUsage,
    MachineCandidate,
    ResourceIdentity,
    ToolIdentity,
    _write_new,  # pyright: ignore[reportPrivateUsage]
    coverage_state,
    followup_filename,
    freeze_raw_response,
    make_worker_packet,
    prepare_output_root,
    require_budget,
    require_unit,
    validate_machine_candidate,
    verify_envelope,
    verify_source_identity,
    write_json,
)
from .evidence_regions import RegionEvidenceMethod, RegionMatch, RegionResource
from .references import reference_text, sha256

REFERENCE_CONFIG: dict[str, object] = {
    "mode": "layout",
    "encoding": "UTF-8",
    "eol": "unix",
    "unicode_normalization": "none",
    "ocr": False,
}
WORKER_PAGE_GROUPS = (tuple(range(1, 19)), tuple(range(35, 42)), tuple(range(83, 87)), (100,))


def packet_configuration(
    fixed_draw: tuple[int, ...], *, context_pages: tuple[int, ...] = ()
) -> dict[str, object]:
    return {
        "physical_pages": list(ALLOWED_PAGES),
        "fixed_draw": list(fixed_draw),
        "context_pages": list(context_pages),
        "source_unit_policy": "physical-page-unsegmented-v1",
        "worker_page_groups": [list(pages) for pages in WORKER_PAGE_GROUPS],
        "render_dpi": 144,
    }


def _remaining(deadline: datetime) -> float:
    if deadline.tzinfo is None:
        raise ValueError("aware runtime deadline required")
    remaining = (deadline - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        raise ValueError("STOP: batch wall deadline reached")
    return remaining


def _run_native(command: list[str], *, deadline: datetime) -> bytes:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=min(120, _remaining(deadline)),
    )
    return result.stdout + result.stderr if "-v" in command else result.stdout


def _artifact(envelope: BatchEnvelope, filename: str, data: bytes) -> Path:
    relative = Path(filename)
    target = envelope.output_root / relative
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not target.resolve().is_relative_to(envelope.output_root)
    ):
        raise ValueError("artifact outside prepared output")
    return _write_new(target, data)


def prepare_batch(
    envelope: BatchEnvelope,
    *,
    fixed_draw: tuple[int, ...],
    neutral_codebook: str,
    reference_config: Mapping[str, object],
    expected_data_root: Path,
    expected_source_path: Path,
    expected_tool: ToolIdentity,
    expected_resource: ResourceIdentity,
    expected_owner_instruction_id: str,
    started_at: datetime,
    deadline: datetime,
    context_pages: tuple[int, ...] = (),
) -> dict[str, object]:
    """Prepare only the authorized page representations; freeze PI input before text reads."""
    verify_envelope(
        envelope,
        expected_data_root=expected_data_root,
        expected_source_path=expected_source_path,
        expected_tool=expected_tool,
        expected_resource=expected_resource,
        expected_owner_instruction_id=expected_owner_instruction_id,
    )
    if (
        started_at.tzinfo is None
        or deadline.tzinfo is None
        or not 0 < (deadline - started_at).total_seconds() <= envelope.max_wall_seconds
    ):
        raise ValueError("aware bounded start/deadline required")
    if started_at > datetime.now(UTC):
        raise ValueError("runtime start cannot be in the future")
    _remaining(deadline)
    if envelope.output_root.exists():
        raise FileExistsError("batch output already exists; never replace or resume implicitly")
    if (
        reference_config != REFERENCE_CONFIG
        or sha256(canonical_json_bytes(dict(reference_config)))
        != envelope.tool.configuration_sha256
    ):
        raise ValueError("reference/tool configuration identity mismatch")
    configuration = packet_configuration(fixed_draw, context_pages=context_pages)
    if sha256(canonical_json_bytes(configuration)) != envelope.resource.packet_configuration_sha256:
        raise ValueError("packet configuration identity mismatch")
    if neutral_codebook.encode("utf-8") != envelope.resource.path.read_bytes():
        raise ValueError("neutral codebook resource bytes mismatch")
    packet_html = source_first_html(
        fixed_draw,
        neutral_codebook,
        fixed_pages=fixed_draw,
        context_pages=context_pages,
    )
    repository = envelope.resource.repository_root
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("STOP: clean implementation Git checkout required")
    if (_git(repository, "rev-parse", "HEAD"), _git(repository, "rev-parse", "HEAD^{tree}")) != (
        envelope.resource.implementation_git_commit,
        envelope.resource.implementation_git_tree,
    ):
        raise ValueError("STOP: implementation commit/tree identity mismatch")
    tools = {tool.tool_name: tool for tool in envelope.tool.native_tools}
    observed_sha = sha256_file(envelope.source_path)
    observed_size = envelope.source_path.stat().st_size
    if (observed_sha, observed_size) != (envelope.source_sha256, envelope.source_size_bytes):
        raise ValueError("STOP: source hash/size identity mismatch")
    for tool in tools.values():
        observed = _run_native([str(tool.path), "-v"], deadline=deadline).decode(
            "utf-8", errors="strict"
        )
        if tool.version not in observed:
            raise ValueError(f"{tool.tool_name} version identity mismatch")
    info = _run_native(
        [str(tools["pdfinfo"].path), str(envelope.source_path)], deadline=deadline
    ).decode("utf-8", errors="strict")
    count = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
    if count is None:
        raise ValueError("STOP: pdfinfo physical-page identity missing")
    verify_source_identity(
        envelope,
        sha256=observed_sha,
        size_bytes=observed_size,
        page_count=int(count[1]),
    )
    units = tuple(
        SourceUnit(
            unit_id=f"p{page:03d}",
            report_id=envelope.report_id,
            report_number=264,
            source_sha256=envelope.source_sha256,
            pages=(page,),
            sections=("physical_page",),
        )
        for page in envelope.physical_pages
    )
    usage = BatchUsage(physical_pages=envelope.physical_pages, packets=4)
    require_budget(envelope, usage)
    prepare_output_root(envelope)
    write_json(envelope, "manifest/run_envelope.json", envelope.model_dump(mode="json"))
    write_json(
        envelope,
        "receipts/source_identity.json",
        {
            "path": str(envelope.source_path),
            "sha256": envelope.source_sha256,
            "size_bytes": envelope.source_size_bytes,
            "physical_page_count": envelope.source_page_count,
            "pdfinfo_representation": info,
            "embedded_title_status": "representation metadata only; not verified source period",
        },
    )
    write_json(
        envelope, "receipts/source_code_identity.json", envelope.resource.model_dump(mode="json")
    )
    write_json(
        envelope,
        "manifest/tool_configuration.json",
        {
            "tool": envelope.tool.model_dump(mode="json"),
            "reference_config": dict(reference_config),
            "source_unit_policy": configuration["source_unit_policy"],
        },
    )
    write_json(
        envelope,
        "manifest/source_unit_frame.json",
        {
            "units": [unit.model_dump(mode="json") for unit in units],
            "case_boundary_status": "unresolved; no full-case completeness claim",
            "unit_meaning": "single physical-page observations, never whole-case boundaries",
            "continuation_rule": "only explicit in-envelope units; otherwise scope-incomplete",
            "ordinary_field_evidence": "anchor inside own unit; report context is separate",
            "report_context_fields": ["report.report_number", "report.reference_period"],
        },
    )
    image_receipts: list[dict[str, object]] = []
    native_invocations = 4
    source_first_pages = tuple(
        page for page in envelope.physical_pages if page in (*fixed_draw, *context_pages)
    )

    def render(page: int) -> None:
        nonlocal native_invocations
        command = [
            str(tools["pdftoppm"].path),
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-r",
            "144",
            "-png",
            str(envelope.source_path),
        ]
        try:
            native_invocations += 1
            image = _run_native(command, deadline=deadline)
            if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("renderer did not return PNG")
            _artifact(envelope, f"representations/page-{page:03d}.png", image)
            image_receipts.append(
                {"physical_page": page, "sha256": sha256(image), "size_bytes": len(image)}
            )
        except Exception as error:
            write_json(
                envelope,
                "preparation_failure.json",
                {
                    "phase": "render",
                    "physical_page": page,
                    "error": str(error),
                    "kind": type(error).__name__,
                },
            )
            raise

    for page in source_first_pages:
        render(page)
    _artifact(envelope, "pi_source_first/source_first_packet.html", packet_html.encode("utf-8"))
    _artifact(
        envelope,
        "pi_source_first/source_first_decision_template.csv",
        source_first_template().encode("utf-8"),
    )
    _artifact(envelope, "pi_source_first/neutral_codebook.txt", neutral_codebook.encode("utf-8"))
    write_json(
        envelope,
        "pi_source_first/fixed_draw.json",
        {"physical_pages": list(fixed_draw), "context_pages": list(context_pages)},
    )
    native_at_freeze = native_invocations
    usage = BatchUsage(
        physical_pages=source_first_pages,
        packets=0,
        wall_seconds=(datetime.now(UTC) - started_at).total_seconds(),
    )
    write_json(
        envelope,
        "manifest/resource_usage.json",
        {
            "usage": usage.model_dump(mode="json"),
            "token_usage": "UNOBSERVED",
            "native_invocations": native_at_freeze,
            "source_model_tasks": 0,
            "started_at": started_at.isoformat(),
            "deadline": deadline.isoformat(),
            "measurement_stage": "source-first freeze; later usage recorded separately",
        },
    )
    write_json(
        envelope,
        "receipts/execution_receipt.json",
        {
            "state": "prepared_source_first_not_machine_complete",
            "source_pages_rendered": list(source_first_pages),
            "native_invocations": native_at_freeze,
            "source_model_tasks": 0,
            "pi_decisions_created": False,
            "token_usage": "UNOBSERVED",
        },
    )
    packet_files = (
        "pi_source_first/source_first_packet.html",
        "pi_source_first/source_first_decision_template.csv",
        "pi_source_first/neutral_codebook.txt",
        "pi_source_first/fixed_draw.json",
        "manifest/run_envelope.json",
        "manifest/source_unit_frame.json",
        "manifest/tool_configuration.json",
        "manifest/resource_usage.json",
        "receipts/source_identity.json",
        "receipts/source_code_identity.json",
        "receipts/execution_receipt.json",
    )
    frozen = {name: sha256_file(envelope.output_root / name) for name in packet_files}
    write_json(
        envelope,
        "manifest/batch_manifest.json",
        {
            "batch_id": envelope.batch_id,
            "envelope_sha256": envelope.fingerprint,
            "source_first_files": frozen,
            "images": image_receipts,
            "gate": "source-first inputs frozen before native-text extraction or machine response",
            "scientific_gate": "requires independent discovery and subsequent PI review",
        },
    )
    frozen["manifest/batch_manifest.json"] = sha256_file(
        envelope.output_root / "manifest/batch_manifest.json"
    )
    write_json(
        envelope,
        "pi_source_first/PACKET_MANIFEST.json",
        {
            "batch_id": envelope.batch_id,
            "envelope_sha256": envelope.fingerprint,
            "files": frozen,
            "images": image_receipts,
            "packet_configuration": configuration,
            "pi_answers": "none",
            "candidate_content": "none",
            "native_text_extraction_started": False,
        },
    )
    for page in envelope.physical_pages:
        if page not in source_first_pages:
            render(page)
    references: dict[tuple[str, int], bytes] = {}
    representations: list[dict[str, object]] = []
    for unit in units:
        page = unit.pages[0]
        base = [str(tools["pdftotext"].path), "-f", str(page), "-l", str(page)]
        try:
            native_invocations += 1
            layout = _run_native(
                [
                    *base,
                    "-layout",
                    "-enc",
                    "UTF-8",
                    "-eol",
                    "unix",
                    "-nopgbrk",
                    str(envelope.source_path),
                    "-",
                ],
                deadline=deadline,
            )
            reference_text(layout)
            _artifact(envelope, f"references/page-{page:03d}.txt", layout)
            references[(unit.unit_id, page)] = layout
            native_invocations += 1
            bbox = _run_native(
                [
                    *base,
                    "-bbox-layout",
                    "-enc",
                    "UTF-8",
                    "-eol",
                    "unix",
                    str(envelope.source_path),
                    "-",
                ],
                deadline=deadline,
            )
            _artifact(envelope, f"representations/page-{page:03d}-bbox.txt", bbox)
            representation = parse_layout_xml(
                bbox.decode("utf-8", errors="strict"), physical_page=page
            )
            representation["reference_sha256"] = sha256(layout)
            representation["span_reference"] = (
                "bbox joined-word text; field spans must use exact references/page-NNN.txt"
            )
            write_json(envelope, f"representations/page-{page:03d}.json", representation)
            representations.append(
                {
                    "physical_page": page,
                    "reference_sha256": sha256(layout),
                    "bbox_sha256": sha256(bbox),
                    "status": representation["representation_status"],
                }
            )
        except Exception as error:
            representations.append(
                {
                    "physical_page": page,
                    "status": "representation_failed_unverified",
                    "kind": type(error).__name__,
                    "error": str(error),
                }
            )
            write_json(
                envelope, f"representations/page-{page:03d}-failure.json", representations[-1]
            )
    packets = tuple(
        make_worker_packet(
            envelope, f"frame-{index}", tuple(unit for unit in units if unit.pages[0] in pages)
        )
        for index, pages in enumerate(WORKER_PAGE_GROUPS, 1)
    )
    for packet in packets:
        write_json(
            envelope, f"worker_packets/{packet.packet_id}.json", packet.model_dump(mode="json")
        )
    _artifact(envelope, "worker_packets/neutral_codebook.txt", neutral_codebook.encode("utf-8"))
    write_json(
        envelope,
        "representations/representation_manifest.json",
        {
            "source_sha256": envelope.source_sha256,
            "pages": representations,
            "visual_source_authoritative": True,
        },
    )
    write_json(
        envelope,
        "representations/page_coverage.json",
        {unit.unit_id: "unprocessed" for unit in units},
    )
    usage = BatchUsage(
        physical_pages=envelope.physical_pages,
        packets=len(packets),
        wall_seconds=(datetime.now(UTC) - started_at).total_seconds(),
    )
    require_budget(envelope, usage)
    _remaining(deadline)
    write_json(
        envelope,
        "receipts/preparation_complete.json",
        {
            "usage": usage.model_dump(mode="json"),
            "token_usage": "UNOBSERVED",
            "started_at": started_at.isoformat(),
            "deadline": deadline.isoformat(),
            "native_invocations": native_invocations,
            "source_model_tasks": 0,
            "state": "representations_prepared_not_machine_complete",
        },
    )
    return {
        "units": units,
        "reference_pages": references,
        "worker_packets": packets,
        "representations": representations,
        "usage": usage,
    }


def finalize_initial_pass(
    envelope: BatchEnvelope,
    pass_name: Literal["candidate", "discovery"],
    raw_responses: Sequence[tuple[str, bytes]],
    *,
    units: tuple[SourceUnit, ...],
    reference_pages: Mapping[tuple[str, int], bytes],
    output_prefix: str | None = None,
    region_methods: Mapping[str, tuple[RegionEvidenceMethod, ...]] | None = None,
    region_resources: Mapping[str, RegionResource] | None = None,
) -> dict[str, object]:
    """Retain exact responses before parsing; never turn a failure or empty result into absence."""
    if pass_name not in {"candidate", "discovery"}:
        raise ValueError("only candidate or independent discovery pass permitted")
    for unit in units:
        require_unit(envelope, unit)
    if len(set(unit.unit_id for unit in units)) != len(units):
        raise ValueError("finalization units must be unique")
    if (region_methods or region_resources) and output_prefix is None:
        raise ValueError("new region methods require a separate derivative destination")
    if not set(region_methods or {}).issubset({response_id for response_id, _ in raw_responses}):
        raise ValueError("region declarations name an unknown response")
    if output_prefix is not None:
        probe = envelope.output_root / followup_filename("normalization.json", output_prefix)
        if probe.parent.exists():
            raise ValueError("followup destination already exists")
        # The normal no-replace writer below validates containment and filename safety.
    receipts = [
        freeze_raw_response(
            envelope, f"{pass_name}-{response_id}", raw, output_prefix=output_prefix
        )
        for response_id, raw in raw_responses
    ]
    candidates: list[MachineCandidate] = []
    issues: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    rejected_responses: list[dict[str, object]] = []
    evidence_matches: list[dict[str, object]] = []
    for (response_id, raw), receipt in zip(raw_responses, receipts, strict=True):
        matches: list[RegionMatch] = []
        admitted = False
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("machine response must contain one candidate object")
            payload = cast(dict[str, object], parsed)
            if payload.get("region_evidence_methods"):
                raise ValueError("machine replies cannot self-declare new region methods")
            payload["raw_response_sha256"] = receipt.sha256
            declarations = (region_methods or {}).get(response_id, ())
            if declarations:
                payload["region_evidence_methods"] = [
                    m.model_dump(mode="json") for m in declarations
                ]
            candidate = MachineCandidate.model_validate_json(canonical_json_bytes(payload))
            found = validate_machine_candidate(
                candidate,
                envelope,
                units,
                reference_pages,
                region_resources=region_resources,
                region_matches=matches,
            )
            write_json(
                envelope,
                followup_filename(
                    f"normalized_responses/{pass_name}-{response_id}.json", output_prefix
                ),
                candidate.model_dump(mode="json"),
            )
            candidates.append(candidate)
            issues.append({"response_id": response_id, "issues": list(found)})
            admitted = True
        except Exception as error:
            errors.append(
                {
                    "response_id": response_id,
                    "kind": type(error).__name__,
                    "error": str(error),
                    "raw_sha256": receipt.sha256,
                }
            )
            if output_prefix is not None:
                try:
                    original_payload: object = json.loads(raw)
                except ValueError:
                    original_payload = None
                rejected_responses.append(
                    {
                        "response_id": response_id,
                        "raw_sha256": receipt.sha256,
                        "original_payload": original_payload,
                        "normalization": "rejected_response_not_source_absence",
                        "all_original_entries_retained": True,
                        "new_followup_traceback": traceback.format_exc(),
                    }
                )
        if output_prefix is not None:
            evidence_matches.extend(
                {
                    "response_id": response_id,
                    "normalization_status": "admitted" if admitted else "rejected",
                    "result": match.model_dump(mode="json"),
                }
                for match in matches
            )
    coverage: dict[str, str] = {}
    for unit in units:
        states = {coverage_state(candidate, unit.unit_id) for candidate in candidates}
        coverage[unit.unit_id] = (
            "machine_candidate_present"
            if "machine_candidate_present" in states
            else "machine_empty_unverified"
            if "machine_empty_unverified" in states
            else "unprocessed"
        )
    result: dict[str, object] = {
        "batch_id": envelope.batch_id,
        "envelope_sha256": envelope.fingerprint,
        "pass_name": pass_name,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "raw_responses": [receipt.model_dump(mode="json") for receipt in receipts],
        "issues": issues,
        "errors": errors,
        "coverage": coverage,
        "status": "incomplete"
        if errors or any(value == "unprocessed" for value in coverage.values())
        else "requires_review",
        "empty_output_certifies_absence": False,
        "pi_decisions_created": False,
        "merge_policy": "fragments retained separately; no silent duplicate ID replacement",
    }
    if output_prefix is not None:
        result.update(
            {
                "kind": "separately_versioned_normalization_derivative_not_initial_run",
                "rejected_responses": rejected_responses,
                "region_evidence_matches": evidence_matches,
                "region_method_declarations": {
                    response_id: [m.model_dump(mode="json") for m in methods]
                    for response_id, methods in (region_methods or {}).items()
                },
                "original_outputs_replaced": False,
                "coverage_interpretation": (
                    "admitted normalization only; rejected entries are noncomparable"
                ),
            }
        )
    filename = (
        "initial_candidates/initial_candidate.json"
        if pass_name == "candidate"
        else "independent_discovery/initial_discovery.json"
    )
    write_json(envelope, followup_filename(filename, output_prefix), result)
    return result


def parse_layout_xml(xml: str, *, physical_page: int) -> dict[str, object]:
    if physical_page not in ALLOWED_PAGES:
        raise ValueError("physical page outside envelope")
    root = ElementTree.fromstring(xml)
    page = next((e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "page"), None)
    if page is None:
        raise ValueError("native representation has no page")
    words: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []
    parts: list[str] = []
    offset = 0
    for line in page.iter():
        if line.tag.rsplit("}", 1)[-1] != "line":
            continue
        row: list[dict[str, object]] = []
        for element in line:
            if element.tag.rsplit("}", 1)[-1] != "word":
                continue
            text = "".join(element.itertext())
            if parts:
                offset += 1
            item: dict[str, object] = {
                "text": text,
                "bbox": [float(element.attrib[k]) for k in ("xMin", "yMin", "xMax", "yMax")],
                "span": [offset, offset + len(text)],
            }
            row.append(item)
            words.append(item)
            parts.append(text)
            offset += len(text)
        if row:
            lines.append({"words": row})
    return {
        "physical_page": physical_page,
        "width": float(page.attrib["width"]),
        "height": float(page.attrib["height"]),
        "text": " ".join(parts),
        "words": words,
        "layout_lines": lines,
        "representation_status": "native_text_present" if words else "native_text_empty_unverified",
        "table_structure": "layout_rows_retained; cell semantics not certified",
    }


def source_first_template() -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream).writerow(
        [
            "source_physical_page",
            "source_unit",
            "discovered_object_family",
            "pi_local_temporary_object_label",
            "source_visible_object_existence",
            "literal_source_value_or_state",
            "source_evidence",
            "discovery_inventory_completeness_judgment",
            "uncertainty_or_unresolved_issue",
            "rationale_or_comment",
            "additional_context_pages_used",
        ]
    )
    return stream.getvalue()


def source_first_html(
    selected_pages: tuple[int, ...],
    neutral_codebook: str,
    *,
    fixed_pages: tuple[int, ...],
    context_pages: tuple[int, ...] = (),
) -> str:
    if (
        selected_pages != fixed_pages
        or len(set(selected_pages)) != 8
        or any(p not in ALLOWED_PAGES for p in selected_pages)
    ):
        raise ValueError("source-first draw must remain fixed")
    if len(set(context_pages)) != len(context_pages) or any(
        page not in ALLOWED_PAGES for page in context_pages
    ):
        raise ValueError("source-first context outside envelope")
    nav = " ".join(f'<a href="#p{p}">PDF {p}</a>' for p in selected_pages)
    sections = "".join(
        f'<section id="p{p}"><h2>Physical PDF page {p}</h2>'
        f'<a href="../representations/page-{p:03d}.png">'
        f'<img src="../representations/page-{p:03d}.png" alt="Complete physical PDF page {p}"></a>'
        "</section>"
        for p in selected_pages
    )
    context = " ".join(
        f'<a href="../representations/page-{p:03d}.png">PDF {p}</a>'
        for p in context_pages
        if p not in selected_pages
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>Report 264 — answer-free source-first review</title>"
        "<style>body{font:17px Georgia,serif;max-width:1100px;margin:2em auto;padding:1em;"
        "line-height:1.5}nav{position:sticky;top:0;background:white;padding:.7em;"
        "border:1px solid #bbb}"
        "img{width:100%;height:auto}section{margin:3em 0;break-before:page}"
        "pre{white-space:pre-wrap;font:15px Georgia,serif}a{color:#17456b}</style>"
        "<h1>Report 264: source-first review</h1>"
        "<p>Pinned source: report 264. Physical PDF numbering is used throughout. "
        "The images reproduce full selected pages, without highlights or machine answers. "
        "The visual source remains authoritative over derived text.</p>"
        "<p>Use the blank decision template to discover source-visible objects and record "
        "literal values/states, evidence, completeness and unresolved issues. Your temporary "
        "labels are your own. An empty machine output or an apparent empty page never proves "
        "that no eligible object exists. Do not infer an event from a stock/cumulative "
        "indicator.</p>"
        "<p>The fixed audit samples eight pages; it does not establish report-wide or population "
        "accuracy. Record actual units/fields reviewed and additional context used. "
        "Do not open machine-output folders before preserving your source-first review.</p>"
        f'<nav>{nav} <a href="#rules">Neutral definitions</a></nav>{sections}'
        "<details><summary>Permitted continuation/context — open only when needed</summary>"
        "<p>These explicit neutral context links are not added sampled review units. "
        "Use only the necessary in-envelope continuation "
        "or report context, and record each extra page. If faithful interpretation requires a "
        "page outside the authorised envelope, mark the object scope-incomplete; do not widen "
        f"the envelope.</p>{context}</details>"
        '<section id="rules"><h2>Neutral scientific definitions</h2><pre>'
        f"{html.escape(neutral_codebook)}</pre></section></html>\n"
    )


def _object_key(obj: object) -> str:
    if not isinstance(obj, dict):
        return json.dumps(obj, sort_keys=True, ensure_ascii=False)
    value = cast(dict[str, object], obj)
    evidence = {
        "domain_object_type": value.get("domain_object_type"),
        "unit_id": value.get("unit_id"),
        "evidence_anchors": value.get("evidence_anchors"),
    }
    return json.dumps(evidence, sort_keys=True, ensure_ascii=False)


def _comparison_inventory(
    value: Mapping[str, object],
) -> tuple[dict[str, list[object]], bool, list[str]]:
    wrapped = "candidates" in value
    fragments: object = value["candidates"] if wrapped else [dict(value)]
    if not isinstance(fragments, list):
        raise ValueError("retained candidate inventory must be a list")
    inventory: dict[str, list[object]] = {
        name: []
        for name in (
            "objects",
            "relationships",
            "annotations",
            "partial_fields",
            "report_context_associations",
        )
    }
    missing: list[str] = []
    for index, fragment in enumerate(cast(list[object], fragments)):
        if not isinstance(fragment, dict):
            raise ValueError("candidate inventory fragment must be an object")
        candidate = cast(dict[str, object], fragment)
        for name, target in inventory.items():
            if name not in candidate and name not in {"objects", "relationships"}:
                missing.append(f"{index}:{name}")
                continue
            if name not in candidate or not isinstance(candidate[name], list):
                raise ValueError(f"candidate inventory requires explicit {name} list")
            for item in cast(list[object], candidate[name]):
                if not isinstance(item, dict):
                    raise ValueError("candidate inventory entry must be an object")
                preserved = cast(dict[str, object], item)
                target.append(
                    preserved
                    | {
                        "candidate_fragment_id": candidate.get("candidate_id"),
                        "candidate_fragment_index": index,
                    }
                    if wrapped
                    else preserved
                )
    return inventory, bool(cast(list[object], fragments)), missing


def _scientific_inventory(objects: list[object]) -> list[dict[str, object]]:
    return [
        {
            key: value
            for key, value in cast(dict[str, object], obj).items()
            if key
            not in {
                "object_id",
                "association_id",
                "relationship_id",
                "candidate_fragment_id",
                "candidate_fragment_index",
            }
        }
        for obj in objects
    ]


def compare_initial_outputs(a: Mapping[str, object], b: Mapping[str, object]) -> dict[str, object]:
    inventory_a, observed_a, missing_a = _comparison_inventory(a)
    inventory_b, observed_b, missing_b = _comparison_inventory(b)
    a_objects, relation_a = inventory_a["objects"], inventory_a["relationships"]
    b_objects, relation_b = inventory_b["objects"], inventory_b["relationships"]
    a_keys = [_object_key(x) for x in a_objects]
    b_keys = [_object_key(x) for x in b_objects]
    a_map: dict[str, list[object]] = defaultdict(list)
    b_map: dict[str, list[object]] = defaultdict(list)
    for key, obj in zip(a_keys, a_objects, strict=True):
        a_map[key].append(obj)
    for key, obj in zip(b_keys, b_objects, strict=True):
        b_map[key].append(obj)
    common = sorted(set(a_map) & set(b_map))
    differences = [
        {"evidence_key": key, "initial_a": a_map[key], "initial_b": b_map[key]}
        for key in common
        if _scientific_inventory(a_map[key]) != _scientific_inventory(b_map[key])
    ]
    fields = ("annotations", "partial_fields", "report_context_associations")
    for name in fields:
        if (
            observed_a
            and observed_b
            and not any(item.endswith(f":{name}") for item in (*missing_a, *missing_b))
            and _scientific_inventory(inventory_a[name]) != _scientific_inventory(inventory_b[name])
        ):
            differences.append(
                {"container": name, "initial_a": inventory_a[name], "initial_b": inventory_b[name]}
            )
    return {
        "matching_basis": "exact-source-evidence; unmatched is not a proven omission",
        "unmatched_initial_a": [obj for k in sorted(set(a_map) - set(b_map)) for obj in a_map[k]],
        "unmatched_initial_b": [obj for k in sorted(set(b_map) - set(a_map)) for obj in b_map[k]],
        "duplicate_initial_a": [
            {"evidence_key": k, "objects": values}
            for k, values in sorted(a_map.items())
            if len(values) > 1
        ],
        "duplicate_initial_b": [
            {"evidence_key": k, "objects": values}
            for k, values in sorted(b_map.items())
            if len(values) > 1
        ],
        "field_or_support_disagreements": differences,
        "top_level_candidate_fields_a": {name: inventory_a[name] for name in fields},
        "top_level_candidate_fields_b": {name: inventory_b[name] for name in fields},
        "missing_candidate_containers_a": missing_a,
        "missing_candidate_containers_b": missing_b,
        "comparison_interpretation": "descriptive exact JSON; no semantic resolution",
        "relationship_outputs_equal": _scientific_inventory(relation_a)
        == _scientific_inventory(relation_b)
        if observed_a and observed_b
        else None,
        "candidate_inventory_observed_a": observed_a,
        "candidate_inventory_observed_b": observed_b,
        "initial_relationships_a": relation_a,
        "initial_relationships_b": relation_b,
        "discovery_recall": None,
        "pi_decisions_created": False,
        "empty_output_certifies_absence": False,
        "semantic_matching_requires_pi": True,
        "initial_a_sha256": hashlib.sha256(
            json.dumps(dict(a), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "initial_b_sha256": hashlib.sha256(
            json.dumps(dict(b), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
    }
