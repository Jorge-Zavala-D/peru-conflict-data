"""Historical geometry-only native region rules, without vocabulary selection."""

from __future__ import annotations

import itertools
import statistics
from collections import Counter
from typing import Any, cast

from .io import box_union, require

VERSION = "M2R05_SOURCE_NATIVE_REGION_ADMISSION_V001"
RULES = "NATIVE_GEOMETRIC_REGION_RULES_V001"

Json = dict[str, Any]
Admission = tuple[
    list[Json], list[Json], list[Json], list[Json], dict[str, str], dict[str, Json], Json
]


def same_line(first: list[float], second: list[float]) -> bool:
    height = min(first[3] - first[1], second[3] - second[1])
    return (
        min(first[3], second[3]) - max(first[1], second[1]) >= 0.75 * height
        and abs((first[1] + first[3] - second[1] - second[3]) / 2) <= 0.25 * height
    )


def empty_strips(boxes: list[list[float]]) -> list[list[float]]:
    if not boxes:
        return []
    spans = sorted((box[0], box[2]) for box in boxes)
    end = spans[0][1]
    result: list[list[float]] = []
    for start, stop in spans[1:]:
        if start > end:
            result.append([end, start])
        end = max(end, stop)
    return result


def line_bands(words: list[Json]) -> tuple[list[Json], list[Json]]:
    bands: list[list[int]] = []
    ambiguous: list[Json] = []
    for index in sorted(
        range(len(words)),
        key=lambda index: (
            words[index]["bbox"][1],
            words[index]["bbox"][0],
            words[index]["bbox"][3],
            index,
        ),
    ):
        bbox = words[index]["bbox"]
        matches = [
            line for line in bands if all(same_line(bbox, words[other]["bbox"]) for other in line)
        ]
        if len(matches) == 1:
            matches[0].append(index)
        else:
            if len(matches) > 1:
                ambiguous.append(
                    {"word_index": index, "reason": "multiple_pairwise_geometric_line_options"}
                )
            bands.append([index])
    result: list[Json] = []
    for line in bands:
        line.sort(key=lambda index: (words[index]["bbox"][0], index))
        height = statistics.median(
            words[index]["bbox"][3] - words[index]["bbox"][1] for index in line
        )
        runs: list[list[int]] = [[]]
        for index in line:
            if runs[-1] and words[index]["bbox"][0] - words[runs[-1][-1]]["bbox"][2] > 3 * height:
                runs.append([])
            runs[-1].append(index)
        result.append(
            {
                "word_indices": line,
                "bbox": box_union([words[index]["bbox"] for index in line]),
                "median_height": height,
                "runs": runs,
            }
        )
    result.sort(key=lambda line: (line["bbox"][1], line["bbox"][0], line["bbox"][3]))
    for number, line in enumerate(result):
        line["line_band_id"] = f"band-{number:04d}"
    return result, ambiguous


def structural_evidence(
    lines: list[Json], words: list[Json], page_width: float
) -> tuple[str, Json]:
    ids: list[int] = [index for line in lines for index in line["word_indices"]]
    bbox = cast("list[float]", box_union([words[index]["bbox"] for index in ids]))
    multi = [line for line in lines if len(line["runs"]) >= 2]
    height = statistics.median(words[index]["bbox"][3] - words[index]["bbox"][1] for index in ids)
    gutters: list[Json] = []
    for gap in empty_strips(
        [words[index]["bbox"] for line in multi for index in line["word_indices"]]
    ):
        support = [
            line["line_band_id"]
            for line in multi
            if any(
                words[left[-1]]["bbox"][2] <= gap[0] and words[right[0]]["bbox"][0] >= gap[1]
                for left, right in zip(
                    cast("list[list[int]]", line["runs"]),
                    cast("list[list[int]]", line["runs"])[1:],
                    strict=False,
                )
            )
        ]
        if gap[1] - gap[0] >= height and len(support) >= 2:
            gutters.append({"empty_x_strip": gap, "supporting_line_band_ids": support})
    cuts = [sum(gutter["empty_x_strip"]) / 2 for gutter in gutters]
    columns: list[Json] = []
    for left, right in zip([bbox[0], *cuts], [*cuts, bbox[2]], strict=False):
        members = [
            index
            for index in ids
            if left <= words[index]["bbox"][0] < words[index]["bbox"][2] <= right
        ]
        occupied = [
            line for line in lines if any(index in members for index in line["word_indices"])
        ]
        column_bbox = box_union([words[index]["bbox"] for index in members])
        counts = [sum(index in members for index in line["word_indices"]) for line in occupied]
        narrow = bool(
            column_bbox
            and column_bbox[2] - column_bbox[0] <= 0.15 * (bbox[2] - bbox[0])
            and len(occupied) >= 2
            and statistics.median(counts) <= 2
        )
        columns.append(
            {
                "interval": [left, right],
                "word_indices": members,
                "occupied_line_band_ids": [line["line_band_id"] for line in occupied],
                "word_bbox": column_bbox,
                "median_words_per_occupied_band": statistics.median(counts) if counts else None,
                "repeated_narrow_column": narrow,
            }
        )
    broad_flow = bool(
        len(columns) == 2
        and columns[-1]["median_words_per_occupied_band"] is not None
        and columns[-1]["median_words_per_occupied_band"] >= 4
    )
    prose = bool(
        len(lines) >= 2
        and all(len(line["runs"]) == 1 for line in lines)
        and statistics.median(line["bbox"][2] - line["bbox"][0] for line in lines)
        >= 0.45 * page_width
        and statistics.median(len(line["word_indices"]) for line in lines) >= 4
    )
    # shortcut: two-column tables and short lists stay ambiguous until separately revised.
    table = bool(
        len(multi) >= 2
        and len(gutters) >= 2
        and any(column["repeated_narrow_column"] for column in columns)
    )
    spanning = [
        line["line_band_id"]
        for line in lines
        if len(line["runs"]) == 1
        and any(
            line["bbox"][0] < gutter["empty_x_strip"][0]
            and line["bbox"][2] > gutter["empty_x_strip"][1]
            for gutter in gutters
        )
    ]
    classification = (
        "candidate_tabular_region"
        if table
        else "ambiguous_region"
        if len(multi) >= 2
        else "candidate_prose_region"
        if prose
        else "candidate_continuation_or_context"
        if len(lines) == 1
        else "unclassified_or_unprocessed"
    )
    if spanning:
        classification = "ambiguous_region"
    return classification, {
        "line_band_ids": [line["line_band_id"] for line in lines],
        "multi_run_band_ids": [line["line_band_id"] for line in multi],
        "median_word_height": height,
        "persistent_gutters": gutters,
        "columns": columns,
        "broad_two_column_flow": broad_flow,
        "spanning_single_run_band_ids": spanning,
        "prose_necessary_conditions": prose,
        "table_necessary_conditions": table,
        "classification_basis": (
            "geometry only; table-like candidates are not official "
            "table/scientific-object identifications"
        ),
    }


def admit(page: Json) -> Admission:
    """Partition every retained word and preserve competing ownership hypotheses."""
    words: list[Json] = page["words"]
    bands, line_ambiguities = line_bands(words)
    blocks: list[list[Json]] = []
    spatial_splits: list[Json] = []
    for band in bands:
        if not blocks:
            blocks.append([band])
            continue
        previous = blocks[-1]
        bottom = max(line["bbox"][3] for line in previous)
        gap = band["bbox"][1] - bottom
        scale = min(previous[-1]["median_height"], band["median_height"])
        if gap > 1.25 * scale:
            spatial_splits.append(
                {
                    "before_band": previous[-1]["line_band_id"],
                    "after_band": band["line_band_id"],
                    "vertical_gap": gap,
                    "height_scale": scale,
                    "reason": "provisional_spatial_component_boundary_not_documentary_end",
                }
            )
            blocks.append([band])
        else:
            previous.append(band)
    parts: list[tuple[list[Json], str]] = []
    edge_boundaries: list[Json] = []
    for block in blocks:
        structured = [index for index, line in enumerate(block) if len(line["runs"]) >= 2]
        if len(structured) >= 2:
            start, stop = structured[0], structured[-1] + 1
            if start:
                parts.append((block[:start], "edge_context"))
                edge_boundaries.append(
                    {
                        "left_band": block[start - 1]["line_band_id"],
                        "right_band": block[start]["line_band_id"],
                        "kind": "possible_spanning_header_or_adjacent_context",
                    }
                )
            parts.append((block[start:stop], "multi_run_core"))
            if stop < len(block):
                parts.append((block[stop:], "edge_context"))
                edge_boundaries.append(
                    {
                        "left_band": block[stop - 1]["line_band_id"],
                        "right_band": block[stop]["line_band_id"],
                        "kind": "possible_trailing_cell_or_context",
                    }
                )
        else:
            parts.append((block, "whole_spatial_component"))
    overlaps: list[Json] = []
    for first, second in itertools.combinations(range(len(words)), 2):
        left, right = words[first]["bbox"], words[second]["bbox"]
        if min(left[2], right[2]) > max(left[0], right[0]) and min(left[3], right[3]) > max(
            left[1], right[1]
        ):
            overlaps.append(
                {
                    "word_indices": [first, second],
                    "kind": "retained_word_bbox_overlap_not_automatically_shared_ownership",
                }
            )
    overlap_words = {index for overlap in overlaps for index in overlap["word_indices"]}
    regions: list[Json] = []
    for number, (lines, part_role) in enumerate(parts):
        classification, evidence = structural_evidence(lines, words, page["width"])
        ids = sorted(index for line in lines for index in line["word_indices"])
        if any(index in overlap_words for index in ids):
            classification = "ambiguous_region"
            evidence["native_word_box_overlap"] = True
        regions.append(
            {
                "region_id": f"region-{number:04d}",
                "classification": classification,
                "qualification": (
                    "structural_candidate_only"
                    if classification not in ("ambiguous_region", "unclassified_or_unprocessed")
                    else "abstained_or_ambiguous"
                ),
                "word_indices": ids,
                "bbox": box_union([words[index]["bbox"] for index in ids]),
                "part_role": part_role,
                "structural_evidence": evidence,
                "boundary_uncertainty": [
                    "spacing/line-pattern boundaries are provisional, "
                    "not official source-table ends"
                ],
                "ownership_uncertainty": [],
                "source_negative_established": False,
                "semantic_page_completeness": False,
            }
        )
    hypotheses: list[Json] = []
    band_owner = {
        band: region["region_id"]
        for region in regions
        for band in region["structural_evidence"]["line_band_ids"]
    }
    for edge in edge_boundaries:
        affected = [
            region
            for region in regions
            if region["region_id"]
            in (band_owner[edge["left_band"]], band_owner[edge["right_band"]])
        ]
        hypothesis_id = f"hypothesis-{len(hypotheses):04d}"
        hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "classification": "ambiguous_region",
                "region_ids": [region["region_id"] for region in affected],
                "word_indices": sorted(
                    index for region in affected for index in region["word_indices"]
                ),
                "bbox": box_union([region["bbox"] for region in affected]),
                "compatible_gutter_evidence": [],
                "edge_band_evidence": edge,
                "alternatives": [
                    "context_is_spanning_header_or_cell_fragment",
                    "context_is_separate_material",
                ],
                "accepted_exclusive_owner": False,
                "reason": (
                    "single-run edge cannot be assigned semantic ownership from geometry alone"
                ),
            }
        )
        for region in affected:
            region["ownership_uncertainty"].append(hypothesis_id)
    for first_index, first in enumerate(regions):
        for distance in (1, 2):
            if first_index + distance >= len(regions):
                continue
            middle = regions[first_index + 1 : first_index + distance]
            if any(
                region["classification"]
                not in ("candidate_continuation_or_context", "unclassified_or_unprocessed")
                for region in middle
            ):
                continue
            second = regions[first_index + distance]
            left_gutters = first["structural_evidence"]["persistent_gutters"]
            right_gutters = second["structural_evidence"]["persistent_gutters"]
            compatible = [
                {"first_strip": left["empty_x_strip"], "second_strip": right["empty_x_strip"]}
                for left in left_gutters
                for right in right_gutters
                if min(left["empty_x_strip"][1], right["empty_x_strip"][1])
                > max(left["empty_x_strip"][0], right["empty_x_strip"][0])
            ]
            if compatible:
                affected = [first, *middle, second]
                ids = sorted({index for region in affected for index in region["word_indices"]})
                hypothesis_id = f"hypothesis-{len(hypotheses):04d}"
                hypotheses.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "classification": "ambiguous_region",
                        "region_ids": [region["region_id"] for region in affected],
                        "word_indices": ids,
                        "bbox": box_union([region["bbox"] for region in affected]),
                        "compatible_gutter_evidence": compatible,
                        "alternatives": [
                            "same_documentary_structure_across_blank_band_or_context",
                            "neighboring_independent_aligned_structures",
                        ],
                        "accepted_exclusive_owner": False,
                        "reason": (
                            "alignment and spacing alone cannot establish continuation or closure"
                        ),
                    }
                )
                for region in affected:
                    region["boundary_uncertainty"].append(hypothesis_id)
                    region["ownership_uncertainty"].append(hypothesis_id)
    line_uncertain = {ambiguity["word_index"] for ambiguity in line_ambiguities}
    for region in regions:
        if any(index in line_uncertain for index in region["word_indices"]):
            region["ownership_uncertainty"].append("multiple_native_line_options")
    require(
        Counter(index for region in regions for index in region["word_indices"])
        == Counter(range(len(words))),
        "nonexclusive_or_incomplete_accounting_partition",
    )
    coverage: list[Json] = []
    accepted: dict[str, str] = {}
    unresolved: dict[str, Json] = {}
    for region in regions:
        for index in region["word_indices"]:
            competing = [
                hypothesis["hypothesis_id"]
                for hypothesis in hypotheses
                if index in hypothesis["word_indices"]
            ]
            uncertain = (
                region["classification"] in ("ambiguous_region", "unclassified_or_unprocessed")
                or bool(region["ownership_uncertainty"])
                or bool(competing)
                or index in overlap_words
            )
            owner = None if uncertain else region["region_id"]
            if owner is not None:
                accepted[str(index)] = owner
            if uncertain:
                unresolved[str(index)] = {
                    "accounting_region_id": region["region_id"],
                    "competing_hypotheses": competing,
                    "classification_uncertain": region["classification"]
                    in ("ambiguous_region", "unclassified_or_unprocessed"),
                    "retained_bbox_overlap": index in overlap_words,
                    "ownership_uncertainty": region["ownership_uncertainty"],
                }
            coverage.append(
                {
                    "word_index": index,
                    "accounting_region_id": region["region_id"],
                    "accepted_region_owner": owner,
                    "disposition": (
                        "ambiguous_region_membership"
                        if competing
                        or region["ownership_uncertainty"]
                        or region["classification"] == "ambiguous_region"
                        or index in overlap_words
                        else "unclassified_context"
                        if region["classification"] == "unclassified_or_unprocessed"
                        else "accepted_candidate_region"
                    ),
                    "competing_hypotheses": competing,
                }
            )
    coverage.sort(key=lambda item: item["word_index"])
    return (
        regions,
        bands,
        hypotheses,
        coverage,
        accepted,
        unresolved,
        {
            "boundary_hypotheses": hypotheses,
            "edge_context_boundary_uncertainties": edge_boundaries,
            "spatial_splits": spatial_splits,
            "native_word_box_overlaps": overlaps,
            "line_band_ambiguities": line_ambiguities,
            "unresolved_overlap_map": unresolved,
        },
    )
