"""Invented receiving/storage contracts, never different-report source access."""

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any

from test_documentary_inspection import invented, repin_view

from peru_conflicts.inspection import builder, queries, validation


class AdditiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def union(self) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
        a, _, _ = invented(self.root / "A", 1, page=9, report="INVENTED_A")
        b, _, _ = invented(self.root / "B", 2, page=9, report="INVENTED_B")
        left = json.loads(a.read_bytes())
        right = json.loads(b.read_bytes())
        merged = {
            **left,
            "snapshot_version": "INVENTED_ADDITIVE_UNION_V001",
            "documents": left["documents"] + right["documents"],
            "views": left["views"] + right["views"],
        }
        union = self.root / "union.json"
        union.write_text(json.dumps(merged), encoding="utf-8")
        return a, union, left, right

    def test_additive_union_preserves_every_existing_unit_record(self) -> None:
        a, union, left, _ = self.union()
        first = self.root / "A.sqlite"
        both = self.root / "AB.sqlite"
        builder.build_snapshot(a, first)
        builder.build_snapshot(union, both)
        with closing(sqlite3.connect(first)) as ca, closing(sqlite3.connect(both)) as cb:
            for table in [
                "units",
                "documentary_rows",
                "cells",
                "row_cells",
                "documentary_columns",
                "contexts",
                "qualifiers",
                "dependencies",
                "owner_words",
                "assertions",
                "assertion_links",
            ]:
                original = ca.execute("SELECT * FROM " + table).fetchall()
                combined = cb.execute("SELECT * FROM " + table).fetchall()
                self.assertTrue(all(row in combined for row in original), table)
            self.assertEqual(cb.execute("SELECT count(*) FROM v_body_rows").fetchone()[0], 4)
            self.assertEqual(cb.execute("SELECT count(*) FROM v_body_cells").fetchone()[0], 12)
            self.assertEqual(
                cb.execute("SELECT count(DISTINCT native_sha256) FROM units").fetchone()[0], 2
            )
            self.assertEqual(
                cb.execute("SELECT count(*) FROM units WHERE physical_page=9").fetchone()[0], 2
            )
            uid = left["views"][0]["sha256"]
            self.assertEqual(
                cb.execute("SELECT count(*) FROM contexts WHERE unit_key=?", (uid,)).fetchone()[0],
                1,
            )
        self.assertTrue(validation.validate(both, union)["success"])

    def test_shared_identical_documents_keep_both_purposes(self) -> None:
        _, union, left, right = self.union()
        merged = json.loads(union.read_bytes())
        shared = next(
            x["sha256"]
            for x in left["documents"]
            if x["sha256"] in {r["sha256"] for r in right["documents"]}
        )
        for document in merged["documents"][: len(left["documents"])]:
            if document["sha256"] == shared:
                document["purposes"] = ["invented report A"]
        for document in merged["documents"][len(left["documents"]) :]:
            if document["sha256"] == shared:
                document["purposes"] = ["invented report B"]
        union.write_text(json.dumps(merged), encoding="utf-8")
        out = self.root / "shared.sqlite"
        builder.build_snapshot(union, out)
        with closing(sqlite3.connect(out)) as c:
            records = c.execute(
                "SELECT raw_bytes,purposes_json FROM documents WHERE sha256=?", (shared,)
            ).fetchall()
            self.assertEqual(len(records), 1)
            self.assertEqual(json.loads(records[0][1]), ["invented report A", "invented report B"])
            self.assertEqual(hashlib.sha256(records[0][0]).hexdigest(), shared)

    def test_duplicate_selected_view_is_rejected_not_counted_twice(self) -> None:
        m, _, _ = invented(self.root / "i")
        manifest = json.loads(m.read_bytes())
        manifest["views"] *= 2
        m.write_text(json.dumps(manifest), encoding="utf-8")
        out = self.root / "duplicate.sqlite"
        with self.assertRaisesRegex(ValueError, "duplicate selected view"):
            builder.build_snapshot(m, out)
        self.assertFalse(out.exists())

    def test_overlapping_cell_views_fail_without_replacing_records(self) -> None:
        m, v, d = invented(self.root / "i")
        v["provenance"]["extra"] = "invented alternative view"
        repin_view(m, v, d)
        changed = json.loads(m.read_bytes())
        # The first frozen view is a separate fixture, never a mutation of its source.
        other, _, _ = invented(self.root / "first")
        original_doc = json.loads(other.read_bytes())
        changed["documents"] += original_doc["documents"]
        changed["views"] += original_doc["views"]
        m.write_text(json.dumps(changed), encoding="utf-8")
        out = self.root / "overlap.sqlite"
        with self.assertRaisesRegex(ValueError, "overlapping original cell"):
            builder.build_snapshot(m, out)
        self.assertFalse(out.exists())

    def test_wrong_optional_record_hash_is_not_unresolved(self) -> None:
        m, v, d = invented(self.root / "i")
        v["dependencies"][0]["evidence_refs"][0]["record_sha256"] = "0" * 64
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "historical record hash mismatch"):
            builder.build_snapshot(m, self.root / "bad.sqlite")

    def test_manifest_relative_locations_are_not_working_directory_relative(self) -> None:
        m, _, _ = invented(self.root / "i")
        obj = json.loads(m.read_bytes())
        for document in obj["documents"]:
            document["path"] = Path(document["path"]).name
        m.write_text(json.dumps(obj), encoding="utf-8")
        out = self.root / "relative.sqlite"
        builder.build_snapshot(m, out)
        self.assertTrue(validation.validate(out, m)["success"])

    def test_unsupported_shape_does_not_publish(self) -> None:
        m, v, d = invented(self.root / "i")
        v["version"] = "UNSUPPORTED_INVENTED_SHAPE"
        repin_view(m, v, d)
        out = self.root / "unsupported.sqlite"
        with self.assertRaisesRegex(ValueError, "unsupported view"):
            builder.build_snapshot(m, out)
        self.assertFalse(out.exists())

    def test_column_scope_role_mismatch_fails(self) -> None:
        m, v, d = invented(self.root / "i", 1)
        v["qualifiers"][0]["target"]["column_index"] = 0
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "qualifier.*role|role.*scope"):
            builder.build_snapshot(m, self.root / "scope.sqlite")

    def test_duplicate_column_identity_is_rejected(self) -> None:
        m, v, d = invented(self.root / "i")
        v["columns"][1]["id"] = v["columns"][0]["id"]
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "column"):
            builder.build_snapshot(m, self.root / "columns.sqlite")

    def test_declared_column_index_cannot_replace_original_cell_index(self) -> None:
        m, v, d = invented(self.root / "i")
        v["columns"][0]["source_index"] = 8
        repin_view(m, v, d)
        with self.assertRaisesRegex(ValueError, "original cell/source column index"):
            builder.build_snapshot(m, self.root / "index.sqlite")

    def test_multi_segment_query_uses_ordinal_not_insertion_order(self) -> None:
        m, v, d = invented(self.root / "i")
        anchor0 = v["original_word_anchors"]["0"]
        anchor1 = v["original_word_anchors"]["1"]
        v["context_node"]["source_segments"] = [
            {
                "word_indices": [i],
                "word_addresses": [anchor["source_address"]],
                "own_text_span": anchor["span"],
                "exact_text": anchor["text"],
                "span_frame": "/text",
            }
            for i, anchor in [(1, anchor1), (0, anchor0)]
        ]
        repin_view(m, v, d)
        out = self.root / "segments.sqlite"
        builder.build_snapshot(m, out)
        with closing(sqlite3.connect(out)) as c:
            rows = c.execute("SELECT * FROM segments ORDER BY ordinal DESC").fetchall()
            c.execute("DELETE FROM segments")
            c.executemany("INSERT INTO segments VALUES(?,?,?,?,?,?)", rows)
            c.commit()
        self.assertEqual(queries.query(out, "priority")[0]["introduction_literal"], "scope\nIntro")

    def test_optimizer_cannot_claim_successful_validation(self) -> None:
        m, _, _ = invented(self.root / "i")
        out = self.root / "safe.sqlite"
        builder.build_snapshot(m, out)
        source = Path(builder.__file__).resolve().parents[2]
        code = (
            "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
            "from peru_conflicts.inspection.validation import validate;"
            "validate(Path(sys.argv[2]),Path(sys.argv[3]))"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-O", "-c", code, str(source), str(out), str(m)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("optimized Python", result.stderr)

    def test_conflicting_reuse_of_native_word_evidence_is_explicitly_rejected(self) -> None:
        a, _, _ = invented(self.root / "A", 1)
        b, _, _ = invented(self.root / "B", 2)
        left = json.loads(a.read_bytes())
        right = json.loads(b.read_bytes())
        merged = {
            **left,
            "documents": left["documents"] + right["documents"],
            "views": left["views"] + right["views"],
        }
        a.write_text(json.dumps(merged), encoding="utf-8")
        out = self.root / "conflict.sqlite"
        with self.assertRaisesRegex(ValueError, "incompatible repeated native-word evidence"):
            builder.build_snapshot(a, out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
