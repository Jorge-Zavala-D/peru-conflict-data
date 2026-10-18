"""Portable known priority adapter; supplied region membership is never expanded."""

from __future__ import annotations

import itertools
import json
import re
import statistics
from collections import Counter
from typing import Any, cast

VERSION = "M2R05_DEVELOPMENTAL_PRIORITY_WORD_ADAPTER_V001"
FRAME = "retained_native_page_words_priority_v001"
LABELS = ["N.°", "Lugar", "Caso", "Situación"]


def union(boxes: list[list[float]]) -> list[float] | None:
    return (
        [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]
        if boxes
        else None
    )


def same_line(a: list[float], b: list[float]) -> bool:
    ah, bh = a[3] - a[1], b[3] - b[1]
    return min(a[3], b[3]) - max(a[1], b[1]) >= 0.75 * min(ah, bh) and abs(
        (a[1] + a[3] - b[1] - b[3]) / 2
    ) <= 0.25 * min(ah, bh)


def gaps(intervals: list[tuple[float, float]], lo: float, hi: float) -> list[list[float]]:
    occupied = sorted((max(a, lo), min(b, hi)) for a, b in intervals if a < hi and b > lo)
    end = lo
    result: list[list[float]] = []
    for a, b in occupied:
        if a > end:
            result.append([end, a])
        end = max(end, b)
    if end < hi:
        result.append([end, hi])
    return result


def unique_widest(items: list[list[float]]) -> list[float] | None:
    ordered = sorted(items, key=lambda x: x[1] - x[0], reverse=True)
    if not ordered or (
        len(ordered) > 1
        and abs((ordered[0][1] - ordered[0][0]) - (ordered[1][1] - ordered[1][0])) <= 1e-6
    ):
        return None
    return ordered[0]


def reconstruct(
    indices: list[int],
    words: list[dict[str, Any]],
) -> tuple[str | None, list[list[int]], str | None]:
    lines: list[list[int]] = []
    for i in sorted(indices, key=lambda k: (words[k]["bbox"][1], words[k]["bbox"][0], k)):
        box = words[i]["bbox"]
        matching = [line for line in lines if all(same_line(box, words[j]["bbox"]) for j in line)]
        if len(matching) > 1:
            return None, [], "ambiguous_line_membership"
        if matching:
            matching[0].append(i)
        else:
            if any(
                min(box[3], words[j]["bbox"][3]) > max(box[1], words[j]["bbox"][1])
                for line in lines
                for j in line
            ):
                return None, [], "overlapping_incompatible_lines"
            lines.append([i])
    lines.sort(key=lambda line: min(words[j]["bbox"][1] for j in line))
    for line in lines:
        line.sort(key=lambda j: (words[j]["bbox"][0], j))
        if any(words[a]["bbox"][2] > words[b]["bbox"][0] for a, b in itertools.pairwise(line)):
            return None, lines, "overlapping_words"
    return "\n".join(" ".join(words[i]["text"] for i in line) for line in lines), lines, None


def discover(
    d: dict[str, Any],
    contract: dict[str, Any],
    evidence: list[dict[str, Any]],
    context: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the known body rules with explicit whole-page geometry-only context."""
    words: list[dict[str, Any]] = d["words"]
    issues: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = [
        {"word_index": i, "disposition": "unprocessed_or_unresolved_context", "owner": None}
        for i in range(len(words))
    ]
    candidate: dict[str, Any] = {
        "version": VERSION,
        "authorship": "Codex AI; exposed development-seen source; no Jorge PI source-first review",
        "source": contract["source"],
        "input_identity": contract["input"],
        "frame": {
            "frame_id": FRAME,
            "dimensions": [d["width"], d["height"]],
            "meaning": "exact retained JSON word bbox values; no PDF-point/image equivalence",
            "span_frame": "this native JSON /text, NOT separate reference txt",
        },
        "status": "unresolved",
        "header": None,
        "ordinal_candidates": [],
        "rows": [],
        "unresolved": issues,
        "canonical_objects_created": False,
        "source_negative_inventory": False,
        "scientific_status": "documentary-only developmental derivative; NOT_READY unchanged",
    }

    def disposition(indices: list[int], state: str, owner: str | None = None) -> None:
        for i in indices:
            coverage[i].update(disposition=state, owner=owner)

    choices = [[i for i, w in enumerate(words) if w["text"] == label] for label in LABELS]
    headers: list[list[int]] = []
    for ids in itertools.product(*choices):
        boxes = [words[i]["bbox"] for i in ids]
        if (
            len(set(ids)) == 4
            and all(boxes[k][2] < boxes[k + 1][0] for k in range(3))
            and all(same_line(a, b) for a, b in itertools.combinations(boxes, 2))
        ):
            headers.append(list(ids))
    if len(headers) != 1:
        issues.append({"kind": "header_not_unique", "candidate_count": len(headers)})
        return candidate, coverage
    header_ids = headers[0]
    hb = union([words[i]["bbox"] for i in header_ids])
    assert hb is not None
    top = hb[3]
    candidate["header"] = {
        "labels": LABELS,
        "word_indices": header_ids,
        "bbox": hb,
        "qualification": "unique pairwise same-line ordered four-column heading",
    }
    disposition(header_ids, "qualified_printed_header", "header")
    for i, w in enumerate(words):
        if w["bbox"][3] < hb[1]:
            disposition([i], "outside_target_before_header")
    ob = words[header_ids[0]]["bbox"]
    ordinals = [
        i
        for i, w in enumerate(words)
        if w["bbox"][1] > top
        and re.fullmatch(r"[1-9][0-9]*\.", w["text"])
        and ob[0] <= (w["bbox"][0] + w["bbox"][2]) / 2 <= ob[2]
    ]
    ordinals.sort(key=lambda i: (words[i]["bbox"][1], words[i]["bbox"][0], i))
    candidate["ordinal_candidates"] = [evidence[i] for i in ordinals]
    disposition(ordinals, "qualified_documentary_ordinal")
    if not ordinals:
        issues.append({"kind": "no_qualified_ordinals"})
        return candidate, coverage
    last = words[ordinals[-1]]["bbox"]
    height = statistics.median(
        w["bbox"][3] - w["bbox"][1] for w in words if top < w["bbox"][1] <= last[3]
    )
    page_gaps = gaps(
        [(w["bbox"][1], w["bbox"][3]) for w in context if w["bbox"][1] > top],
        top,
        d["height"],
    )
    stops = [gap for gap in page_gaps if gap[0] >= last[3] and gap[1] - gap[0] >= height]
    stop = stops[0] if stops else None
    bottom = sum(stop) / 2 if stop else None
    candidate["table_region"] = {
        "bbox": [0, top, d["width"], bottom] if bottom else None,
        "after_last_ordinal_gap": stop,
        "height_reference": height,
        "boundary_method": "first whole-page vertical whitespace >= median body word height "
        "after last ordinal",
    }
    if bottom is None:
        issues.append({"kind": "unqualified_table_bottom"})
    body = [
        i
        for i, w in enumerate(words)
        if w["bbox"][1] >= top and (bottom is None or w["bbox"][3] <= bottom)
    ]
    for i, w in enumerate(words):
        if bottom is not None and w["bbox"][1] > bottom:
            disposition([i], "outside_target_after_table")
    centers = [sum(words[i]["bbox"][::2]) / 2 for i in header_ids]
    col_gaps = [
        unique_widest(
            gaps(
                [(words[i]["bbox"][0], words[i]["bbox"][2]) for i in body + header_ids],
                a,
                b,
            )
        )
        for a, b in itertools.pairwise(centers)
    ]
    cuts = [sum(g) / 2 if g else None for g in col_gaps]
    candidate["columns"] = {
        "labels": LABELS,
        "empty_strip_evidence": col_gaps,
        "cuts": cuts,
        "method": "unique widest empty x strip between consecutive heading centers over "
        "full body/header word projection",
    }
    if any(c is None for c in cuts):
        issues.append({"kind": "unqualified_column_boundary"})
    if bottom is not None and all(c is not None for c in cuts):
        # shortcut: inspect four word heights; broader unanchored discovery needs a new version.
        neighbor = [
            i
            for i, w in enumerate(context)
            if bottom < w["bbox"][1] < bottom + 4 * height
            and w["bbox"][3] - w["bbox"][1] <= 1.25 * height
        ]
        ranges = list(zip([0, *cuts], [*cuts, d["width"]], strict=False))
        if all(
            any(left <= context[i]["bbox"][0] < context[i]["bbox"][2] <= right for i in neighbor)
            for left, right in ranges[1:]
        ):
            issues.append(
                {
                    "kind": "possible_unanchored_continuation_after_stop",
                    "context_word_indices": neighbor,
                }
            )
    rowgaps: list[list[float] | None] = []
    for first, second in itertools.pairwise(ordinals):
        a, b = words[first]["bbox"][3], words[second]["bbox"][1]
        gap = (
            unique_widest(
                gaps(
                    [(words[i]["bbox"][1], words[i]["bbox"][3]) for i in body],
                    a,
                    b,
                )
            )
            if a < b
            else None
        )
        rowgaps.append(gap)
        if gap is None:
            issues.append(
                {"kind": "ambiguous_row_boundary", "ordinal_word_indices": [first, second]}
            )
    boundaries = [top] + [sum(g) / 2 if g else None for g in rowgaps] + [bottom]
    duplicates = Counter(words[i]["text"] for i in ordinals)
    used = set(header_ids + ordinals)
    for n, ordinal_index in enumerate(ordinals):
        word = words[ordinal_index]
        row_id = f"p{contract['input']['physical_page']:03d}:ordinal-word-{ordinal_index}"
        row: dict[str, Any] = {
            "row_id": row_id,
            "role": "primary",
            "source_unit": "priority_alert_documentary_observation",
            "ordinal": evidence[ordinal_index],
            "status": "partial",
            "row_region": [0, boundaries[n], d["width"], boundaries[n + 1]],
            "boundary_gap_before": rowgaps[n - 1] if n else None,
            "boundary_gap_after": rowgaps[n] if n < len(rowgaps) else stop,
            "cells": [],
            "issues": [],
        }
        coverage[ordinal_index]["owner"] = row_id
        qualified = (
            boundaries[n] is not None
            and boundaries[n + 1] is not None
            and all(c is not None for c in cuts)
        )
        if duplicates[word["text"]] > 1:
            row["issues"].append("duplicate_printed_ordinal")
        if not qualified:
            row["issues"].append("unqualified_row_or_column_boundary")
        ranges = (
            list(zip([0, *cuts], [*cuts, d["width"]], strict=False))
            if all(c is not None for c in cuts)
            else []
        )
        for col, label in enumerate(LABELS[1:], 1):
            selected: list[int] = []
            ambiguous: list[int] = []
            if qualified:
                lo, hi = boundaries[n : n + 2]
                left, right = ranges[col]
                for i in body:
                    if i in ordinals:
                        continue
                    box = words[i]["bbox"]
                    if box[0] < right and box[2] > left and box[1] < hi and box[3] > lo:
                        if left <= box[0] < box[2] <= right and lo <= box[1] < box[3] <= hi:
                            selected.append(i)
                        else:
                            ambiguous.append(i)
            value, lines, error = reconstruct(selected, words)
            status = (
                "processed"
                if selected and not error and not ambiguous
                else "unavailable_no_qualified_words"
                if not selected and not ambiguous
                else "ambiguous_ownership"
            )
            if col == 3 and len(lines) > 1:
                status, error = (
                    "ambiguous_ownership",
                    "multiple_status_lines_without_unique_ordinal_ownership",
                )
            cell: dict[str, Any] = {
                "column_index": col,
                "printed_label": label,
                "field": ["lugar_text_original", "caso_text_original", "situacion_text_original"][
                    col - 1
                ],
                "status": status,
                "value": value if status == "processed" else None,
                "reconstruction_if_unqualified": value if status != "processed" else None,
                "typed_value_json": json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if status == "processed"
                else None,
                "word_indices": [i for line in lines for i in line] if lines else selected,
                "line_word_indices": lines,
                "bbox": union([words[i]["bbox"] for i in selected]),
                "frame": FRAME,
                "ambiguous_word_indices": ambiguous,
                "error": error,
                "value_origin": "geometry-ordered native tokens; inserted U+0020 and U+000A "
                "are derivative syntax",
            }
            if any(i in used for i in selected):
                cell["status"] = "ambiguous_ownership"
                row["issues"].append("conflicting_word_membership")
            disposition(
                selected,
                "accepted_documentary_cell"
                if cell["status"] == "processed"
                else "ambiguous_row_or_cell_boundary",
                f"{row_id}:column-{col}",
            )
            disposition(ambiguous, "ambiguous_row_or_cell_boundary", row_id)
            used.update(selected + ambiguous)
            row["cells"].append(cell)
        if all(c["status"] == "processed" for c in row["cells"]) and not row["issues"]:
            row["status"] = "accepted"
        row["bbox"] = union([word["bbox"]] + [c["bbox"] for c in row["cells"] if c["bbox"]])
        candidate["rows"].append(row)
    for i in body:
        if i not in used:
            disposition([i], "unassigned_word_within_candidate_table")
    unassigned = [
        c["word_index"]
        for c in coverage
        if c["disposition"]
        in (
            "unassigned_word_within_candidate_table",
            "ambiguous_row_or_cell_boundary",
        )
    ]
    if unassigned:
        issues.append({"kind": "unassigned_or_ambiguous_body_words", "word_indices": unassigned})
    candidate["status"] = (
        "processed"
        if all(r["status"] == "accepted" for r in candidate["rows"]) and not issues
        else "partial"
    )
    return candidate, coverage


def scoped_priority(view: Any, contract: dict[str, Any]) -> dict[str, Any]:
    candidate, _ = discover(
        {"words": view.words, "width": view.page["width"], "height": view.page["height"]},
        {"source": contract["source"], "input": contract["input"]},
        view.evidence,
        view.context,
    )

    def remap(obj: Any) -> Any:
        if isinstance(obj, list):
            return [remap(x) for x in cast(list[Any], obj)]
        if not isinstance(obj, dict):
            return obj
        out: dict[str, Any] = {}
        for k, v in cast(dict[str, Any], obj).items():
            if k in ("word_indices", "ambiguous_word_indices", "ordinal_word_indices"):
                out[k] = [view.ids[i] for i in v]
            elif k == "line_word_indices":
                out[k] = [[view.ids[i] for i in line] for line in v]
            else:
                out[k] = remap(v)
        return out

    candidate = remap(candidate)
    view.record["boundary_context_access"] = {
        "policy": "REGION_GEOMETRY_STOP_CONTEXT_V001",
        "original_native_sha256": contract["input"]["sha256"],
        "geometry_word_pointers": [f"/words/{i}/bbox" for i in range(len(view.context))],
        "text_access": False,
        "uses": ["whole-page whitespace stop", "four-height neighbor guard"],
        "reported_stop": candidate.get("table_region"),
    }
    for row in candidate["rows"]:
        row["row_id"] = (
            f"p{contract['input']['physical_page']:03d}:ordinal-word-{row['ordinal']['word_index']}"
        )
    return {
        "adapter": "priority",
        "region_id": view.region["region_id"],
        "status": candidate["status"],
        "header": candidate["header"],
        "rows": candidate["rows"],
        "unresolved": candidate["unresolved"],
        "details": {
            "columns": candidate.get("columns"),
            "table_region": candidate.get("table_region"),
        },
        "view": view.record,
    }
