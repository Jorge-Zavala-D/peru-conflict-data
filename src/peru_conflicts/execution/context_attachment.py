"""Hash-bound, role-neutral inspection views. No discovery or extraction calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from copy import deepcopy
from itertools import pairwise
from pathlib import Path
from typing import Any, NoReturn, cast

VERSION = "SOURCE_BOUND_CONTEXT_ATTACHMENT_V002"
PROFILE_VERSION = "SOURCE_BOUND_CONTEXT_ROLE_PROFILE_V001"
PROFILE_ROLES = {
    "regional_quantitative": {"category", "count", "percentage"},
    "priority_documentary": {"place_text", "case_description", "published_situation"},
}
TARGETS = {
    "regional_quantitative": {
        "subject": "table_proposal",
        "reporting_period": "table_proposal",
        "geographic_breakdown": "reported_organization",
        "count_unit": "count_column",
        "percentage_sign": "percentage_column",
    },
    "priority_documentary": {
        "introductory_scope": "table_proposal",
        "documentary_scope": "table_proposal",
    },
}
PERMISSIONS = {
    "inspection": True,
    "normalization": False,
    "automatic_dispatch": False,
    "scientific_acceptance": False,
    "benchmark_scoring": False,
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def record_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def bad_constant(value: str) -> NoReturn:
        raise ValueError("nonfinite_json:" + value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)


def attach_context(request: dict[str, Any], documents: dict[str, bytes]) -> dict[str, Any]:
    """Preserve supplied records and qualified links; never discover or resolve ownership."""
    require(request["contract"] == VERSION, "contract_version")
    require(request.get("human_reviewed", False) is False, "evidence_reclassification")
    require(request["alternative_completeness"] is False, "alternative_completeness")
    require(set(documents) == set(request["documents"]), "document_registry_mismatch")
    loaded: dict[str, Any] = {}
    for name, pin in request["documents"].items():
        require(re.fullmatch("[0-9a-f]{64}", pin["sha256"]) is not None, "invalid_hash")
        require(
            hashlib.sha256(documents[name]).hexdigest() == pin["sha256"], "hash_mismatch:" + name
        )
        loaded[name] = strict_json(documents[name])

    def dereference(ref: dict[str, Any]) -> tuple[Any, str]:
        try:
            pointer = ref["pointer"]
            value = loaded[ref["document"]]
            require(pointer == "" or pointer.startswith("/"), "reference_unresolved")
            for token in pointer.split("/")[1:]:
                require(re.search(r"~(?![01])", token) is None, "reference_unresolved")
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    require(
                        re.fullmatch(r"0|[1-9][0-9]*", token) is not None, "reference_unresolved"
                    )
                    value = cast("list[Any]", value)[int(token)]
                else:
                    require(isinstance(value, dict), "reference_unresolved")
                    value = cast("dict[str, Any]", value)[token]
            return value, "sha256:" + request["documents"][ref["document"]][
                "sha256"
            ] + "#" + pointer
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError("reference_unresolved:" + str(ref)) from error

    native_name = request["native_document"]
    native = loaded[native_name]
    native_hash = request["documents"][native_name]["sha256"]
    require(re.fullmatch("[0-9a-f]{64}", request["pdf_sha256"]) is not None, "pdf_identity")
    require(
        type(request["physical_page"]) is int
        and native["physical_page"] == request["physical_page"],
        "page_mismatch",
    )
    require(native["width"] > 0 and native["height"] > 0, "native_dimensions")
    descriptor, descriptor_address = dereference(request["descriptor_ref"])
    profile, profile_address = dereference(request["profile_ref"])
    require(
        profile["version"] == PROFILE_VERSION and profile["name"] in PROFILE_ROLES,
        "profile_version",
    )
    columns: list[dict[str, Any]] = profile["columns"]
    by_column = {c["id"]: c for c in columns}
    require(
        len(by_column) == len(columns)
        and len({c["source_index"] for c in columns}) == len(columns),
        "duplicate_columns",
    )
    require(
        all(type(c["source_index"]) is int and c["source_index"] >= 0 for c in columns),
        "column_index",
    )
    require(
        {c["role"] for c in columns} == PROFILE_ROLES[profile["name"]] and len(columns) == 3,
        "profile_roles",
    )
    word_records: list[dict[str, Any]] = descriptor["word_evidence"]
    word_lookup = {w["word_index"]: w for w in word_records}
    require(len(word_lookup) == len(word_records), "duplicate_word_evidence")

    def anchor(index: int) -> dict[str, Any]:
        require(type(index) is int and 0 <= index < len(native["words"]), "word_reference")
        word = native["words"][index]
        old = word_lookup.get(index)
        require(old is not None, "word_evidence_missing")
        old = cast("dict[str, Any]", old)
        evidence, evidence_address = dereference(old["record_ref"])
        require(
            all(evidence.get(key) == word[key] for key in ("text", "span", "bbox")),
            "inherited_word_binding",
        )
        if "word_pointer" in evidence:
            require(evidence["word_pointer"] == "/words/" + str(index), "inherited_word_pointer")
        if "source_pointer" in evidence:
            require(evidence["source_pointer"] == "/words/" + str(index), "inherited_word_pointer")
        for key, expected in [
            ("word_index", index),
            ("physical_page", native["physical_page"]),
            ("native_sha256", native_hash),
            ("source_pdf_sha256", request["pdf_sha256"]),
        ]:
            if key in evidence:
                require(evidence[key] == expected, "inherited_word_identity")
        if "layout_pointers" in evidence:
            require(
                evidence["layout_pointers"] == old["layout_pointers"], "inherited_layout_pointers"
            )
        if "layout_pointer" in evidence:
            require(
                [evidence["layout_pointer"]] == old["layout_pointers"], "inherited_layout_pointers"
            )
        begin, end = word["span"]
        require(
            type(begin) is int and type(end) is int and 0 <= begin <= end <= len(native["text"]),
            "word_span",
        )
        require(native["text"][begin:end] == word["text"], "word_span_text_mismatch")
        require(bool(old["layout_pointers"]), "original_layout_reference")
        for pointer in old["layout_pointers"]:
            require(
                re.fullmatch(r"/layout_lines/(0|[1-9][0-9]*)/words/(0|[1-9][0-9]*)", pointer)
                is not None,
                "original_layout_reference",
            )
            layout, _ = dereference({"document": native_name, "pointer": pointer})
            require(
                all(layout.get(key) == word[key] for key in ("text", "span", "bbox")),
                "original_layout_binding",
            )
        return {
            "source_address": "sha256:" + native_hash + "#/words/" + str(index),
            "word_pointer": "/words/" + str(index),
            "word_index": index,
            "text": word["text"],
            "span": deepcopy(word["span"]),
            "span_frame": "/text",
            "bbox": deepcopy(word["bbox"]),
            "layout_pointers": list(old["layout_pointers"]),
            "evidence_address": evidence_address,
        }

    def segments(lists: list[list[int]]) -> list[dict[str, Any]]:
        require(bool(lists), "source_segment_missing")
        flat = [i for indices in lists for i in indices]
        require(len(flat) == len(set(flat)), "duplicate_segment_membership")
        result: list[dict[str, Any]] = []
        for indices in lists:
            require(bool(indices), "source_segment_missing")
            words = [anchor(i) for i in indices]
            require(
                all(b == a + 1 for a, b in pairwise(indices)),
                "source_segment_not_contiguous",
            )
            begin, end = words[0]["span"][0], words[-1]["span"][1]
            require(begin <= end, "source_segment_order")
            result.append(
                {
                    "word_indices": list(indices),
                    "word_addresses": [w["source_address"] for w in words],
                    "own_text_span": [begin, end],
                    "span_frame": "/text",
                    "exact_text": native["text"][begin:end],
                }
            )
        return result

    context = request["context"]
    require(context["kind"] in {"caption", "introductory_paragraph"}, "context_kind")
    context_segments = segments(context["segments"])
    context_words = [i for s in context_segments for i in s["word_indices"]]
    cells: list[dict[str, Any]] = []
    originals: dict[str, Any] = {}
    cell_descriptors = descriptor["cells"]
    require(
        len({c["id"] for c in cell_descriptors}) == len(cell_descriptors),
        "duplicate_cell_reference",
    )
    body_words: list[int] = []
    for item in cell_descriptors:
        original, address = dereference(item["record_ref"])
        column = by_column.get(item["column_id"])
        require(
            column is not None and original["column_index"] == column["source_index"],
            "cell_column_reference",
        )
        require(bool(original["word_indices"]), "cell_word_reference")
        for i in original["word_indices"]:
            anchor(i)
        body_words.extend(original["word_indices"])
        originals[item["id"]] = original
        cells.append(
            {
                "descriptor_id": item["id"],
                "row_descriptor_id": item["row_id"],
                "column_id": item["column_id"],
                "source_address": address,
                "record_sha256": record_hash(original),
                "word_indices": list(original["word_indices"]),
                "display_value_inherited": original[item["value_key"]],
                "display_value_is_contiguous_source_quote": False,
                "value_origin": original.get(
                    "value_origin",
                    original.get(
                        "reconstruction_rule",
                        "inherited reconstructed value; joining syntax is derivative",
                    ),
                ),
            }
        )
    require(bool(cells), "cell_grouping_reference")
    rows: list[dict[str, Any]] = []
    grouped: list[str] = []
    for row in descriptor["rows"]:
        original, address = dereference(row["record_ref"])
        ids = row["ordered_cell_ids"]
        grouped += ids
        require(all(i in originals for i in ids), "grouping_cell_reference")
        expected = [originals[i] for i in ids]
        if row["grouping_format"] == "embedded_cells":
            require(original["cells"] == expected, "grouping_binding")
        else:
            require(
                row["grouping_format"] == "ordered_original_ids"
                and original["ordered_cell_ids"] == [c["cell_id"] for c in expected],
                "grouping_binding",
            )
            require(
                all(c["row_id"] == original["row_id"] for c in expected), "grouping_row_conflict"
            )
        require(
            all(c["row_id"] == row["id"] for c in cell_descriptors if c["id"] in ids),
            "grouping_row_conflict",
        )
        rows.append(
            {
                "descriptor_id": row["id"],
                "source_address": address,
                "record_sha256": record_hash(original),
                "ordered_cell_descriptor_ids": list(ids),
                "grouping_status": "inherited exposed-AI proposal, not independent adjudication",
            }
        )
    require(len({r["descriptor_id"] for r in rows}) == len(rows), "duplicate_row_reference")
    require(
        Counter(grouped) == Counter(c["id"] for c in cell_descriptors), "grouping_cell_multiplicity"
    )
    metadata: list[dict[str, Any]] = []
    metadata_words: list[int] = []
    for item in descriptor["metadata"]:
        require(item["kind"] in {"header", "ordinal"}, "metadata_role")
        original, address = dereference(item["record_ref"])
        indices = original.get("word_indices", [original.get("word_index")])
        require(indices == item["word_indices"], "metadata_binding")
        for i in indices:
            anchor(i)
        metadata_words += indices
        metadata.append(
            {
                "kind": item["kind"],
                "source_address": address,
                "record_sha256": record_hash(original),
                "word_indices": list(indices),
            }
        )
    require(
        len(body_words) == len(set(body_words))
        and len(context_words) == len(set(context_words))
        and len(metadata_words) == len(set(metadata_words))
        and set(body_words).isdisjoint(context_words)
        and set(body_words).isdisjoint(metadata_words)
        and set(context_words).isdisjoint(metadata_words),
        "duplicate_ownership_context_body_metadata",
    )

    def assertions(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for ref in refs:
            item, address = dereference(ref)
            require(
                item.get("status") in {"exposed_AI_interpretation", "inherited_proposal"}
                and item.get("attribution") == "Codex AI"
                and item.get("stage")
                in {"new_attachment_interpretation", "inherited_attachment_interpretation"},
                "evidence_reclassification",
            )
            result.append({**deepcopy(item), "source_address": address, "human_reviewed": False})
        return result

    attachment = assertions(request["attachment_assertion_refs"])
    require(bool(attachment), "attachment_evidence_missing")
    require(
        all(a.get("context_segments") == context["segments"] for a in attachment),
        "attachment_source_binding",
    )
    qualifiers: list[dict[str, Any]] = []
    require(
        len({q["kind"] for q in request["qualifiers"]}) == len(request["qualifiers"]),
        "duplicate_qualifier",
    )
    for q in request["qualifiers"]:
        literal = segments(q["segments"])
        kind = q["kind"]
        refs = assertions(q.get("assertion_refs", []))
        if "exact_contiguous_text" in q:
            require(
                len(literal) == 1 and q["exact_contiguous_text"] == literal[0]["exact_text"],
                "contiguous_claim",
            )
        expected_target = TARGETS[profile["name"]].get(kind)
        target = None
        resolution = "unresolved_unsupported_attachment"
        if expected_target is not None:
            require(q["target"] == expected_target, "target_scope:" + kind)
            allowed = set(metadata_words) if kind == "percentage_sign" else set(context_words)
            wanted = {i for s in literal for i in s["word_indices"]}
            if kind == "percentage_sign":
                percentage_index = next(
                    c["source_index"] for c in columns if c["role"] == "percentage"
                )
                allowed = {
                    i
                    for item in descriptor["metadata"]
                    if item["kind"] == "header"
                    for i in item["word_indices"]
                    if native["words"][i]["text"] == "%"
                }
                allowed |= {
                    i
                    for c in cells
                    if by_column[c["column_id"]]["source_index"] == percentage_index
                    and originals[c["descriptor_id"]].get("row_kind") == "printed_header"
                    for i in c["word_indices"]
                }
            require(wanted <= allowed, "qualifier_source_scope:" + kind)
            support = {"kind": kind, "target": q["target"], "segments": q["segments"]}
            if any(support in a.get("supports", []) for a in refs):
                target = {"kind": expected_target, "source_address": descriptor_address}
                if kind in {"count_unit", "percentage_sign"}:
                    role = "count" if kind == "count_unit" else "percentage"
                    column = next(c for c in columns if c["role"] == role)
                    target = {
                        "kind": "column",
                        "column_id": column["id"],
                        "role": role,
                        "source_address": profile_address
                        + "/columns/"
                        + str(columns.index(column)),
                    }
                resolution = "attached_for_inspection_only"
            else:
                resolution = "unresolved_missing_semantic_support"
        display = q.get("display_text", " | ".join(s["exact_text"] for s in literal))
        qualifiers.append(
            {
                "kind": kind,
                "source_segments": literal,
                "display_text": display,
                "display_is_contiguous_source_quote": len(literal) == 1
                and display == literal[0]["exact_text"],
                "literal_evidence_class": "direct_source_bound_literal",
                "target": target,
                "resolution": resolution,
                "applicability": refs,
                "qualification": q.get(
                    "qualification", "AI applicability is not a literal-source fact."
                ),
            }
        )
    dependencies: list[dict[str, Any]] = []
    for dep in request["dependencies"]:
        state = dep["state"]
        require(
            state
            in {
                "unknown",
                "confirmed_none",
                "reported_empty",
                "absent_field",
                "unreviewed_interpretation",
            },
            "dependency_state",
        )
        require(bool(dep["evidence_refs"]), "dependency_evidence_missing")
        refs: list[dict[str, Any]] = []
        for ref in dep["evidence_refs"]:
            item, address = dereference(ref)
            require(
                item.get("status") == state and bool(item.get("attribution")), "dependency_evidence"
            )
            if state == "reported_empty":
                require(item.get("value") == "", "dependency_evidence_empty")
            if state == "confirmed_none":
                require(bool(item.get("statement")), "dependency_evidence_none")
            refs.append(
                {
                    "source_address": address,
                    "record_sha256": record_hash(item),
                    "source_status": state,
                }
            )
        record = {
            "name": dep["name"],
            "state": state,
            "evidence_refs": refs,
            "meaning": dep.get(
                "meaning",
                "Unresolved interpretation is not null source data, zero or confirmed absence.",
            ),
        }
        if state == "reported_empty":
            record["exact_reported_value"] = ""
        dependencies.append(record)
    used = sorted(
        set(
            body_words
            + metadata_words
            + context_words
            + [i for q in qualifiers for s in q["source_segments"] for i in s["word_indices"]]
        )
    )
    return {
        "version": VERSION,
        "representation": "external_attached_noncell_context",
        "created_by": "Codex AI",
        "source": {
            "native_sha256": native_hash,
            "pdf_sha256": request["pdf_sha256"],
            "physical_page": native["physical_page"],
            "width": native["width"],
            "height": native["height"],
            "frame": "original serialized native coordinates; no transform",
        },
        "profile_address": profile_address,
        "columns": deepcopy(columns),
        "receiving_descriptor_address": descriptor_address,
        "table_proposal_reference": {
            "receiving_descriptor_address": descriptor_address,
            "meaning": "Exact supplied inherited row/cell collection; not a canonical "
            "table identity.",
        },
        "context_node": {
            "kind": context["kind"],
            "non_cell": True,
            "source_segments": context_segments,
            "technical_address": "sha256:"
            + record_hash({"native": native_hash, "context": context})
            + "#external_context",
        },
        "original_word_anchors": {str(i): anchor(i) for i in used},
        "cell_references": cells,
        "row_references": rows,
        "documentary_metadata": metadata,
        "attachment_assertions": attachment,
        "qualifiers": qualifiers,
        "dependencies": dependencies,
        "provenance": {
            "cells": "inherited exposed Codex-AI proposal; not re-extracted or "
            "independently adjudicated",
            "attachment": "See each assertion stage; new judgment is not attributed to the "
            "inherited candidate.",
            "execution_authority": request["execution_authority"],
            "lineage": deepcopy(request["lineage"]),
            "owner_personal_source_rechecking": False,
            "production_no_dispatch_changed": False,
        },
        "alternative_universe_complete": False,
        "permissions": dict(PERMISSIONS),
    }


def write_view(view: dict[str, Any], path: str | Path) -> None:
    raw = (json.dumps(view, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def inspection_markdown(view: dict[str, Any]) -> str:
    def escape(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    lines = [
        "# Inspection-only external context view",
        "",
        "Created by Codex AI. Underlying rows/cells are inherited exposed-AI proposals.",
        "Attachment assertions retain their own authorship and creation "
        "stage. Owner authorized this developmental operation, not personal source rechecking.",
        "No normalization, automatic dispatch, scientific acceptance or "
        "benchmark scoring permission. Production no-dispatch is unchanged.",
        "",
        "Context kind: " + view["context_node"]["kind"],
        "",
    ]
    lines += ["> " + escape(s["exact_text"]) for s in view["context_node"]["source_segments"]]
    lines += [
        "",
        "| Qualifier | Exact separate source fragments | Target | Resolution |",
        "| --- | --- | --- | --- |",
    ]
    for q in view["qualifiers"]:
        lines.append(
            "| "
            + " | ".join(
                escape(v)
                for v in [
                    q["kind"],
                    " ; ".join("[" + s["exact_text"] + "]" for s in q["source_segments"]),
                    q["target"] if q["target"] else "unresolved/no edge",
                    q["resolution"],
                ]
            )
            + " |"
        )
    lines += [
        "",
        "Source fragments, display ellipses and inherited joining syntax "
        "are not interchangeable contiguous source quotes.",
        "",
        "Explicit interpretation/dependency states:",
    ]
    lines += [
        "- " + d["name"] + ": " + d["state"] + " — " + d["meaning"] for d in view["dependencies"]
    ]
    lines += [
        "",
        "## Inherited documentary table (no new extraction)",
        "",
        "| " + " | ".join(escape(c["display_label"]) for c in view["columns"]) + " |",
        "| " + " | ".join("---" for _ in view["columns"]) + " |",
    ]
    cells = {c["descriptor_id"]: c for c in view["cell_references"]}
    for row in view["row_references"]:
        ordered = {cells[i]["column_id"]: cells[i] for i in row["ordered_cell_descriptor_ids"]}
        lines.append(
            "| "
            + " | ".join(
                escape(ordered[c["id"]]["display_value_inherited"]) for c in view["columns"]
            )
            + " |"
        )
    lines += [
        "",
        "Headers and ordinals remain separately referenced documentary "
        "metadata, not additional substantive cells.",
        "Unknown meaning does not erase literal cells and does not confer downstream eligibility.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Load supplied bytes and create absent outputs; no transactional-write claim."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    request_path = cast("Path", args.request)
    locations_path = cast("Path", args.locations)
    outputs = [cast("Path", args.output_json), cast("Path", args.output_markdown)]
    try:
        require(outputs[0].resolve() != outputs[1].resolve(), "duplicate_output_path")
        require(not any(path.exists() for path in outputs), "output_exists")
        require(
            not any(
                part.lower() in {"00_external", "01_raw", "99_archive"}
                for path in outputs
                for part in path.resolve().parts
            ),
            "protected_output_storage",
        )
        request = cast("dict[str, Any]", strict_json(request_path.read_bytes()))
        locations = cast("dict[str, Any]", strict_json(locations_path.read_bytes()))
        require(
            set(locations["documents"]) == set(request["documents"]), "document_registry_mismatch"
        )
        paths: dict[str, Path] = {}
        for name, location in locations["documents"].items():
            require(isinstance(location, str), "document_location")
            paths[name] = locations_path.parent / location
        input_paths = {p.resolve() for p in [request_path, locations_path, *paths.values()]}
        require(all(p.resolve() not in input_paths for p in outputs), "output_is_input")
        documents = {name: path.read_bytes() for name, path in paths.items()}
        view = attach_context(request, documents)
        markdown = inspection_markdown(view).encode("utf-8")
        json.dumps(view, ensure_ascii=False, allow_nan=False)
        write_view(view, outputs[0])
        with outputs[1].open("xb") as stream:
            stream.write(markdown)
            stream.flush()
            os.fsync(stream.fileno())
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        UnicodeError,
        RecursionError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(error),
                    "output_paths_present": [str(p) for p in outputs if p.exists()],
                    "transactionally_atomic": False,
                }
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "inspection_view_created",
                "output_json": str(outputs[0]),
                "output_markdown": str(outputs[1]),
                "transactionally_atomic": False,
            }
        )
    )
    return 0
