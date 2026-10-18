"""Invented-only integration/transfer fixtures; never imports an admission detector."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from peru_conflicts.execution.native_documentary import receiver as c

Json = dict[str, Any]


def put(path: str | Path, value: Json) -> Json:
    c.write(path, value)
    return c.pin(path)


def fixture(
    root: Path,
    layouts: tuple[str, ...] = ("priority",),
    change: Callable[[list[Json], list[list[int]]], Any] | None = None,
    scale: float = 1,
    dx: float = 0,
    dy: float = 0,
    reverse: bool = False,
) -> tuple[Json, Json]:
    tokens: list[Json] = []
    memberships: list[list[int]] = []
    for n, layout in enumerate(layouts):
        start = len(tokens)
        y = 30 + n * 180
        rows = (
            [
                ["N.°", "Lugar", "Caso", "Situación"],
                ["1.", "Valle", "Petición", "Activo"],
                ["2.", "Isla", "Solicitud", "Diálogo"],
            ]
            if layout == "priority"
            else [["Región", "Total", "%"], ["Zona Azul", "7", "35.0%"], ["TOTAL", "20", "100.0%"]]
        )
        xs = [30, 100, 260, 440] if layout == "priority" else [50, 280, 450]
        for r, row in enumerate(rows):
            for col, text in enumerate(row):
                for k, token in enumerate(text.split(" ")):
                    x = xs[col] + k * 30
                    tokens.append(
                        {
                            "text": token,
                            "bbox": [
                                (x + dx) * scale,
                                (y + r * 35 + dy) * scale,
                                (x + max(12, len(token) * 4) + dx) * scale,
                                (y + r * 35 + 9 + dy) * scale,
                            ],
                        }
                    )
        memberships.append(list(range(start, len(tokens))))
    tokens.append(
        {
            "text": "Crédito",
            "bbox": [
                (20 + dx) * scale,
                (len(layouts) * 180 + 100 + dy) * scale,
                (60 + dx) * scale,
                (len(layouts) * 180 + 109 + dy) * scale,
            ],
        }
    )
    if change:
        change(tokens, memberships)
    if reverse:
        old = tokens
        tokens = list(reversed(tokens))
        m = {i: len(old) - 1 - i for i in range(len(old))}
        memberships = [[m[i] for i in ids] for ids in memberships]
    text = ""
    words: list[Json] = []
    for t in tokens:
        start = len(text)
        text += t["text"]
        words.append(t | {"span": [start, len(text)]})
        text += " \n"
    page: Json = {
        "physical_page": 5,
        "width": (650 + dx) * scale,
        "height": (len(layouts) * 180 + 250 + dy) * scale,
        "text": text,
        "words": words,
        "layout_lines": [{"words": [w]} for w in words],
        "reference_sha256": "a" * 64,
        "representation_status": "native_text_present",
    }
    native = put(root / "native.json", page)
    regions: list[Json] = []
    bands: list[Json] = []
    owners: dict[str, str] = {}
    coverage: list[Json] = []
    for n, ids in enumerate(memberships):
        rid = f"fixture-{n}"
        bids: list[str] = []
        ys = sorted(set(words[i]["bbox"][1] for i in ids))
        for yy in ys:
            b = f"b{len(bands)}"
            bids.append(b)
            line = sorted(
                [i for i in ids if words[i]["bbox"][1] == yy], key=lambda i: words[i]["bbox"][0]
            )
            bands.append({"line_band_id": b, "word_indices": line})
        bbox = cast("list[float]", c.union([words[i]["bbox"] for i in ids]))
        basecuts = [75, 220, 400] if layouts[n] == "priority" else [220, 400]
        cuts = [(x + dx) * scale for x in basecuts]
        intervals = list(zip([bbox[0], *cuts], [*cuts, bbox[2]], strict=False))
        supplied_sequence = [
            i for b in bands if b["line_band_id"] in bids for i in b["word_indices"]
        ]
        columns = [
            {
                "interval": [left, right],
                "word_indices": [
                    i
                    for i in supplied_sequence
                    if left <= sum(cast("list[float]", words[i]["bbox"])[::2]) / 2 <= right
                ],
            }
            for left, right in intervals
        ]
        gutters = [
            {
                "empty_x_strip": [(x - 5 + dx) * scale, (x + 5 + dx) * scale],
                "supporting_line_band_ids": bids,
            }
            for x in basecuts
        ]
        for b in bands:
            if b["line_band_id"] in bids:
                b["bbox"] = c.union([words[i]["bbox"] for i in b["word_indices"]])
                b["runs"] = [
                    [
                        i
                        for i in b["word_indices"]
                        if left <= sum(cast("list[float]", words[i]["bbox"])[::2]) / 2 <= right
                    ]
                    for left, right in intervals
                ]
                b["runs"] = [run for run in b["runs"] if run]
        regions.append(
            {
                "region_id": rid,
                "classification": "candidate_tabular_region",
                "word_indices": sorted(ids),
                "bbox": c.union([words[i]["bbox"] for i in ids]),
                "ownership_uncertainty": [],
                "boundary_uncertainty": ["provisional boundary"],
                "structural_evidence": {
                    "line_band_ids": bids,
                    "table_necessary_conditions": True,
                    "columns": columns,
                    "persistent_gutters": gutters,
                },
            }
        )
        owners.update({str(i): rid for i in ids})
    remaining = sorted(set(range(len(words))) - set(map(int, owners)))
    if remaining:
        regions.append(
            {
                "region_id": "context",
                "classification": "candidate_continuation_or_context",
                "word_indices": remaining,
                "bbox": c.union([words[i]["bbox"] for i in remaining]),
                "ownership_uncertainty": [],
                "boundary_uncertainty": [],
                "structural_evidence": {"line_band_ids": []},
            }
        )
    owners.update({str(i): "context" for i in remaining})
    for r in regions:
        for i in r["word_indices"]:
            coverage.append(
                {
                    "word_index": i,
                    "accounting_region_id": r["region_id"],
                    "accepted_region_owner": r["region_id"],
                    "competing_hypotheses": [],
                }
            )
    source: Json = {"pdf_sha256": "b" * 64, "report_number": 999}
    inp = native | {
        "physical_page": 5,
        "dimensions": [page["width"], page["height"]],
        "reference_sha256": page["reference_sha256"],
    }
    candidate: Json = {
        "version": "M2R05_SOURCE_NATIVE_REGION_ADMISSION_V001",
        "rule_version": "NATIVE_GEOMETRIC_REGION_RULES_V001",
        "source": source,
        "native_input": inp,
        "coordinate_frame": {"representation": c.FRAME, "dimensions": inp["dimensions"]},
        "regions": regions,
        "line_bands": bands,
        "competing_region_hypotheses": [],
        "source_word_count": len(words),
        "source_negative_established": False,
        "semantic_page_completeness": False,
    }
    ap = put(root / "admission.json", candidate)
    cp = put(
        root / "coverage.json",
        {
            "words": sorted(coverage, key=lambda w: w["word_index"]),
            "accepted_ownership_map": owners,
            "unresolved_overlap_map": {},
        },
    )
    audit = put(root / "audit.json", {"failed_checks": 0, "failures": [], "candidate": ap})
    contract: Json = {
        "version": c.VERSION,
        "mode": "invented",
        "source": source,
        "input": inp,
        "admission": ap,
        "coverage": cp,
        "validation": audit,
        "addendum": None,
        "coordinate_representation": c.FRAME,
        "registry": c.registry(),
        "context_policy": c.CONTEXT_POLICY,
        "geometry_predicates": getattr(c, "GEOMETRY_PREDICATES", {}),
    }
    return contract, page


class CompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def execute(self, contract: Json, name: str = "result") -> tuple[int, Path]:
        path = self.root / (name + "_contract.json")
        if not path.exists():
            put(path, contract)
        output = self.root / (name + "_output")
        from peru_conflicts.execution import source_addressed_tables as engine

        with (
            patch.object(c, "scoped_priority", wraps=c.scoped_priority) as pri,
            patch.object(c, "scoped_regional", wraps=c.scoped_regional) as reg,
            patch.object(engine, "run", wraps=engine.run) as common,
        ):
            rc = c.main(["--contract", str(path), "--output-dir", str(output)])
            measured = {
                "priority": pri.call_count,
                "regional": reg.call_count,
                "engine": common.call_count,
            }
            if rc == 0:
                decisions = c.read(output / "dispatch_ledger.json")["decisions"]
                if all(d["decision"] == "no_dispatch" for d in decisions):
                    self.assertEqual(measured, {"priority": 0, "regional": 0, "engine": 0})
                    self.assertEqual(c.read(output / "composed_candidate.json")["results"], [])
                    self.assertEqual(c.read(output / "table_derivative.json")["tables"], [])
                    self.assertFalse((output / "engine_config.json").exists())
                    TEST_EVENTS.append(
                        {
                            "test": self.id(),
                            "all_regions_rejected_before_generation": True,
                            "measured_calls": measured,
                            "reasons": [d["reasons"] for d in decisions],
                        }
                    )
            elif rc == 2:
                self.assertEqual(measured, {"priority": 0, "regional": 0, "engine": 0})
        return rc, output

    def changed_admission(self, spec: Json, fn: Callable[[Json], Any]) -> Json:
        a = c.read(spec["admission"]["path"])
        fn(a)
        path = self.root / ("modified_" + str(len(list(self.root.glob("modified*")))) + ".json")
        spec["admission"] = put(path, a)
        audit = c.read(spec["validation"]["path"])
        audit["candidate"] = spec["admission"]
        spec["validation"] = put(path.with_name(path.stem + "_audit.json"), audit)
        return spec

    def test_both_layouts_end_to_end(self) -> Any:
        spec, _ = fixture(self.root, ("priority", "regional"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        d = c.read(out / "composed_candidate.json")
        self.assertEqual([x["adapter"] for x in d["results"]], ["priority", "regional"])
        for result in d["results"]:
            self.assertTrue(result["rows"])
            self.assertEqual(result["status"], "processed")
        from peru_conflicts.execution.native_documentary.profile import build
        from peru_conflicts.execution.source_addressed_tables import run

        cfg = build(out)
        put(out / "engine_config.json", cfg)
        engine_rc = run(out / "engine_config.json", out / "engine_result.json")
        self.assertEqual(engine_rc, 0, json.dumps(c.read(out / "engine_result.json").get("errors")))
        self.assertEqual(c.read(out / "engine_result.json")["candidate_status"], "processed")
        counts = c.read(out / "engine_result.json")["counts"]
        self.assertEqual(counts["documentary_rows"], 2)
        self.assertEqual(counts["published_measurements"], 2)
        TEST_EVENTS.append(
            {
                "test": self.id(),
                "real_invented_adapter_routes": ["priority", "regional"],
                "unchanged_engine_return_code": engine_rc,
                "counts": counts,
            }
        )

    def test_unknown_header_no_dispatch(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[1].update(text="Destino"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(c.read(out / "composed_candidate.json")["calls"]["priority"], 0)

    def test_ownership_abstains(self) -> Any:
        for kind in ["ambiguous_region", "candidate_prose_region"]:
            folder = self.root / kind
            folder.mkdir()
            spec, _ = fixture(folder)
            a = c.read(spec["admission"]["path"])
            a["regions"][0]["classification"] = kind
            (folder / "admission.json").unlink()
            spec["admission"] = put(folder / "admission.json", a)
            if kind == "ambiguous_region":
                coverage = c.read(spec["coverage"]["path"])
                for i in a["regions"][0]["word_indices"]:
                    coverage["words"][i]["accepted_region_owner"] = None
                    coverage["accepted_ownership_map"].pop(str(i))
                    coverage["unresolved_overlap_map"][str(i)] = {"classification_uncertain": True}
                (folder / "coverage.json").unlink()
                spec["coverage"] = put(folder / "coverage.json", coverage)
            a = c.read(spec["validation"]["path"])
            a["candidate"] = spec["admission"]
            (folder / "audit.json").unlink()
            spec["validation"] = put(folder / "audit.json", a)
            rc, out = self.execute(spec, kind)
            self.assertEqual(rc, 0)
            self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_wrong_native_hash(self) -> Any:
        spec, _ = fixture(self.root)
        spec["input"]["sha256"] = "c" * 64
        self.assertEqual(self.execute(spec)[0], 2)

    def test_wrong_frame(self) -> Any:
        spec, _ = fixture(self.root)
        spec["coordinate_representation"] = "pixels"
        self.assertEqual(self.execute(spec)[0], 2)

    def test_duplicate_membership(self) -> Any:
        spec, _ = fixture(self.root)
        spec = self.changed_admission(spec, lambda a: a["regions"][0]["word_indices"].append(0))
        self.assertEqual(self.execute(spec)[0], 2)

    def test_unrelated_failure_not_waived(self) -> Any:
        spec, _ = fixture(self.root)
        a = c.read(spec["validation"]["path"])
        a.update(failed_checks=1, failures=[{"check": "unrelated", "address": "x"}])
        (self.root / "audit.json").unlink()
        spec["validation"] = put(self.root / "audit.json", a)
        self.assertEqual(self.execute(spec)[0], 2)

    def test_serialization_transfer(self) -> Any:
        spec, _ = fixture(self.root, reverse=True, scale=1.4, dx=15, dy=20)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        result = c.read(out / "composed_candidate.json")["results"][0]
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["rows"][0]["cells"][0]["value"], "Valle")

    def test_body_change_same_dispatch(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[6].update(text="Cambio"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "composed_candidate.json")["results"][0]["adapter"], "priority"
        )

    def test_duplicate_ordinal_partial(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[8].update(text="1."))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertNotEqual(
            c.read(out / "composed_candidate.json")["results"][0]["status"], "processed"
        )

    def test_missing_ordinal_partial(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[8].update(text="?"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertNotEqual(
            c.read(out / "composed_candidate.json")["results"][0]["status"], "processed"
        )

    def test_exclusive_outputs(self) -> Any:
        spec, _ = fixture(self.root)
        self.assertEqual(self.execute(spec)[0], 0)
        self.assertEqual(self.execute(spec)[0], 2)

    def test_determinism(self) -> Any:
        spec, _ = fixture(self.root)
        _, one = self.execute(spec, "one")
        _, two = self.execute(spec, "two")
        self.assertEqual(
            c.read(one / "composed_candidate.json"), c.read(two / "composed_candidate.json")
        )

    def test_offregion_header_cannot_qualify(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            m[0].remove(1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_broad_two_column_no_dispatch(self) -> Any:
        spec, _ = fixture(self.root)
        spec = self.changed_admission(
            spec,
            lambda a: a["regions"][0]["structural_evidence"].update(broad_two_column_flow=True),
        )
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_spanning_structure_no_dispatch(self) -> Any:
        spec, _ = fixture(self.root)
        spec = self.changed_admission(
            spec,
            lambda a: a["regions"][0]["structural_evidence"].update(
                spanning_single_run_band_ids=["b1"]
            ),
        )
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_conflicting_owner_rejected(self) -> Any:
        spec, _ = fixture(self.root)
        v = c.read(spec["coverage"]["path"])
        v["words"][0]["accepted_region_owner"] = "other"
        spec["coverage"] = put(self.root / "conflict.json", v)
        self.assertEqual(self.execute(spec)[0], 2)

    def test_unmatched_addendum_rejected(self) -> Any:
        spec, _ = fixture(self.root)
        a = c.read(spec["validation"]["path"])
        a.update(
            failed_checks=1,
            failures=[
                {"pass": False, "check": "supplied_column_membership", "address": "fixture-0"}
            ],
        )
        spec["validation"] = put(self.root / "failed_audit.json", a)
        spec["addendum"] = put(
            self.root / "bad_addendum.json",
            {"candidate": {"sha256": "c" * 64}, "first_validation": spec["validation"]},
        )
        self.assertEqual(self.execute(spec)[0], 2)

    def test_missing_addendum_rejected(self) -> Any:
        spec, _ = fixture(self.root)
        a = c.read(spec["validation"]["path"])
        a.update(
            failed_checks=1,
            failures=[
                {"pass": False, "check": "supplied_column_membership", "address": "fixture-0"}
            ],
        )
        spec["validation"] = put(self.root / "failed_audit.json", a)
        self.assertEqual(self.execute(spec)[0], 2)

    def test_column_set_match_wrong_sequence_rejected(self) -> Any:
        spec, page = fixture(self.root)

        def mutate(a: Any) -> Any:
            ids = [i for b in a["line_bands"] for i in b["word_indices"]]
            a["regions"][0]["structural_evidence"]["columns"] = [
                {"interval": [0, page["width"]], "word_indices": list(reversed(ids))}
            ]

        spec = self.changed_admission(spec, mutate)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertIn(
            "supplied_column_geometric_sequence_mismatch",
            c.read(out / "dispatch_ledger.json")["decisions"][0]["reasons"],
        )

    def test_band_x_order_rejected(self) -> Any:
        spec, _ = fixture(self.root)
        spec = self.changed_admission(spec, lambda a: a["line_bands"][0]["word_indices"].reverse())
        self.assertEqual(self.execute(spec)[0], 2)

    def test_unknown_body_does_not_change_registry(self) -> Any:
        spec, _ = fixture(
            self.root, change=lambda w, m: [w[i].update(text="Región") for i in (5, 6, 7)]
        )
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "dispatch_ledger.json")["decisions"][0]["adapter"], "priority"
        )

    def test_literal_internal_spaces_and_newline(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[5].update(text="Árbol  raro\nñ"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "composed_candidate.json")["results"][0]["rows"][0]["cells"][0]["value"],
            "Árbol  raro\nñ",
        )

    def test_multiline_cells_preserved(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            w.append({"text": "segunda", "bbox": [100, 76, 130, 85]})
            m[0].append(len(w) - 1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "composed_candidate.json")["results"][0]["rows"][0]["cells"][0]["value"],
            "Valle\nsegunda",
        )

    def test_box_overlap_abstains(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[6].update(bbox=[100, 65, 280, 74]))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "dispatch_ledger.json")["decisions"][0]["decision"], "no_dispatch"
        )
        self.assertEqual(c.read(out / "composed_candidate.json")["calls"]["priority"], 0)

    def test_offregion_geometry_unanchored_guard_retained(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            for x in (100, 260, 440):
                w.append({"text": "sin-ancla", "bbox": [x, 120, x + 35, 129]})

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        result = c.read(out / "composed_candidate.json")["results"][0]
        self.assertEqual(result["status"], "partial")
        self.assertTrue(
            any(
                x["kind"] == "possible_unanchored_continuation_after_stop"
                for x in result["unresolved"]
            )
        )

    def test_offregion_text_change_no_field_effect(self) -> Any:
        spec, _ = fixture(self.root)
        _, out = self.execute(spec, "before")
        before = c.read(out / "composed_candidate.json")["results"][0]["rows"]
        sub = self.root / "afterfixture"
        sub.mkdir()
        spec, _ = fixture(
            sub, change=lambda w, m: w[-1].update(text="N.° Lugar Caso Situación TOTAL")
        )
        _, out = self.execute(spec, "after")
        after = c.read(out / "composed_candidate.json")["results"][0]["rows"]
        self.assertEqual(
            [[x["value"] for x in row["cells"]] for row in before],
            [[x["value"] for x in row["cells"]] for row in after],
        )

    def test_regional_transfer_total_distinct(self) -> Any:
        spec, _ = fixture(self.root, ("regional",), scale=0.7, dx=40, dy=25, reverse=True)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        rows = c.read(out / "composed_candidate.json")["results"][0]["rows"]
        self.assertEqual([r["row_kind"] for r in rows], ["regional_category", "published_total"])

    def test_competing_layouts_no_dispatch(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            for text, x in [("Región", 50), ("Total", 280), ("%", 450)]:
                w.append({"text": text, "bbox": [x, 12, x + 20, 21]})
                m[0].append(len(w) - 1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_malformed_geometry_rejected(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[5].update(bbox=[100, 65, 99, 74]))
        self.assertEqual(self.execute(spec)[0], 2)

    def test_cli_populated_entry_point(self) -> Any:
        spec, _ = fixture(self.root)
        put(self.root / "cli_contract.json", spec)
        r = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "peru_conflicts.execution.native_documentary.receiver",
                "--contract",
                str(self.root / "cli_contract.json"),
                "--output-dir",
                str(self.root / "cli_output"),
            ],
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertTrue((self.root / "cli_output" / "candidate_seal.json").exists())

    def test_known_order_addendum_only(self) -> Any:
        spec, _ = fixture(self.root)
        audit = c.read(spec["validation"]["path"])
        fail = [{"pass": False, "check": "supplied_column_membership", "address": "fixture-0"}]
        audit.update(
            failed_checks=1, failures=fail, check_category_counts={"native_input_identity": 1}
        )
        spec["validation"] = put(self.root / "known_audit.json", audit)
        add = {
            "first_validation": spec["validation"],
            "candidate": spec["admission"],
            "first_failures": fail,
            "failed_checks": 0,
            "passed_checks": 49,
            "no_generation_or_boundary_regrouping": True,
            "check_category_counts": {"same_pinned_native_source": 1},
        }
        spec["addendum"] = put(self.root / "known_addendum.json", add)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertEqual(
            c.read(out / "composed_candidate.json")["results"][0]["adapter"], "priority"
        )

    def test_zero_regions_is_not_source_negative(self) -> Any:
        spec, _ = fixture(self.root, ())
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        cand = c.read(out / "composed_candidate.json")
        self.assertFalse(cand["results"])
        self.assertFalse(cand["source_negative_established"])

    def test_repeated_heading_no_dispatch(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            for text, x in zip(
                ["N.°", "Lugar", "Caso", "Situación"], [30, 100, 260, 440], strict=True
            ):
                w.append({"text": text, "bbox": [x, 12, x + 20, 21]})
                m[0].append(len(w) - 1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_null_word_rejected_not_zero(self) -> Any:
        # Construction itself must reject nulls, rather than converting them to text/zero.
        with self.assertRaises(TypeError):
            fixture(self.root, change=lambda w, m: w[5].update(text=None))

    def test_wrong_physical_page(self) -> Any:
        spec, _ = fixture(self.root)
        spec["input"]["physical_page"] = 6
        self.assertEqual(self.execute(spec)[0], 2)

    def test_null_and_empty_rejected_at_receiver(self) -> Any:
        for n, text in enumerate((None, False, 0, "")):
            folder = self.root / str(n)
            folder.mkdir()
            spec, page = fixture(folder)
            page["words"][5]["text"] = text
            spec["input"] = put(folder / "invalid_native.json", page) | {
                k: spec["input"][k] for k in ("physical_page", "dimensions", "reference_sha256")
            }
            self.assertEqual(self.execute(spec, "invalid" + str(n))[0], 2)

    def test_source_credit_alternative_no_dispatch(self) -> Any:
        spec, _ = fixture(self.root)
        a = c.read(spec["admission"]["path"])
        ids = a["regions"][0]["word_indices"]
        a["competing_region_hypotheses"] = [
            {
                "hypothesis_id": "credit-alternative",
                "region_ids": [a["regions"][0]["region_id"]],
                "word_indices": ids,
            }
        ]
        spec = self.changed_admission(
            spec, lambda v: v.update(competing_region_hypotheses=a["competing_region_hypotheses"])
        )
        cov = c.read(spec["coverage"]["path"])
        for i in ids:
            cov["words"][i].update(
                accepted_region_owner=None, competing_hypotheses=["credit-alternative"]
            )
            cov["accepted_ownership_map"].pop(str(i))
            cov["unresolved_overlap_map"][str(i)] = {"competing_hypotheses": ["credit-alternative"]}
        spec["coverage"] = put(self.root / "credit_coverage.json", cov)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        self.assertFalse(c.read(out / "composed_candidate.json")["results"])

    def test_multiline_status_retains_abstention(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            w.append({"text": "segunda", "bbox": [440, 76, 470, 85]})
            m[0].append(len(w) - 1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        r = c.read(out / "composed_candidate.json")["results"][0]
        self.assertEqual(r["status"], "partial")
        self.assertIsNone(r["rows"][0]["cells"][2]["value"])


TEST_EVENTS: list[Json] = []


class GeometryGateTests(unittest.TestCase):
    tmp: tempfile.TemporaryDirectory[str]
    root: Path

    setUp = CompositionTests.setUp
    tearDown = CompositionTests.tearDown
    execute = CompositionTests.execute
    changed_admission = CompositionTests.changed_admission

    def reject_before_generation(self, spec: Any, reason: Any) -> Any:
        from peru_conflicts.execution import source_addressed_tables as engine

        with (
            patch.object(c, "scoped_priority", wraps=c.scoped_priority) as pri,
            patch.object(c, "scoped_regional", wraps=c.scoped_regional) as reg,
            patch.object(c, "qualify", wraps=c.qualify) as qual,
            patch.object(engine, "run", wraps=engine.run) as common,
        ):
            rc, out = self.execute(spec)
            measured = {
                "priority": pri.call_count,
                "regional": reg.call_count,
                "engine": common.call_count,
                "qualification": qual.call_count,
            }
            TEST_EVENTS.append(
                {
                    "test": self.id(),
                    "boundary": "no generation before geometry rejection",
                    "required_reason": reason,
                    "measured_calls": measured,
                    "return_code": rc,
                }
            )
            self.assertEqual(
                rc,
                0,
                "Must reach the geometry gate, not reject an unrelated identity/fixture error",
            )
            first = c.read(out / "dispatch_ledger.json")["decisions"][0]
            self.assertEqual(first["decision"], "no_dispatch")
            self.assertIn(reason, first["reasons"])
            self.assertEqual(
                measured, {"priority": 0, "regional": 0, "engine": 0, "qualification": 0}
            )
            self.assertEqual(c.read(out / "composed_candidate.json")["results"], [])
            self.assertEqual(c.read(out / "table_derivative.json")["tables"], [])
            self.assertFalse((out / "engine_config.json").exists())
            return first

    def test_priority_internal_overlap_before_qualification_and_generation(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[6].update(bbox=[100, 65, 280, 74]))
        first = self.reject_before_generation(spec, "internal_positive_area_overlap")
        issues = first["geometry_checks"]["issues"]
        pair = next(i for i in issues if i["kind"] == "internal_positive_area_overlap")
        self.assertEqual(pair["word_pointers"], ["/words/5", "/words/6"])
        self.assertEqual(pair["rectangles"][1], [100, 65, 280, 74])

    def test_regional_internal_overlap_before_generation(self) -> Any:
        spec, _ = fixture(
            self.root, ("regional",), change=lambda w, m: w[5].update(bbox=[50, 65, 300, 74])
        )
        self.reject_before_generation(spec, "internal_positive_area_overlap")

    def test_column_whole_extent_not_midpoint(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[6].update(bbox=[210, 65, 240, 74]))
        # 225 is inside column [220,400], but x0=210 is outside it.
        first = self.reject_before_generation(spec, "word_not_wholly_in_one_supplied_column")
        self.assertTrue(
            any(
                i["kind"] == "supplied_column_membership_mismatch"
                for i in first["geometry_checks"]["issues"]
            )
        )

    def test_single_run_spanning_contradicts_empty_flag(self) -> Any:
        spec, _ = fixture(self.root)

        def mutate(a: Any) -> Any:
            a["line_bands"][0]["runs"] = [a["line_bands"][0]["word_indices"]]

        spec = self.changed_admission(spec, mutate)
        self.reject_before_generation(spec, "source_bound_single_run_spans_gutter")

    def test_edge_and_corner_touch_are_not_positive_area(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            for text, box in [("edge", [120, 65, 140, 74]), ("corner", [140, 74, 160, 83])]:
                w.append({"text": text, "bbox": box})
                m[0].append(len(w) - 1)

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        decision = c.read(out / "dispatch_ledger.json")["decisions"][0]
        self.assertEqual(decision["decision"], "dispatch")
        self.assertFalse(decision["geometry_checks"]["issues"])
        self.assertEqual(c.read(out / "composed_candidate.json")["calls"]["priority"], 1)
        TEST_EVENTS.append({"test": self.id(), "edge_and_corner_contact_admitted": True})

    def test_overlap_only_in_ineligible_context_not_global(self) -> Any:
        def change(w: Any, m: Any) -> Any:
            w.append({"text": "fuera-A", "bbox": [100, 300, 140, 309]})
            w.append({"text": "fuera-B", "bbox": [120, 304, 160, 313]})

        spec, _ = fixture(self.root, change=change)
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        decision = c.read(out / "dispatch_ledger.json")["decisions"][0]
        self.assertEqual(decision["decision"], "dispatch")
        self.assertEqual(c.read(out / "composed_candidate.json")["calls"]["priority"], 1)
        TEST_EVENTS.append(
            {"test": self.id(), "off_target_overlap_does_not_disable_clean_region": True}
        )

    def test_cross_region_intersection_still_no_dispatch(self) -> Any:
        spec, _ = fixture(
            self.root, change=lambda w, m: w.append({"text": "fuera", "bbox": [105, 65, 110, 74]})
        )
        self.reject_before_generation(spec, "off_region_geometry_intersects_candidate")

    def test_wrong_column_sequence_not_sorted_away(self) -> Any:
        spec, _ = fixture(self.root)

        def mutate(a: Any) -> Any:
            a["regions"][0]["structural_evidence"]["columns"][1]["word_indices"].reverse()

        spec = self.changed_admission(spec, mutate)
        first = self.reject_before_generation(spec, "supplied_column_geometric_sequence_mismatch")
        check = first["geometry_checks"]["column_checks"][1]
        self.assertTrue(check["exact_membership_with_multiplicity"])
        self.assertFalse(check["exact_declared_geometric_sequence"])

    def test_missing_structural_metadata_abstains(self) -> Any:
        spec, _ = fixture(self.root)
        spec = self.changed_admission(
            spec, lambda a: a["regions"][0]["structural_evidence"].update(columns=[])
        )
        self.reject_before_generation(spec, "missing_supplied_column_geometry")

    def test_mixed_bad_region_only_clean_regional_generated(self) -> Any:
        spec, _ = fixture(
            self.root,
            ("priority", "regional"),
            change=lambda w, m: w[6].update(bbox=[100, 65, 280, 74]),
        )
        with (
            patch.object(c, "scoped_priority", wraps=c.scoped_priority) as pri,
            patch.object(c, "scoped_regional", wraps=c.scoped_regional) as reg,
        ):
            rc, out = self.execute(spec)
            self.assertEqual(rc, 0)
            self.assertEqual(pri.call_count, 0)
            self.assertEqual(reg.call_count, 1)
        cand = c.read(out / "composed_candidate.json")
        self.assertEqual([r["adapter"] for r in cand["results"]], ["regional"])
        bad = set(c.read(spec["admission"]["path"])["regions"][0]["word_indices"])
        self.assertFalse(
            bad.intersection(
                i
                for r in cand["results"]
                for row in r["rows"]
                for cell in row["cells"]
                for i in cell["word_indices"]
            )
        )
        TEST_EVENTS.append(
            {
                "test": self.id(),
                "measured_calls": {"priority": 0, "regional": 1},
                "rejected_word_leakage": 0,
            }
        )

    def test_duplicate_column_member_is_strict_input_error(self) -> Any:
        spec, _ = fixture(self.root)

        def mutate(a: Any) -> Any:
            col = a["regions"][0]["structural_evidence"]["columns"][0]
            col["word_indices"].append(col["word_indices"][0])

        spec = self.changed_admission(spec, mutate)
        with patch.object(
            c, "scoped_priority", side_effect=AssertionError("generation forbidden")
        ) as pri:
            rc, _ = self.execute(spec)
            self.assertEqual(rc, 2)
            self.assertEqual(pri.call_count, 0)

    def test_receive_only_has_fail_on_call_guards(self) -> Any:
        spec, _ = fixture(self.root)
        put(self.root / "receive_contract.json", spec)
        from peru_conflicts.execution import source_addressed_tables as engine

        with (
            patch.object(c, "scoped_priority", side_effect=AssertionError("forbidden")) as pri,
            patch.object(c, "scoped_regional", side_effect=AssertionError("forbidden")) as reg,
            patch.object(c, "compose", side_effect=AssertionError("forbidden")) as full,
            patch.object(engine, "run", side_effect=AssertionError("forbidden")) as common,
        ):
            rc = c.main(
                [
                    "--contract",
                    str(self.root / "receive_contract.json"),
                    "--receive-only",
                    "--output",
                    str(self.root / "receiving.json"),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(
                [pri.call_count, reg.call_count, full.call_count, common.call_count], [0, 0, 0, 0]
            )
        result = c.read(self.root / "receiving.json")
        self.assertEqual(result["decisions"][0]["decision"], "would_dispatch")
        self.assertFalse(result["executed"])
        self.assertTrue(all(v == 0 for v in result["generation_entry_attempts"].values()))
        self.assertNotIn("rows", result)
        TEST_EVENTS.append(
            {
                "test": self.id(),
                "receive_only_generation_attempts": result["generation_entry_attempts"],
                "eligible_region_executed": False,
            }
        )

    def test_actual_composition_generation_is_disabled(self) -> Any:
        spec, _ = fixture(self.root)
        spec["mode"] = "actual"
        spec["run_scope"] = {
            "allowed_operations": ["receive"],
            "allowed_adapters": [],
            "max_adapter_calls": 0,
            "max_engine_calls": 0,
        }
        with patch.object(
            c,
            "receive",
            side_effect=AssertionError("must not read actual input for full composition"),
        ) as receiver:
            rc, _ = self.execute(spec)
            self.assertEqual(rc, 2)
            self.assertEqual(receiver.call_count, 0)

    def test_transfer_both_routes_source_pointer_rebinding_and_engine(self) -> Any:
        spec, page = fixture(
            self.root, ("priority", "regional"), scale=1.5, dx=17, dy=23, reverse=True
        )
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        evidence = c.read(out / "source_word_evidence.json")["words"]
        for i, e in enumerate(evidence):
            self.assertEqual(e["source_pointer"], f"/words/{i}")
            self.assertEqual(e["span"], page["words"][i]["span"])
            self.assertEqual(page["text"][e["span"][0] : e["span"][1]], page["words"][i]["text"])
        from peru_conflicts.execution.native_documentary.profile import build
        from peru_conflicts.execution.source_addressed_tables import run

        put(out / "engine_config.json", build(out))
        rc = run(out / "engine_config.json", out / "engine_result.json")
        self.assertEqual(rc, 0)
        TEST_EVENTS.append(
            {
                "test": self.id(),
                "invented_translation_scale_reordered_serialization": True,
                "source_pointers_rebound": len(evidence),
                "engine_return_code": rc,
            }
        )

    def test_literal_zero_body_not_missing(self) -> Any:
        spec, _ = fixture(self.root, change=lambda w, m: w[5].update(text="0"))
        rc, out = self.execute(spec)
        self.assertEqual(rc, 0)
        cell = c.read(out / "composed_candidate.json")["results"][0]["rows"][0]["cells"][0]
        self.assertEqual(cell["status"], "processed")
        self.assertEqual(cell["value"], "0")

    def test_receive_only_accidental_priority_call_fails_and_counts(self) -> Any:
        spec, _ = fixture(self.root)
        put(self.root / "guard_contract.json", spec)

        def accident(view: Any) -> Any:
            return c.scoped_priority(view, spec)

        with patch.object(c, "qualify", side_effect=accident):
            self.assertEqual(
                c.main(
                    [
                        "--contract",
                        str(self.root / "guard_contract.json"),
                        "--receive-only",
                        "--output",
                        str(self.root / "guarded.json"),
                    ]
                ),
                2,
            )
        self.assertFalse((self.root / "guarded.json").exists())
        counts = c.read(self.root / "guarded.guard.json")["generation_entry_attempts"]
        self.assertEqual(counts["priority_wrapper"], 1)
        TEST_EVENTS.append(
            {"test": self.id(), "deliberate_invented_forbidden_entry_counted_and_failed": counts}
        )

    def test_receive_only_raw_and_engine_entry_sentinels_fail_visibly(self) -> Any:
        from peru_conflicts.execution import source_addressed_tables as engine

        actions: list[tuple[str, Callable[[Any], Any]]] = [
            ("priority_algorithm", lambda view: c.module("priority").discover(None, None, None)),
            (
                "regional_algorithm",
                lambda view: c.module("regional").adapt_page(None, None, None, None),
            ),
            (
                "regional_wrapper",
                lambda view: c.scoped_regional(None, cast("Json", None), cast("Path", None)),
            ),
            ("full_composition", lambda view: c.compose(cast("Json", None), cast("Path", None))),
            ("engine", lambda view: engine.run(cast("Path", None), cast("Path", None))),
        ]
        for n, (name, action) in enumerate(actions):
            folder = self.root / str(n)
            folder.mkdir()
            spec, _ = fixture(folder)
            put(folder / "contract.json", spec)
            output = folder / "receiving.json"
            with patch.object(c, "qualify", side_effect=action):
                self.assertEqual(
                    c.main(
                        [
                            "--contract",
                            str(folder / "contract.json"),
                            "--receive-only",
                            "--output",
                            str(output),
                        ]
                    ),
                    2,
                )
            self.assertFalse(output.exists())
            counts = c.read(output.with_suffix(".guard.json"))["generation_entry_attempts"]
            self.assertEqual(counts[name], 1)
            self.assertEqual(sum(counts.values()), 1)
            TEST_EVENTS.append(
                {
                    "test": self.id(),
                    "deliberate_invented_forbidden_entry": name,
                    "entry_counts": counts,
                    "real_generation_occurred": False,
                }
            )


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    if os.environ.get("NATIVE_TEST_EVIDENCE"):
        c.write(
            Path(os.environ["NATIVE_TEST_EVIDENCE"]),
            {
                "version": "V002_INVENTED_ACCEPTANCE_EVIDENCE",
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "events": TEST_EVENTS,
                "actual_source_calls": 0,
            },
        )
    raise SystemExit(not result.wasSuccessful())
