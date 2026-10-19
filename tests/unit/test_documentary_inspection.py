"""Invented records only; ordinary independent unittest identities, no subTest."""

import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from peru_conflicts.inspection import builder
from peru_conflicts.inspection import exports as exporter
from peru_conflicts.inspection import queries as reader
from peru_conflicts.inspection import validation as validator

HERE = Path(__file__).resolve().parent


def packed(value: Any) -> Any:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: Any) -> Any:
    return hashlib.sha256(packed(value).encode()).hexdigest()


def invented(
    folder: Any,
    version: Any = 2,
    page: Any = 9,
    missing_value: Any = False,
    report: str = "INVENTED_A",
) -> Any:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    strings = [
        "Intro",
        "scope",
        "Lugar",
        "Caso",
        "Situación",
        "Nº",
        "1.",
        "2.",
        "Same",
        "word",
        "new",
        "Same",
        "word",
        "new",
    ]
    words: list[dict[str, Any]] = []
    cursor = 0
    for i, s in enumerate(strings):
        words.append({"text": s, "span": [cursor, cursor + len(s)], "bbox": [i, 0, i + 1, 1]})
        cursor += len(s) + 1
    native: dict[str, Any] = {
        "report_identity": report,
        "physical_page": page,
        "width": 100,
        "height": 100,
        "text": " ".join(strings),
        "words": words,
        "layout_lines": [{"words": words}],
    }
    docs: dict[str, tuple[str, Path]] = {}

    def put(name: Any, value: Any) -> Any:
        raw = json.dumps(value, ensure_ascii=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        p = folder / (name + ".json")
        p.write_bytes(raw)
        docs[name] = (sha, p)
        return sha

    ns = put("native", native)
    values = [None, "", 0, False, "0", 'New\nquoted "á"']
    legacy: list[dict[str, Any]] = []
    groups = [
        {"row_id": "header", "row_kind": "printed_header", "ordered_cell_ids": ["h0", "h1", "h2"]}
    ]
    for i in range(3):
        legacy.append(
            {
                "cell_id": "h" + str(i),
                "row_id": "header",
                "row_kind": "printed_header",
                "column_index": i,
                "word_indices": [2 + i],
                "value_inherited_unchanged": strings[2 + i],
            }
        )
    rows: list[dict[str, Any]] = []
    for r in range(2):
        cells: list[dict[str, Any]] = []
        for c in range(3):
            cell: dict[str, Any] = {
                "column_index": c + 1,
                "word_indices": [8 + r * 3 + c],
                "value": values[r * 3 + c],
                "status": "inherited",
                "extra": {"zero": 0, "false": False, "null": None},
            }
            if missing_value and r == 0 and c == 0:
                cell.pop("value")
            cells.append(cell)
            legacy.append(
                {
                    "cell_id": f"r{r}c{c}",
                    "row_id": "same-local-label",
                    "row_kind": "published_total" if r == 0 else "category",
                    "column_index": c,
                    "word_indices": [8 + r * 3 + c],
                    "value_inherited_unchanged": values[r * 3 + c],
                }
            )
        rows.append(
            {"row_id": "same-local-label", "role": "primary", "status": "inherited", "cells": cells}
        )
        groups.append(
            {
                "row_id": "same-local-label",
                "row_kind": "published_total" if r == 0 else "category",
                "ordered_cell_ids": [f"r{r}c{c}" for c in range(3)],
            }
        )
    proposal: dict[str, Any] = {
        "native_sha256": ns,
        "rows": rows,
        "inherited_cells": legacy,
        "inherited_grouping": groups,
        "word_evidence": {str(i): w for i, w in enumerate(words)},
        "header": {"word_indices": [2, 3, 4, 5]},
        "ordinals": [{"word_index": 6}, {"word_index": 7}],
    }
    ps = put("proposal", proposal)
    assertion = {
        "status": "exposed_AI_interpretation",
        "attribution": "Codex AI",
        "stage": "invented_attachment",
        "human_reviewed": False,
        "context_segments": [[0, 1]],
        "claim": "Invented context support",
    }
    aps = put(
        "assertions",
        {
            "attachment": assertion,
            "dependency": {"status": "unknown", "attribution": "invented evidence"},
        },
    )

    def address(sha: str, p: str) -> str:
        return "sha256:" + sha + "#" + p

    anchors: dict[str, Any] = {}
    selected = list(range(14)) if version == 2 else [0, 1, 2, 3, 4, *range(8, 14)]
    for i in selected:
        anchors[str(i)] = {
            "source_address": address(ns, "/words/" + str(i)),
            "word_index": i,
            **words[i],
            "layout_pointers": ["/layout_lines/0/words/" + str(i)],
            "evidence_address": address(ns, "/words/" + str(i)),
        }
    segment = {
        "word_indices": [0, 1],
        "word_addresses": [address(ns, "/words/0"), address(ns, "/words/1")],
        "own_text_span": [0, words[1]["span"][1]],
        "exact_text": "Intro scope",
        "span_frame": "/text",
    }
    ref = dict(assertion, source_address=address(aps, "/attachment"))
    permissions = {
        "inspection": True,
        "normalization": False,
        "automatic_dispatch": False,
        "scientific_acceptance": False,
        "benchmark_scoring": False,
    }
    view: dict[str, Any] = {
        "version": "SOURCE_BOUND_CONTEXT_ATTACHMENT_V00" + str(version),
        "source": {
            "native_sha256": ns,
            "pdf_sha256": hashlib.sha256(report.encode()).hexdigest(),
            "physical_page": page,
            "width": 100,
            "height": 100,
            "frame": "invented original native frame",
        },
        "created_by": "Codex AI",
        "context_node": {"non_cell": True, "source_segments": [segment]},
        "original_word_anchors": anchors,
        "permissions": permissions,
        "provenance": {
            "cells": "inherited exposed AI",
            "owner_personal_source_rechecking": False,
            "production_no_dispatch_changed": False,
            "execution_authority": "owner execution only",
        },
        "alternative_universe_complete": False,
        "dependencies": [
            {
                "name": "unknown_scope",
                "state": "unknown",
                "evidence_refs": [{"source_address": address(aps, "/dependency")}],
            }
        ],
    }
    if version == 1:
        view.update(
            inherited_cells=legacy,
            inherited_grouping=groups,
            inherited_grouping_address=address(ps, "/inherited_grouping"),
            inherited_word_evidence_address=address(ps, "/word_evidence"),
            cell_references=[
                {
                    "source_address": address(ps, "/inherited_cells/" + str(i)),
                    "record_sha256": digest(c),
                }
                for i, c in enumerate(legacy)
            ],
            attachment_assertions={"assertions": [ref], "human_reviewed": False},
        )
        view["qualifiers"] = [
            {
                "kind": "count_unit",
                "target": {"kind": "column", "column_index": 1, "role": "count"},
                "source_segments": [segment],
                "display_text": "Intro … scope",
                "display_is_contiguous_source_quote": False,
                "applicability": {"assertions": [ref], "human_reviewed": False},
                "resolution": "attached_for_inspection_only",
            }
        ]
    else:
        view["context_node"]["kind"] = "introductory_paragraph"
        view["columns"] = [
            {"id": name, "source_index": i + 1, "role": role, "display_label": name}
            for i, (name, role) in enumerate(
                [
                    ("place", "place_text"),
                    ("case", "case_description"),
                    ("situation", "published_situation"),
                ]
            )
        ]
        view["cell_references"] = [
            {
                "descriptor_id": f"c{r}-{c}",
                "row_descriptor_id": "r" + str(r),
                "column_id": view["columns"][c]["id"],
                "source_address": address(ps, f"/rows/{r}/cells/{c}"),
                "record_sha256": digest(rows[r]["cells"][c]),
                "word_indices": rows[r]["cells"][c]["word_indices"],
                **(
                    {"display_value_inherited": rows[r]["cells"][c]["value"]}
                    if "value" in rows[r]["cells"][c]
                    else {}
                ),
            }
            for r in range(2)
            for c in range(3)
        ]
        view["row_references"] = [
            {
                "descriptor_id": "r" + str(r),
                "source_address": address(ps, "/rows/" + str(r)),
                "record_sha256": digest(row),
                "ordered_cell_descriptor_ids": [f"c{r}-{c}" for c in range(3)],
            }
            for r, row in enumerate(rows)
        ]
        view["documentary_metadata"] = [
            {
                "kind": "header",
                "source_address": address(ps, "/header"),
                "record_sha256": digest(proposal["header"]),
                "word_indices": [2, 3, 4, 5],
            }
        ] + [
            {
                "kind": "ordinal",
                "source_address": address(ps, "/ordinals/" + str(i)),
                "record_sha256": digest(proposal["ordinals"][i]),
                "word_indices": [6 + i],
            }
            for i in range(2)
        ]
        view["attachment_assertions"] = [ref]
        view["qualifiers"] = [
            {
                "kind": "introductory_scope",
                "target": {"kind": "table_proposal"},
                "source_segments": [segment],
                "display_text": "Intro scope",
                "display_is_contiguous_source_quote": True,
                "applicability": [ref],
                "resolution": "attached_for_inspection_only",
            }
        ]
    request: dict[str, Any] = {"column_roles": {"category": 0, "count": 1, "percentage": 2}}
    req = put("request", request)
    vs = put("view", view)
    manifest: dict[str, Any] = {
        "snapshot_version": "INVENTED_DOCUMENTARY_SNAPSHOT_V001",
        "projection_version": "DOCUMENTARY_SQLITE_PROJECTION_V001",
        "documents": [
            {"sha256": s, "path": str(p), "purposes": ["invented"]} for s, p in docs.values()
        ],
        "views": [{"sha256": vs, "request_sha256": req, "label": "invented"}],
        "authorship": {"new_import": "Codex AI", "owner": "execution authority only"},
    }
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, view, docs


def repin_view(path: Any, view: Any, docs: Any) -> None:
    manifest: dict[str, Any] = json.loads(path.read_bytes())
    old = manifest["views"][0]["sha256"]
    raw = json.dumps(view, ensure_ascii=False).encode()
    new = hashlib.sha256(raw).hexdigest()
    docs["view"][1].write_bytes(raw)
    for item in manifest["documents"]:
        if item["sha256"] == old:
            item["sha256"] = new
    manifest["views"][0]["sha256"] = new
    path.write_text(json.dumps(manifest), encoding="utf-8")


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, version: Any = 2, **kw: Any) -> Any:
        m, v, d = invented(self.folder / "inputs", version, **kw)
        out = self.folder / "snapshot.sqlite"
        builder.build_snapshot(m, out)
        return sqlite3.connect(out), m, v, d, out

    def test_regional_scope_headers_and_duplicate_local_labels(self) -> None:
        c, _, _, _, _ = self.build(1)
        self.assertEqual(
            c.execute("SELECT count(*) FROM documentary_rows WHERE row_class='body'").fetchone()[0],
            2,
        )
        self.assertEqual(
            c.execute("SELECT count(*) FROM cells WHERE cell_class='header'").fetchone()[0], 3
        )
        self.assertEqual(
            c.execute("SELECT DISTINCT column_role FROM v_cell_qualifiers").fetchall(), [("count",)]
        )
        c.close()

    def test_priority_no_dummy_numeric_roles_and_metadata_separate(self) -> None:
        c, _, _, _, _ = self.build()
        self.assertEqual(c.execute("SELECT count(*) FROM v_body_rows").fetchone()[0], 2)
        self.assertEqual(c.execute("SELECT count(*) FROM v_body_cells").fetchone()[0], 6)
        self.assertEqual(
            c.execute(
                "SELECT count(*) FROM metadata_words mw JOIN documentary_metadata m "
                "USING(metadata_key) WHERE m.kind='header'"
            ).fetchone()[0],
            4,
        )
        self.assertEqual(
            c.execute("SELECT count(*) FROM documentary_metadata WHERE kind='ordinal'").fetchone()[
                0
            ],
            2,
        )
        c.close()

    def test_types_presence_and_full_record_roundtrip(self) -> None:
        c, _, _, _, _ = self.build()
        values = c.execute("SELECT value_type,value_json FROM cells ORDER BY cell_key").fetchall()
        self.assertEqual(
            values,
            [
                ("null", "null"),
                ("string", '""'),
                ("number", "0"),
                ("boolean", "false"),
                ("string", '"0"'),
                ("string", '"New\\nquoted \\"á\\""'),
            ],
        )
        self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        for (payload,) in c.execute("SELECT payload_json FROM source_records"):
            self.assertIsInstance(
                json.loads(payload), (dict, list, str, int, float, bool, type(None))
            )
        row = json.loads(
            c.execute(
                "SELECT payload_json FROM source_records WHERE pointer='/rows/0/cells/0'"
            ).fetchone()[0]
        )
        self.assertNotIn("optional_absent", row)
        self.assertIsNone(row["extra"]["null"])
        self.assertIs(row["extra"]["false"], False)
        c.close()

    def test_wrong_hash_rejected(self) -> None:
        m, _, _ = invented(self.folder / "i")
        doc = json.loads(m.read_bytes())
        doc["documents"][0]["sha256"] = "0" * 64
        m.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "hash"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_negative_pointer_rejected(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["cell_references"][0]["source_address"] = (
            "sha256:" + d["proposal"][0] + "#/rows/-1/cells/0"
        )
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "pointer"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_missing_required_binding_rejected(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["cell_references"][0]["source_address"] = "sha256:" + d["proposal"][0] + "#/missing"
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "pointer"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_missing_required_value_rejected(self) -> None:
        m, _, _ = invented(self.folder / "i", missing_value=True)
        with self.assertRaisesRegex(ValueError, "required value"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_grouping_conflict_rolls_back(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["row_references"][0]["ordered_cell_descriptor_ids"].reverse()
        repin_view(m, v, d)
        out = self.folder / "bad.sqlite"
        with self.assertRaisesRegex(ValueError, "grouping"):
            builder.build_snapshot(m, out)
        if out.exists():
            c = sqlite3.connect(out)
            self.assertEqual(
                c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0], 0
            )
            c.close()

    def test_permission_upgrade_rejected(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["permissions"]["scientific_acceptance"] = True
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "permission"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_owner_authority_does_not_promote_human_review(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["provenance"]["owner_personal_source_rechecking"] = True
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "human"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_empty_selected_inventory_not_silently_accepted(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["cell_references"] = []
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "empty"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_optional_context_is_explicitly_unresolved(self) -> None:
        m, v, d = invented(self.folder / "i", 1)
        v["linked_contextual_limits"] = [{"source_address": "sha256:" + "0" * 64 + "#/unknown"}]
        repin_view(m, v, d)
        out = self.folder / "ok.sqlite"
        builder.build_snapshot(m, out)
        c = sqlite3.connect(out)
        self.assertEqual(c.execute("SELECT count(*) FROM unresolved_references").fetchone()[0], 1)
        c.close()

    def test_existing_output_never_overwritten(self) -> None:
        m, _, _ = invented(self.folder / "i")
        out = self.folder / "old.sqlite"
        out.write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            builder.build_snapshot(m, out)
        self.assertEqual(out.read_bytes(), b"original")

    def test_independent_roundtrip_validator_priority(self) -> None:
        c, m, _, _, out = self.build()
        c.close()
        result = validator.validate(out, m)
        self.assertTrue(result["success"])
        self.assertEqual(result["accounting"]["body_cells"], 6)
        self.assertTrue(result["read_only_hash_unchanged"])

    def test_independent_roundtrip_validator_regional(self) -> None:
        c, m, _, _, out = self.build(1)
        c.close()
        result = validator.validate(out, m)
        self.assertEqual(result["accounting"]["header_cells"], 3)

    def test_validator_rejects_tampered_projection(self) -> None:
        c, m, _, _, out = self.build()
        c.execute("UPDATE cells SET value_json='false' WHERE value_type='null'")
        c.commit()
        c.close()
        with self.assertRaises(AssertionError):
            validator.validate(out, m)

    def test_query_reader_parameterization_and_sealed_hash(self) -> None:
        c, _, _, _, out = self.build()
        c.close()
        before = out.read_bytes()
        self.assertEqual(len(reader.query(out, "priority")), 2)
        self.assertEqual(reader.query(out, "trace", "not-an-address' OR 1=1 --"), [])
        self.assertEqual(out.read_bytes(), before)
        connection = sqlite3.connect(out.resolve().as_uri() + "?mode=ro", uri=True)
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("DELETE FROM cells")
        connection.close()

    def test_two_units_duplicate_labels_do_not_merge(self) -> None:
        m1, _, _ = invented(self.folder / "one", 1)
        m2, _, _ = invented(self.folder / "two", 2, report="INVENTED_B")
        a = json.loads(m1.read_bytes())
        b = json.loads(m2.read_bytes())
        a["views"] += b["views"]
        a["documents"] = list({x["sha256"]: x for x in a["documents"] + b["documents"]}.values())
        m1.write_text(json.dumps(a), encoding="utf-8")
        out = self.folder / "both.sqlite"
        builder.build_snapshot(m1, out)
        result = validator.validate(out, m1)
        self.assertEqual(result["accounting"]["units"], 2)
        self.assertEqual(result["accounting"]["body_rows"], 4)
        self.assertEqual(result["accounting"]["body_cells"], 12)

    def test_root_escaped_and_noncanonical_pointer_boundaries(self) -> None:
        obj = {"a/b": {"~key": [False, None]}}
        self.assertIs(builder.pointer(obj, ""), obj)
        self.assertIs(builder.pointer(obj, "/a~1b/~0key/0"), False)
        with self.assertRaisesRegex(ValueError, "pointer"):
            builder.pointer(obj, "/a~1b/~0key/01")

    def test_authored_human_metadata_not_promoted(self) -> None:
        m, v, d = invented(self.folder / "i")
        v["attachment_assertions"][0]["human_reviewed"] = True
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "human"):
            builder.build_snapshot(m, self.folder / "bad.sqlite")

    def test_all_distinct_dependency_states_survive(self) -> None:
        m, v, d = invented(self.folder / "i")
        states = [
            "unknown",
            "confirmed_none",
            "reported_empty",
            "absent_field",
            "unreviewed_interpretation",
        ]
        v["dependencies"] = [
            dict(v["dependencies"][0], name="invented_" + state, state=state) for state in states
        ]
        repin_view(m, v, d)
        out = self.folder / "all-states.sqlite"
        builder.build_snapshot(m, out)
        self.assertEqual([x["state"] for x in reader.query(out, "dependencies")], states)
        self.assertTrue(validator.validate(out, m)["success"])

    def test_qualifier_literal_can_reference_original_header_outside_caption(self) -> None:
        m, v, d = invented(self.folder / "i", 1)
        anchor = v["original_word_anchors"]["4"]
        segment = {
            "word_indices": [4],
            "word_addresses": [anchor["source_address"]],
            "own_text_span": anchor["span"],
            "exact_text": anchor["text"],
            "span_frame": "/text",
        }
        v["qualifiers"][0].update(
            kind="percentage_sign",
            target={"kind": "column", "column_index": 2, "role": "percentage"},
            source_segments=[segment],
            display_text=anchor["text"],
            display_is_contiguous_source_quote=True,
        )
        repin_view(m, v, d)
        out = self.folder / "header-qualifier.sqlite"
        builder.build_snapshot(m, out)
        self.assertTrue(validator.validate(out, m)["success"])
        c = sqlite3.connect(out)
        self.assertEqual(
            c.execute("SELECT DISTINCT column_role FROM v_cell_qualifiers").fetchall(),
            [("percentage",)],
        )
        c.close()

    def test_failed_exclusive_publication_reports_partial_file(self) -> None:
        m, _, _ = invented(self.folder / "i")
        out = self.folder / "partial.sqlite"
        with (
            mock.patch.object(
                builder.shutil, "copyfileobj", side_effect=OSError("invented write failure")
            ),
            self.assertRaisesRegex(OSError, "actual output=.*bytes=0"),
        ):
            builder.build_snapshot(m, out)
        self.assertTrue(out.exists())
        self.assertEqual(out.read_bytes(), b"")
        with self.assertRaises(FileExistsError):
            builder.build_snapshot(m, out)

    def test_csv_and_html_convenience_exports_preserve_raw_strings(self) -> None:
        c, _, _, _, out = self.build()
        c.close()
        folder = self.folder / "exports"
        folder.mkdir()
        before = out.read_bytes()
        result = exporter.export(out, folder)
        with (folder / "cells_long_utf8.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 6)
        self.assertEqual(json.loads(rows[-1]["value_json"]), 'New\nquoted "á"')
        self.assertIn(
            "New<br>quoted &quot;á&quot;",
            (folder / "inspection_overview.html").read_text(encoding="utf-8"),
        )
        self.assertEqual(result["query_counts"]["priority"], 2)
        self.assertEqual(out.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
