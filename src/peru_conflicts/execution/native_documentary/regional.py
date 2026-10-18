"""Portable known three-column regional adapter with explicit reference comparison."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

VERSION = "M2R05_DEVELOPMENTAL_NATIVE_ROW_ADAPTER_V002"
FRAME = "retained_native_layout_words_v002"
REPRESENTATION = "REGIONAL_NATIVE_WORD_TABLE_V002"
LABELS = ["Región", "Total", "%"]
RULES: dict[str, Any] = {
    "vertical_overlap_min": 0.75,
    "center_delta_max": 0.25,
    "header_tokens": LABELS,
    "label_joiner": " ",
    "scan_policy": "stop_at_first_unqualified_neighbor",
}


def compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ab, bb = a["bbox"], b["bbox"]
    h = min(ab[3] - ab[1], bb[3] - bb[1])
    return (
        max(0, min(ab[3], bb[3]) - max(ab[1], bb[1])) >= 0.75 * h
        and abs((ab[1] + ab[3] - bb[1] - bb[3]) / 2) <= 0.25 * h
    )


def bounds(words: list[dict[str, Any]]) -> list[float]:
    return [
        min(w["bbox"][0] for w in words),
        min(w["bbox"][1] for w in words),
        max(w["bbox"][2] for w in words),
        max(w["bbox"][3] for w in words),
    ]


def components(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending = set(range(len(words)))
    result: list[dict[str, Any]] = []
    while pending:
        seed = min(pending)
        pending.remove(seed)
        connected, queue = [seed], [seed]
        while queue:
            current = queue.pop()
            neighbors = [i for i in sorted(pending) if compatible(words[current], words[i])]
            pending.difference_update(neighbors)
            connected.extend(neighbors)
            queue.extend(neighbors)
        tokens = sorted(
            (words[i] for i in connected), key=lambda w: (w["bbox"][0], w["word_index"])
        )
        result.append(
            {
                "words": tokens,
                "pairwise_qualified": all(compatible(a, b) for a in tokens for b in tokens),
                "bbox": bounds(tokens),
            }
        )
    return sorted(result, key=lambda c: (c["bbox"][1], c["bbox"][0]))


def cell(
    row_id: str,
    column: int,
    words: list[dict[str, Any]],
    identity: dict[str, Any],
) -> dict[str, Any]:
    value = " ".join(w["text"] for w in words)
    return {
        "cell_id": f"{row_id}:c{column}",
        "column_index": column,
        "value": value,
        "type": "string",
        "typed_value_json": json.dumps(value, ensure_ascii=False),
        "reconstruction_rule": "join original words with one U+0020"
        if len(words) > 1
        else "original single word",
        "raw_label_typography_claimed": False,
        "word_indices": [w["word_index"] for w in words],
        "words": words,
        "bbox": bounds(words),
        "frame": FRAME,
        "source_identity": identity,
        "qualification": "source_word_union_not_authoritative_PDF_cell_boundary",
    }


def adapt_page(
    page: dict[str, Any],
    words: list[dict[str, Any]],
    spec: dict[str, Any],
    source: dict[str, Any],
    *,
    reference_text: str | None = None,
) -> dict[str, Any]:
    """Reconstruct only qualified rows; reference text affects the comparison flag alone."""
    identity = {
        "pdf_sha256": source["pdf_sha256"],
        "report_number": source["report_number"],
        "physical_page": spec["physical_page"],
        "native_page_sha256": spec["layout_sha256"],
    }
    groups = components(words)
    for n, group in enumerate(groups):
        group["component_id"] = f"p{spec['physical_page']:03d}:component:{n:04d}"
    headers = [
        g
        for g in groups
        if g["pairwise_qualified"] and [w["text"] for w in g["words"]] == RULES["header_tokens"]
    ]
    coverage = {w["word_index"]: "unprocessed_header_unavailable" for w in words}
    result: dict[str, Any] = {
        "physical_page": spec["physical_page"],
        "source_identity": identity,
        "frame": {
            "id": FRAME,
            "width": page["width"],
            "height": page["height"],
            "units": "serialized native coordinate values",
            "PDF_or_image_equivalence": False,
        },
        "span_frame": "/text",
        "reference_text_identical_to_joined_word_text": page["text"] == reference_text
        if reference_text is not None
        else None,
        "header_candidate_count": len(headers),
        "header": None,
        "rows": [],
        "unresolved_components": [],
        "components": [],
        "continuation": None,
        "status": "header_unavailable",
        "table_completeness_established": False,
    }
    if len(headers) == 1:
        header = headers[0]
        header_id = f"p{spec['physical_page']:03d}:header"
        result["header"] = {
            "header_id": header_id,
            "cells": [cell(header_id, i, [w], identity) for i, w in enumerate(header["words"])],
            "bbox": header["bbox"],
            "frame": FRAME,
        }
        centers = [(w["bbox"][0] + w["bbox"][2]) / 2 for w in header["words"]]
        boundaries = [(centers[0] + centers[1]) / 2, (centers[1] + centers[2]) / 2]
        result["native_column_boundaries"] = boundaries
        header_position = groups.index(header)
        for group in groups[:header_position]:
            for w in group["words"]:
                coverage[w["word_index"]] = "outside_target_before_header"
        for w in header["words"]:
            coverage[w["word_index"]] = "printed_header"
        stopped = False
        for group in groups[header_position + 1 :]:
            if stopped:
                for w in group["words"]:
                    coverage[w["word_index"]] = "unprocessed_after_first_stop"
                continue
            columns: list[list[dict[str, Any]]] = [[], [], []]
            crossed = False
            for w in group["words"]:
                x0, _, x1, _ = w["bbox"]
                if any(x0 < b < x1 for b in boundaries):
                    crossed = True
                col = (
                    0
                    if x1 <= boundaries[0]
                    else 1
                    if x0 >= boundaries[0] and x1 <= boundaries[1]
                    else 2
                )
                columns[col].append(w)
            label, count, percent = columns
            numeric_label = any(
                re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?%?\.?", w["text"]) for w in label
            )
            complete = (
                not crossed
                and label
                and not numeric_label
                and any(ch.isalpha() for w in label for ch in w["text"])
                and len(count) == 1
                and len(percent) == 1
                and re.fullmatch(r"[0-9]+", count[0]["text"])
                and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", percent[0]["text"])
            )
            if not group["pairwise_qualified"] or not complete:
                reason = (
                    "pairwise_vertical_qualification_failed"
                    if not group["pairwise_qualified"]
                    else "not_a_complete_three_column_row"
                )
                result["unresolved_components"].append(
                    group
                    | {
                        "reason": reason,
                        "status": "unresolved",
                        "physical_page": spec["physical_page"],
                        "source_identity": identity,
                        "frame": FRAME,
                        "relative_to_last_accepted_row": {
                            "last_row_id": result["rows"][-1]["row_id"] if result["rows"] else None,
                            "native_vertical_gap": group["bbox"][1] - result["rows"][-1]["bbox"][3]
                            if result["rows"]
                            else None,
                        },
                        "footer_classification": "not_deterministically_established",
                        "table_end_proven": False,
                    }
                )
                for w in group["words"]:
                    coverage[w["word_index"]] = "unresolved_first_neighbor"
                stopped = True
                continue
            row_id = (
                f"regional:p{spec['physical_page']:03d}:"
                f"w{min(w['word_index'] for w in group['words']):05d}:v002"
            )
            row = {
                "row_id": row_id,
                "physical_page": spec["physical_page"],
                "source_identity": identity,
                "role": "primary",
                "row_kind": "published_total"
                if " ".join(w["text"] for w in label) == "TOTAL"
                else "regional_category",
                "processing_status": "individually_qualified",
                "bbox": group["bbox"],
                "frame": FRAME,
                "cells": [cell(row_id, i, tokens, identity) for i, tokens in enumerate(columns)],
                "rule_identity": VERSION,
                "original_table_array_row_binding": None,
            }
            result["rows"].append(row)
            for w in group["words"]:
                coverage[w["word_index"]] = "accepted_source_row"
        result["status"] = (
            "populated_partial_source_evidence" if result["rows"] else "no_qualified_rows"
        )
    result["components"] = [
        {
            "component_id": g["component_id"],
            "bbox": g["bbox"],
            "word_indices": [w["word_index"] for w in g["words"]],
            "pairwise_qualified": g["pairwise_qualified"],
            "coverage_states": sorted({coverage[w["word_index"]] for w in g["words"]}),
        }
        for g in groups
    ]
    result["word_coverage"] = [
        {"word_index": i, "source_pointer": f"/words/{i}", "status": coverage[i]}
        for i in range(len(words))
    ]
    return result


def scoped_regional(view: Any, contract: dict[str, Any], output: Path) -> dict[str, Any]:
    """Adapt an admitted region; actual generation needs the separate run scope."""
    if contract["mode"] == "actual":
        scope = contract.get("run_scope", {})
        if "regional" not in scope.get("allowed_adapters", []) or "compose" not in scope.get(
            "allowed_operations", []
        ):
            raise ValueError("regional_generation_not_authorized")
    words: list[dict[str, Any]] = [
        {k: copy.deepcopy(w[k]) for k in ("text", "span", "bbox")}
        | {
            "word_index": j,
            "source_pointer": f"/words/{j}",
            "span_frame": "/text",
            "layout_line_index": j,
            "layout_word_position": 0,
            "layout_pointer": f"/layout_lines/{j}/words/0",
        }
        for j, w in enumerate(view.words)
    ]
    spec = {
        "physical_page": view.page["physical_page"],
        "layout_sha256": contract["input"]["sha256"],
    }
    raw = adapt_page(view.page, words, spec, contract["source"], reference_text=view.page["text"])
    rows: list[dict[str, Any]] = []
    for row in raw["rows"]:
        cells: list[dict[str, Any]] = []
        for c in row["cells"]:
            ids = [view.ids[i] for i in c["word_indices"]]
            cells.append(
                {
                    "field": [
                        "region_text_original",
                        "count_text_original",
                        "percentage_text_original",
                    ][c["column_index"]],
                    "column_index": c["column_index"],
                    "status": "processed",
                    "value": c["value"],
                    "typed_value_json": c["typed_value_json"],
                    "word_indices": ids,
                    "line_word_indices": [ids],
                    "bbox": c["bbox"],
                }
            )
        rows.append(
            {
                "row_id": f"regional:{view.region['region_id']}:{len(rows) + 1}",
                "role": "aggregate_measure",
                "row_kind": row["row_kind"],
                "status": "accepted",
                "cells": cells,
                "ordinal": None,
            }
        )
    header = raw["header"]
    header_ids = [view.ids[c["word_indices"][0]] for c in header["cells"]] if header else []
    return {
        "adapter": "regional",
        "region_id": view.region["region_id"],
        "status": "processed" if rows and not raw["unresolved_components"] else "partial",
        "header": {"labels": LABELS, "word_indices": header_ids},
        "rows": rows,
        "unresolved": [{"reason": x["reason"]} for x in raw["unresolved_components"]],
        "view": view.record,
    }
