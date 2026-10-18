"""Private region-to-known-adapter composition. No admission detector is imported."""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from . import io, priority, regional
from .io import FRAME, load_native, pin, read, require, write
from .io import box_union as union
from .priority import scoped_priority
from .regional import scoped_regional

VERSION = "SOURCE_NATIVE_DOCUMENTARY_PIPELINE_V001"
GEOMETRY_PREDICATES = {
    "version": "REGION_PRE_DISPATCH_GEOMETRY_V002",
    "positive_area_overlap": "min(ax1,bx1)>max(ax0,bx0) AND min(ay1,by1)>max(ay0,by0)",
    "column_membership": "lo <= x0 < x1 <= hi",
    "membership_and_order": "exact multiplicity/no duplicates; separately supplied line/x sequence",
    "spanning": "single supplied run with source-word-union x0<gutter_lo AND x1>gutter_hi",
    "scope": "otherwise dispatch-eligible admitted memberships only",
    "normalization": "none; no epsilon, ratio, snapping, regrouping or threshold changes",
}
CONTEXT_POLICY = {
    "version": "REGION_GEOMETRY_STOP_CONTEXT_V001",
    "access": "original word indices and rectangles only; no off-region text/spans",
    "uses": [
        "priority whole-page whitespace stop",
        "priority immediate four-height unanchored continuation guard",
        "cross-boundary overlap abstention",
    ],
    "cannot_supply": ["header tokens", "ordinals", "cell values", "accepted membership"],
    "thresholds": "unchanged priority V001; no tuning",
}


def module(name: str) -> Any:
    return {"io": io, "priority": priority, "regional": regional}[name]


def pinned(spec: dict[str, Any]) -> dict[str, Any]:
    require(pin(spec["path"])["sha256"] == spec["sha256"], "pinned_identity_mismatch")
    if "size_bytes" in spec:
        require(pin(spec["path"])["size_bytes"] == spec["size_bytes"], "pinned_size_mismatch")
    return read(spec["path"])


def registry() -> dict[str, Any]:
    return {
        "version": "REGION_KNOWN_LAYOUT_REGISTRY_V001",
        "priority": {
            "headings": ["N.°", "Lugar", "Caso", "Situación"],
            "implementation": "PRIORITY_GEOMETRY_RULES_V001",
        },
        "regional": {
            "headings": ["Región", "Total", "%"],
            "implementation": "NATIVE_REGIONAL_ADAPTER_V002",
        },
        "unknown_or_competing": "no_dispatch",
    }


def validate_addendum(
    contract: dict[str, Any], candidate: dict[str, Any], page: dict[str, Any]
) -> None:
    """Import audit lineage without borrowing its pass counts as source evidence."""
    if "validation" not in contract:
        require("addendum" not in contract, "addendum_without_validation")
        return
    audit = pinned(contract["validation"])
    require(
        audit["candidate"]["sha256"] == contract["admission"]["sha256"], "audit_candidate_mismatch"
    )
    require(audit["failed_checks"] == len(audit["failures"]), "inconsistent_audit")
    if not audit["failures"]:
        return
    require(contract.get("addendum") is not None, "missing_ordering_addendum")
    add = pinned(contract["addendum"])
    require(
        add["first_validation"]["sha256"] == contract["validation"]["sha256"]
        and add["candidate"]["sha256"] == contract["admission"]["sha256"],
        "unmatched_addendum",
    )
    require(
        add["first_failures"] == audit["failures"]
        and add["failed_checks"] == 0
        and not add.get("failures", [])
        and add["no_generation_or_boundary_regrouping"],
        "unqualified_addendum",
    )
    require(
        candidate["native_input"]["sha256"] == contract["input"]["sha256"],
        "addendum_native_mismatch",
    )
    regions = {r["region_id"]: r for r in candidate["regions"]}
    bands = {b["line_band_id"]: b for b in candidate["line_bands"]}
    for failure in audit["failures"]:
        # The importer supports this predicate revision, not arbitrary failed audits.
        require(failure["check"] == "supplied_column_membership", "unrelated_audit_failure")
        require(failure["address"] in regions, "audit_unknown_region")
        region = regions[failure["address"]]
        sequence = [
            i
            for b in region["structural_evidence"]["line_band_ids"]
            for i in bands[b]["word_indices"]
        ]
        for col in region["structural_evidence"]["columns"]:
            lo, hi = col["interval"]
            expected = [
                i
                for i in region["word_indices"]
                if lo <= page["words"][i]["bbox"][0] < page["words"][i]["bbox"][2] <= hi
            ]
            geometric = [i for i in sequence if i in expected]
            require(
                Counter(col["word_indices"]) == Counter(expected)
                and len(col["word_indices"]) == len(set(col["word_indices"]))
                and col["word_indices"] == geometric,
                "superseded_column_predicate_still_fails",
            )


class RegionView:
    """Original evidence plus local adapter ordinals; never a replacement native file."""

    def __init__(
        self,
        region: dict[str, Any],
        page: dict[str, Any],
        evidence: list[dict[str, Any]],
        candidate: dict[str, Any],
        contract: dict[str, Any],
    ) -> None:
        self.region = region
        self.ids: list[int] = list(region["word_indices"])
        self.page = page
        self.original_evidence = evidence
        self.local_to_original = self.ids
        self.words = [copy.deepcopy(page["words"][i]) for i in self.ids]
        self.evidence: list[dict[str, Any]] = []
        for i in self.ids:
            e: dict[str, Any] = copy.deepcopy(evidence[i])
            e["word_pointer"] = f"/words/{i}"
            e["source_pdf_sha256"] = contract["source"]["pdf_sha256"]
            e["frame"] = FRAME
            self.evidence.append(e)
        bands = {b["line_band_id"]: b for b in candidate["line_bands"]}
        self.geometric_order = [
            i
            for b in region["structural_evidence"]["line_band_ids"]
            for i in bands[b]["word_indices"]
        ]
        self.record = {
            "version": "REGION_VIEW_V001",
            "region_id": region["region_id"],
            "source": contract["source"],
            "native_input": contract["input"],
            "admission": contract["admission"],
            "admission_rule": candidate["rule_version"],
            "frame": FRAME,
            "dimensions": [page["width"], page["height"]],
            "word_indices": self.ids,
            "declared_membership_order": "original admission array order, not a geometric sequence",
            "geometric_word_order": self.geometric_order,
            "local_to_original": self.local_to_original,
            "original_word_pointers": [f"/words/{i}" for i in self.ids],
            "bbox": region["bbox"],
            "boundary_uncertainty": region["boundary_uncertainty"],
            "ownership_uncertainty": region["ownership_uncertainty"],
            "context_policy": CONTEXT_POLICY,
            "source_negative_established": False,
            "semantic_page_completeness": False,
        }
        self.context = [
            {"bbox": w["bbox"], "original_word_index": i} for i, w in enumerate(page["words"])
        ]


def internal_geometry(
    region: dict[str, Any], page: dict[str, Any], bands: dict[str, Any]
) -> dict[str, Any]:
    """Direct necessary conditions on supplied memberships, never new segmentation."""
    ids = region["word_indices"]
    words = page["words"]
    ev = region["structural_evidence"]
    issues: list[dict[str, Any]] = []
    column_checks: list[dict[str, Any]] = []

    def issue(kind: str, **detail: Any) -> None:
        issues.append({"kind": kind, **detail})

    for a, b in itertools.combinations(ids, 2):
        x, y = words[a]["bbox"], words[b]["bbox"]
        if min(x[2], y[2]) > max(x[0], y[0]) and min(x[3], y[3]) > max(x[1], y[1]):
            issue(
                "internal_positive_area_overlap",
                word_indices=[a, b],
                word_pointers=[f"/words/{a}", f"/words/{b}"],
                rectangles=[x, y],
            )
    sequence = [i for bid in ev["line_band_ids"] for i in bands[bid]["word_indices"]]
    columns = ev.get("columns", [])
    gutters = ev.get("persistent_gutters", [])
    if not columns:
        issue("missing_supplied_column_geometry")
    if not gutters:
        issue("missing_supplied_gutter_geometry")
    if any(a["interval"][1] > b["interval"][0] for a, b in itertools.pairwise(columns)):
        issue("overlapping_or_unordered_supplied_column_intervals")
    for n, col in enumerate(columns):
        lo, hi = col["interval"]
        expected = [i for i in ids if lo <= words[i]["bbox"][0] < words[i]["bbox"][2] <= hi]
        ordered = [i for i in sequence if lo <= words[i]["bbox"][0] < words[i]["bbox"][2] <= hi]
        multiset = Counter(col["word_indices"]) == Counter(expected)
        order = col["word_indices"] == ordered
        column_checks.append(
            {
                "column": n,
                "interval": [lo, hi],
                "exact_membership_with_multiplicity": multiset,
                "exact_declared_geometric_sequence": order,
                "expected_count": len(expected),
                "supplied_count": len(col["word_indices"]),
            }
        )
        if not multiset:
            issue(
                "supplied_column_membership_mismatch",
                column=n,
                interval=[lo, hi],
                expected_word_indices=expected,
                supplied_word_indices=col["word_indices"],
            )
        if not order:
            issue(
                "supplied_column_geometric_sequence_mismatch",
                column=n,
                expected_sequence=ordered,
                supplied_sequence=col["word_indices"],
            )
    if columns:
        for i in ids:
            box = words[i]["bbox"]
            owners = [
                n
                for n, col in enumerate(columns)
                if col["interval"][0] <= box[0] < box[2] <= col["interval"][1]
            ]
            if len(owners) != 1:
                issue(
                    "word_not_wholly_in_one_supplied_column",
                    word_pointer=f"/words/{i}",
                    rectangle=box,
                    whole_rectangle_column_owners=owners,
                )
    for bid in ev["line_band_ids"]:
        band = bands[bid]
        runs: Any = band.get("runs")
        if not isinstance(runs, list) or not runs:
            issue("missing_supplied_run_geometry", line_band_id=bid)
            continue
        flat: list[int] = [i for run in cast(list[list[int]], runs) for i in run]
        require(
            Counter(flat) == Counter(band["word_indices"]) and len(flat) == len(set(flat)),
            "malformed_supplied_run_membership",
        )
        box = union([words[i]["bbox"] for i in band["word_indices"]])
        if band.get("bbox") != box:
            issue(
                "supplied_line_band_bbox_mismatch",
                line_band_id=bid,
                source_word_union=box,
                supplied_bbox=band.get("bbox"),
            )
        for n, gutter in enumerate(gutters):
            strip: Any = gutter["empty_x_strip"]
            require(
                isinstance(strip, list)
                and len(cast(list[Any], strip)) == 2
                and all(
                    type(v) in (int, float) and math.isfinite(v) for v in cast(list[Any], strip)
                )
                and 0 <= cast(list[float], strip)[0] < cast(list[float], strip)[1] <= page["width"],
                "malformed_supplied_gutter",
            )
            if (
                len(cast(list[Any], runs)) == 1
                and box is not None
                and box[0] < strip[0]
                and box[2] > strip[1]
            ):
                issue(
                    "source_bound_single_run_spans_gutter",
                    line_band_id=bid,
                    gutter_index=n,
                    empty_x_strip=strip,
                    source_word_union=box,
                    word_pointers=[f"/words/{i}" for i in band["word_indices"]],
                )
    return {
        "performed": True,
        "predicate_version": GEOMETRY_PREDICATES["version"],
        "word_count": len(ids),
        "positive_area_pairs_checked": len(ids) * (len(ids) - 1) // 2,
        "column_checks": column_checks,
        "issues": issues,
    }


def receive(
    contract: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    list[tuple[str, RegionView]],
]:
    require(
        contract["version"] == VERSION and contract["coordinate_representation"] == FRAME,
        "unsupported_composition_contract_or_frame",
    )
    require(
        contract["registry"] == registry() and contract["context_policy"] == CONTEXT_POLICY,
        "unfrozen_registry_or_context",
    )
    require(contract["geometry_predicates"] == GEOMETRY_PREDICATES, "unfrozen_geometry_predicates")
    require(contract["mode"] in ("invented", "actual"), "unsupported_execution_mode")
    io_contract = {
        "version": "M2R05_NATIVE_REGION_ADMISSION_CONTRACT_V001",
        "coordinate_representation": FRAME,
        "rules_version": "NATIVE_GEOMETRIC_REGION_RULES_V001",
        "source": contract["source"],
        "input": contract["input"],
    }
    page, evidence = load_native(io_contract)
    spans = sorted(w["span"] for w in page["words"])
    require(all(a[1] <= b[0] for a, b in itertools.pairwise(spans)), "overlapping_native_spans")
    candidate = pinned(contract["admission"])
    coverage = pinned(contract["coverage"])
    require(
        candidate["version"]
        in ("M2R05_SOURCE_NATIVE_REGION_ADMISSION_V001", "SOURCE_NATIVE_REGION_CANDIDATE_V001")
        and candidate["rule_version"] == "NATIVE_GEOMETRIC_REGION_RULES_V001",
        "wrong_admission_rules",
    )
    require(
        candidate["source"]["pdf_sha256"] == contract["source"]["pdf_sha256"]
        and candidate["source"]["report_number"] == contract["source"]["report_number"],
        "source_identity_mismatch",
    )
    require(
        all(
            candidate["native_input"][k] == contract["input"][k]
            for k in ("sha256", "physical_page", "dimensions", "reference_sha256")
        ),
        "admission_native_mismatch",
    )
    require(
        candidate["coordinate_frame"]
        == {"representation": FRAME, "dimensions": contract["input"]["dimensions"]}
        or (
            candidate["coordinate_frame"]["representation"] == FRAME
            and candidate["coordinate_frame"]["dimensions"] == contract["input"]["dimensions"]
        ),
        "candidate_frame_mismatch",
    )
    require(
        not candidate["source_negative_established"]
        and not candidate["semantic_page_completeness"],
        "unsupported_completeness_claim",
    )
    validate_addendum(contract, candidate, page)
    require(candidate["source_word_count"] == len(page["words"]), "source_population_mismatch")
    regions = candidate["regions"]
    rids = [r["region_id"] for r in regions]
    require(len(rids) == len(set(rids)), "duplicate_region")
    ids = [i for r in regions for i in r["word_indices"]]
    require(Counter(ids) == Counter(range(len(page["words"]))), "altered_or_duplicate_membership")
    cov = coverage["words"]
    require(
        [w["word_index"] for w in cov] == list(range(len(page["words"]))),
        "coverage_order_or_population",
    )
    accepted: dict[str, str] = {}
    unresolved: set[int] = set()
    bands = {b["line_band_id"]: b for b in candidate["line_bands"]}
    require(len(bands) == len(candidate["line_bands"]), "duplicate_line_band")
    for r in regions:
        members = r["word_indices"]
        require(
            r["bbox"] == union([page["words"][i]["bbox"] for i in members]), "wrong_region_bbox"
        )
        for i in members:
            row = cov[i]
            require(row["accounting_region_id"] == r["region_id"], "coverage_region_mismatch")
            owner = row["accepted_region_owner"]
            require(owner is None or owner == r["region_id"], "conflicting_ownership")
            if owner:
                require(
                    not row["competing_hypotheses"]
                    and not r["ownership_uncertainty"]
                    and r["classification"] != "ambiguous_region",
                    "accepted_competing_ownership",
                )
                accepted[str(i)] = owner
            else:
                unresolved.add(i)
        sequence = [
            i for b in r["structural_evidence"]["line_band_ids"] for i in bands[b]["word_indices"]
        ]
        if sequence:
            require(
                Counter(sequence) == Counter(members) and len(sequence) == len(set(sequence)),
                "supplied_band_membership_multiplicity",
            )
            for b in r["structural_evidence"]["line_band_ids"]:
                line = bands[b]["word_indices"]
                require(
                    line == sorted(line, key=lambda i: (page["words"][i]["bbox"][0], i)),
                    "supplied_band_geometric_sequence",
                )
            for col in r["structural_evidence"].get("columns", []):
                interval: Any = col["interval"]
                require(
                    isinstance(interval, list)
                    and len(cast(list[Any], interval)) == 2
                    and all(
                        type(v) in (int, float) and math.isfinite(v)
                        for v in cast(list[Any], interval)
                    )
                    and 0
                    <= cast(list[float], interval)[0]
                    < cast(list[float], interval)[1]
                    <= page["width"],
                    "malformed_supplied_column_interval",
                )
                require(
                    len(col["word_indices"]) == len(set(col["word_indices"]))
                    and set(col["word_indices"]) <= set(members),
                    "duplicate_or_foreign_supplied_column_address",
                )
    require(accepted == coverage["accepted_ownership_map"], "accepted_map_mismatch")
    require(
        set(map(int, coverage["unresolved_overlap_map"])) == unresolved, "unresolved_map_mismatch"
    )
    hypotheses = candidate["competing_region_hypotheses"]
    competing = {i for h in hypotheses for i in h["word_indices"]}
    require(not competing.intersection(map(int, accepted)), "hypothesis_accepted_conflict")
    decisions: list[dict[str, Any]] = []
    views: list[tuple[str, RegionView]] = []
    for r in regions:
        reasons: list[str] = []
        if r["classification"] != "candidate_tabular_region":
            reasons.append("non_tabular_or_ambiguous_class")
        if any(accepted.get(str(i)) != r["region_id"] for i in r["word_indices"]):
            reasons.append("not_exclusively_accepted_membership")
        if any(i in competing for i in r["word_indices"]):
            reasons.append("competing_boundary_hypothesis")
        ev = r["structural_evidence"]
        if (
            not ev.get("table_necessary_conditions", False)
            or ev.get("broad_two_column_flow", False)
            or ev.get("spanning_single_run_band_ids", [])
        ):
            reasons.append("unsupported_or_spanning_structure")
        if r["ownership_uncertainty"]:
            reasons.append("ownership_uncertainty")
        membership = set(r["word_indices"])
        box = r["bbox"]
        if any(
            i not in membership
            and min(w["bbox"][2], box[2]) > max(w["bbox"][0], box[0])
            and min(w["bbox"][3], box[3]) > max(w["bbox"][1], box[1])
            for i, w in enumerate(page["words"])
        ):
            reasons.append("off_region_geometry_intersects_candidate")
        geometry: dict[str, Any] = {
            "performed": False,
            "issues": [],
            "reason": "already_ineligible_under_existing_rules",
        }
        if not reasons:
            geometry = internal_geometry(r, page, bands)
            reasons.extend(dict.fromkeys(issue["kind"] for issue in geometry["issues"]))
        view = RegionView(r, page, evidence, candidate, contract) if not reasons else None
        qualifiers: list[str] = []
        if view:
            qualifiers = qualify(view)
            if len(qualifiers) != 1:
                reasons.append("unknown_or_competing_layout_qualification")
        selected = qualifiers[0] if len(qualifiers) == 1 and not reasons else None
        if (
            selected
            and contract["mode"] == "actual"
            and selected not in contract.get("run_scope", {}).get("allowed_adapters", [])
        ):
            reasons.append("adapter_not_authorized_in_run_scope")
            selected = None
        decisions.append(
            {
                "region_id": r["region_id"],
                "classification": r["classification"],
                "word_count": len(r["word_indices"]),
                "accepted_owner_words": sum(
                    accepted.get(str(i)) == r["region_id"] for i in r["word_indices"]
                ),
                "qualifications": qualifiers,
                "adapter": selected,
                "decision": "dispatch" if selected else "no_dispatch",
                "reasons": reasons,
                "boundary_uncertainty": r["boundary_uncertainty"],
                "geometry_checks": geometry,
            }
        )
        if selected and view is not None:
            views.append((selected, view))
    return page, evidence, candidate, coverage, decisions, views


def qualify(view: RegionView) -> list[str]:
    p = module("priority")
    result: list[str] = []
    for name, spec in registry().items():
        if name not in ("priority", "regional"):
            continue
        choices: list[list[int]] = [
            [i for i, w in enumerate(view.words) if w["text"] == label]
            for label in spec["headings"]
        ]
        headers: list[tuple[int, ...]] = []
        for ids in itertools.product(*choices):
            boxes = [view.words[i]["bbox"] for i in ids]
            if (
                len(set(ids)) == len(ids)
                and all(a[2] < b[0] for a, b in itertools.pairwise(boxes))
                and all(p.same_line(a, b) for a, b in itertools.combinations(boxes, 2))
            ):
                headers.append(ids)
        if len(headers) == 1:
            result.append(name)
    return result


def compose(
    contract: dict[str, Any], output: Path, *, generation_counts: dict[str, int] | None = None
) -> dict[str, Any]:
    if contract["mode"] == "actual":
        require(
            "compose" in contract.get("run_scope", {}).get("allowed_operations", []),
            "composition_not_authorized",
        )
    require(not output.exists(), "exclusive_output_exists")
    page, evidence, admission, coverage, decisions, views = receive(contract)
    output.mkdir()
    write(
        output / "dispatch_ledger.json",
        {
            "version": VERSION,
            "decisions": decisions,
            "admission": contract["admission"],
            "generation_started": False,
        },
    )
    write(output / "dispatch_ledger_seal.json", pin(output / "dispatch_ledger.json"))
    calls = {"admission": 0, "composition": 1, "priority": 0, "regional": 0, "engine": 0}
    results: list[dict[str, Any]] = []
    if contract["mode"] == "actual":
        scope = contract["run_scope"]
        require(
            all(name in scope["allowed_adapters"] for name, _ in views), "adapter_not_authorized"
        )
        if len(views) > scope["max_adapter_calls"]:
            write(
                output / "downstream_abstention.json",
                {
                    "reason": "eligible_regions_exceed_generation_budget",
                    "eligible_regions": len(views),
                    "generation_started": False,
                },
            )
            views = []
    for adapter, view in views:
        calls[adapter] += 1
        if generation_counts is not None:
            generation_counts[adapter] += 1
        if contract["mode"] == "actual":
            write(
                output / (adapter + "_generation_started.json"),
                {
                    "adapter": adapter,
                    "underlying_generation_call": calls[adapter],
                    "region_id": view.region["region_id"],
                    "started_utc": datetime.now(UTC).isoformat(),
                    "admitted_word_indices": view.ids,
                },
            )
        result = (
            scoped_priority(view, contract)
            if adapter == "priority"
            else scoped_regional(view, contract, output)
        )
        allowed = set(view.ids)
        for row in result["rows"]:
            for cell in row["cells"]:
                require(set(cell["word_indices"]) <= allowed, "off_region_field_leak")
        results.append(result)
    composed = {
        "version": VERSION,
        "authorship": "Codex AI exposed developmental composition; not Jorge PI review",
        "source": contract["source"],
        "input": contract["input"],
        "admission": contract["admission"],
        "registry": registry(),
        "context_policy": CONTEXT_POLICY,
        "results": results,
        "calls": calls,
        "canonical_objects_created": False,
        "source_negative_established": False,
        "semantic_page_completeness": False,
    }
    write(output / "composed_candidate.json", composed)
    write(
        output / "source_word_evidence.json",
        {
            "input": contract["input"],
            "frame": FRAME,
            "span_frame": "native JSON own /text",
            "words": evidence,
        },
    )
    extracted = {i for result in results for i in result["view"]["word_indices"]}
    field_words = {
        i
        for result in results
        for row in result["rows"]
        for cell in row["cells"]
        for i in cell["word_indices"]
    }
    write(
        output / "source_scope_accounting.json",
        {
            "source_words": len(page["words"]),
            "adapter_admitted_words": len(extracted),
            "outside_adapter_words": len(page["words"]) - len(extracted),
            "accepted_context_or_other_words": len(
                set(map(int, coverage["accepted_ownership_map"])) - extracted
            ),
            "unresolved_words": len(coverage["unresolved_overlap_map"]),
            "regions": len(admission["regions"]),
            "coverage": contract["coverage"],
            "extracted_membership": sorted(extracted),
            "extracted_membership_meaning": (
                "adapter-admitted scope, including headers and ordinals"
            ),
            "returned_cell_source_word_indices": sorted(field_words),
            "returned_cell_source_word_count": len(field_words),
            "no_source_negative_claim": True,
        },
    )
    tables: list[dict[str, Any]] = []
    for result in results:
        selected = [r for r in result["rows"] if r["status"] == "accepted"]
        if selected and result["status"] == "processed":
            header = result["header"]["labels"]
            cells = [header] + [
                ([r["ordinal"]["text"]] if result["adapter"] == "priority" else [])
                + [cell["value"] for cell in r["cells"]]
                for r in selected
            ]
            tables.append(
                {
                    "bbox": result["view"]["bbox"],
                    "cells": cells,
                    "region_id": result["region_id"],
                    "adapter": result["adapter"],
                    "row_ids": [r["row_id"] for r in selected],
                }
            )
    write(
        output / "table_derivative.json",
        {
            "source_sha256": contract["source"]["pdf_sha256"],
            "report_number": contract["source"]["report_number"],
            "physical_page": contract["input"]["physical_page"],
            "status": "region_scoped_native_word_derivative_v001",
            "authority": (
                "Codex AI region-scoped source-native documentary derivative; not raw official text"
            ),
            "empty_table_result_certifies_absence": False,
            "native_sha256": contract["input"]["sha256"],
            "candidate": pin(output / "composed_candidate.json"),
            "tables": tables,
            "source_negative_established": False,
            "coordinate_frame": FRAME,
        },
    )
    write(
        output / "candidate_seal.json",
        {
            "version": "COMPOSITION_FIRST_SEAL_V001",
            "files": [
                pin(output / name)
                for name in [
                    "dispatch_ledger.json",
                    "composed_candidate.json",
                    "source_word_evidence.json",
                    "source_scope_accounting.json",
                    "table_derivative.json",
                ]
            ],
            "underlying_calls": calls,
        },
    )
    return composed


def receiving_only(contract: dict[str, Any], output: Path) -> dict[str, Any]:
    """Inspect the same receiver while generator entry points fail visibly."""
    from contextlib import ExitStack
    from unittest.mock import patch

    from peru_conflicts.execution import source_addressed_tables as engine

    require(not output.exists(), "exclusive_output_exists")
    counts = {
        key: 0
        for key in (
            "priority_wrapper",
            "priority_algorithm",
            "regional_wrapper",
            "regional_algorithm",
            "full_composition",
            "engine",
        )
    }

    def blocked(name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            counts[name] += 1
            raise RuntimeError("receive_only_generation_entry_forbidden:" + name)

        return fail

    try:
        with ExitStack() as stack:
            for target, name, label in (
                (sys.modules[__name__], "scoped_priority", "priority_wrapper"),
                (sys.modules[__name__], "scoped_regional", "regional_wrapper"),
                (sys.modules[__name__], "compose", "full_composition"),
                (priority, "discover", "priority_algorithm"),
                (regional, "adapt_page", "regional_algorithm"),
                (engine, "run", "engine"),
                (engine, "main", "engine"),
            ):
                stack.enter_context(patch.object(target, name, blocked(label)))
            page, _, candidate, coverage, decisions, views = receive(contract)
    finally:
        write(
            output.with_suffix(".guard.json"),
            {
                "version": "RECEIVING_ONLY_FAIL_ON_CALL_V001",
                "generation_entry_attempts": counts,
                "generation_functions_restored": True,
            },
        )
    for decision in decisions:
        if decision["decision"] == "dispatch":
            decision["decision"] = "would_dispatch"
        decision["executed"] = False
    admitted = {i for _, view in views for i in view.ids}
    accepted = set(map(int, coverage["accepted_ownership_map"]))
    result = {
        "version": VERSION,
        "mode": "receiving_only",
        "executed": False,
        "source": contract["source"],
        "input": contract["input"],
        "admission": contract["admission"],
        "predicate_contract": GEOMETRY_PREDICATES,
        "decisions": decisions,
        "generation_entry_attempts": counts,
        "source_words": len(page["words"]),
        "accounting_regions": len(candidate["regions"]),
        "eligible_words_not_extracted": len(admitted),
        "outside_eligible_words": len(page["words"]) - len(admitted),
        "accepted_context_or_other_words": len(accepted - admitted),
        "unresolved_words": len(coverage["unresolved_overlap_map"]),
        "source_negative_established": False,
        "semantic_page_completeness": False,
        "canonical_objects_created": False,
    }
    write(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--receive-only", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    try:
        if a.receive_only:
            require(
                a.output is not None and a.output_dir is None, "receive_only_requires_output_file"
            )
            result = receiving_only(read(a.contract), cast(Path, a.output))
            print(
                __import__("json").dumps(
                    {
                        "mode": "receiving_only",
                        "eligible_regions": sum(
                            d["decision"] == "would_dispatch" for d in result["decisions"]
                        ),
                        "generation_entry_attempts": result["generation_entry_attempts"],
                    }
                )
            )
            return 0
        require(
            a.output_dir is not None and a.output is None, "composition_requires_output_directory"
        )
        result = compose(read(a.contract), cast(Path, a.output_dir))
        print(
            json.dumps(
                {
                    "status": "preserved",
                    "calls": result["calls"],
                    "results": [
                        {k: r[k] for k in ("region_id", "adapter", "status")}
                        for r in result["results"]
                    ],
                }
            )
        )
        return 0
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as e:
        print(
            json.dumps({"status": "rejected_or_failed_preserve_first", "error": str(e)}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
