"""Invented qualifier/metadata boundaries; ordinary independent collected cases."""

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from test_documentary_inspection import invented, repin_view

from peru_conflicts.inspection import builder, cli, queries, validation


class ScopeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def valid(self, version: int = 1) -> tuple[Path, Path]:
        manifest, _, _ = invented(self.root / "inputs", version)
        output = self.root / "valid.sqlite"
        builder.build_snapshot(manifest, output)
        self.assertTrue(validation.validate(output, manifest)["success"])
        return manifest, output

    def reject_input(self, version: int, target: Any, kind: str | None = None) -> None:
        manifest, view, docs = invented(self.root / "inputs", version)
        view["qualifiers"][0]["target"] = target
        if kind is not None:
            view["qualifiers"][0]["kind"] = kind
        repin_view(manifest, view, docs)
        before = {str(p): p.read_bytes() for _, p in docs.values()}
        output = self.root / "rejected.sqlite"
        with self.assertRaisesRegex(ValueError, "qualifier_scope"):
            builder.build_snapshot(manifest, output)
        self.assertFalse(output.exists())
        self.assertEqual(before, {str(p): p.read_bytes() for _, p in docs.values()})

    def mutate(self, output: Path, sql: str, args: tuple[Any, ...] = ()) -> None:
        with closing(sqlite3.connect(output)) as connection:
            connection.execute(sql, args)
            connection.commit()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def reject_validation(self, manifest: Path, output: Path, reason: str) -> None:
        before = hashlib.sha256(output.read_bytes()).hexdigest()
        with self.assertRaisesRegex((AssertionError, ValueError), reason):
            validation.validate(output, manifest)
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), before)

    def permission_case(self, key: str | None, value: Any, remove: bool = False) -> None:
        manifest, output = self.valid()
        with closing(sqlite3.connect(output)) as connection:
            permissions = json.loads(
                connection.execute(
                    "SELECT value_json FROM snapshot_metadata WHERE key='permissions'"
                ).fetchone()[0]
            )
        if key is None:
            permissions.update(
                normalization=True,
                automatic_dispatch=True,
                scientific_acceptance=True,
                benchmark_scoring=True,
            )
        elif remove:
            del permissions[key]
        else:
            permissions[key] = value
        self.mutate(
            output,
            "UPDATE snapshot_metadata SET value_json=? WHERE key='permissions'",
            (json.dumps(permissions),),
        )
        self.reject_validation(manifest, output, "snapshot_metadata")
        emitted = [
            json.loads(r["value_json"])
            for r in queries.query(output, "limits")
            if r["key"] == "permissions"
        ]
        self.assertEqual(emitted, [permissions])  # Reject, never sanitize inspected bytes.

    def test_A_regional_count_cannot_target_category(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": 0, "role": "category"})

    def test_B_priority_intro_cannot_target_place(self) -> None:
        self.reject_input(
            2, {"kind": "column", "column_index": 1, "column_id": "place", "role": "place_text"}
        )

    def test_C_original_target_cannot_be_broadened_to_table(self) -> None:
        manifest, output = self.valid()
        self.mutate(
            output,
            "UPDATE qualifiers SET target_kind='table_proposal',"
            "target_column=NULL WHERE kind='count_unit'",
        )
        with closing(sqlite3.connect(output)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT DISTINCT column_role FROM v_cell_qualifiers ORDER BY column_role"
                ).fetchall(),
                [("category",), ("count",), ("percentage",)],
            )
        self.reject_validation(manifest, output, "qualifier_projection")

    def test_D_all_snapshot_permissions_cannot_be_promoted(self) -> None:
        self.permission_case(None, True)

    def test_wrong_same_unit_column_is_rejected(self) -> None:
        manifest, output = self.valid()
        self.mutate(
            output,
            "UPDATE qualifiers SET target_column=(SELECT column_key FROM "
            "documentary_columns WHERE column_role='category') WHERE kind='count_unit'",
        )
        self.reject_validation(manifest, output, "qualifier_projection")

    def test_foreign_unit_column_is_rejected(self) -> None:
        a, _, _ = invented(self.root / "A", 1, report="INVENTED_A")
        b, _, _ = invented(self.root / "B", 1, report="INVENTED_B")
        left, right = json.loads(a.read_bytes()), json.loads(b.read_bytes())
        left["documents"] += right["documents"]
        left["views"] += right["views"]
        a.write_text(json.dumps(left), encoding="utf-8")
        output = self.root / "union.sqlite"
        builder.build_snapshot(a, output)
        self.assertTrue(validation.validate(output, a)["success"])
        first, second = [s["sha256"] for s in left["views"]]
        self.mutate(
            output,
            "UPDATE qualifiers SET target_column=(SELECT column_key FROM "
            "documentary_columns WHERE unit_key=? AND column_role='count') WHERE unit_key=?",
            (second, first),
        )
        self.reject_validation(a, output, "qualifier_projection")

    def test_wrong_qualifier_ordinal_is_rejected(self) -> None:
        manifest, output = self.valid()
        self.mutate(output, "UPDATE qualifiers SET ordinal=99")
        self.reject_validation(manifest, output, "qualifier_projection")

    def test_wrong_qualifier_kind_is_rejected(self) -> None:
        manifest, output = self.valid()
        self.mutate(output, "UPDATE qualifiers SET kind='subject'")
        self.reject_validation(manifest, output, "qualifier_projection")

    def test_count_column_id_cannot_conflict_with_index(self) -> None:
        self.reject_input(
            1, {"kind": "column", "column_index": 1, "column_id": "category", "role": "count"}
        )

    def test_count_target_boolean_index_is_not_integer(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": True, "role": "count"})

    def test_count_target_float_index_is_not_integer(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": 1.0, "role": "count"})

    def test_count_target_string_index_is_not_integer(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": "1", "role": "count"})

    def test_count_cannot_target_percentage(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": 2, "role": "percentage"})

    def test_percentage_cannot_target_count(self) -> None:
        self.reject_input(
            1, {"kind": "column", "column_index": 1, "role": "count"}, "percentage_sign"
        )

    def valid_target(
        self, version: int, kind: str, target: Any, resolution: str = "attached_for_inspection_only"
    ) -> None:
        manifest, view, docs = invented(self.root / "inputs", version)
        view["qualifiers"][0].update(kind=kind, target=target, resolution=resolution)
        repin_view(manifest, view, docs)
        output = self.root / "positive.sqlite"
        builder.build_snapshot(manifest, output)
        self.assertTrue(validation.validate(output, manifest)["success"])
        with closing(sqlite3.connect(output)) as connection:
            scopes = connection.execute(
                "SELECT DISTINCT column_role FROM v_cell_qualifiers ORDER BY column_role"
            ).fetchall()
        expected = (
            [("count",)]
            if kind == "count_unit" and target is not None
            else [("percentage",)]
            if kind == "percentage_sign"
            else [
                (r,)
                for r in (
                    ["category", "count", "percentage"]
                    if version == 1
                    else ["case_description", "place_text", "published_situation"]
                )
            ]
            if target is not None and target["kind"] == "table_proposal"
            else []
        )
        self.assertEqual(scopes, expected)

    def test_valid_regional_count_target(self) -> None:
        self.valid_target(1, "count_unit", {"kind": "column", "column_index": 1, "role": "count"})

    def test_valid_regional_percentage_target(self) -> None:
        self.valid_target(
            1, "percentage_sign", {"kind": "column", "column_index": 2, "role": "percentage"}
        )

    def test_valid_regional_subject_table_target(self) -> None:
        self.valid_target(1, "subject", {"kind": "table_proposal"})

    def test_valid_regional_period_table_target(self) -> None:
        self.valid_target(1, "reporting_period", {"kind": "table_proposal"})

    def test_valid_regional_organization_has_no_body_cell_edge(self) -> None:
        self.valid_target(1, "geographic_breakdown", {"kind": "reported_organization"})

    def test_valid_priority_intro_table_target(self) -> None:
        self.valid_target(2, "introductory_scope", {"kind": "table_proposal"})

    def test_valid_priority_documentary_table_target(self) -> None:
        self.valid_target(2, "documentary_scope", {"kind": "table_proposal"})

    def test_missing_support_preserves_explicit_no_edge(self) -> None:
        self.valid_target(1, "count_unit", None, "unresolved_missing_semantic_support")

    def test_unknown_kind_preserves_explicit_no_edge(self) -> None:
        self.valid_target(2, "invented_unsupported", None, "unresolved_unsupported_attachment")

    def test_unresolved_label_cannot_authorize_malformed_active_scope(self) -> None:
        self.reject_input(1, {"kind": "table_proposal"}, "count_unit")

    def test_cli_validation_failure_has_no_success_payload_or_sanitization(self) -> None:
        manifest, output = self.valid()
        self.mutate(output, "UPDATE snapshot_metadata SET value_json='{}' WHERE key='permissions'")
        before = output.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(["validate", str(output), str(manifest)])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIs(json.loads(stderr.getvalue())["success"], False)
        self.assertEqual(output.read_bytes(), before)

    def metadata_case(self, key: str, value: Any = None, delete: bool = False) -> None:
        manifest, output = self.valid()
        if delete:
            self.mutate(output, "DELETE FROM snapshot_metadata WHERE key=?", (key,))
        else:
            self.mutate(
                output,
                "UPDATE snapshot_metadata SET value_json=? WHERE key=?",
                (json.dumps(value), key),
            )
        self.reject_validation(manifest, output, "snapshot_metadata")

    def test_permission_normalization_is_rejected(self) -> None:
        self.permission_case("normalization", True, False)

    def test_permission_dispatch_is_rejected(self) -> None:
        self.permission_case("automatic_dispatch", True, False)

    def test_permission_scientific_is_rejected(self) -> None:
        self.permission_case("scientific_acceptance", True, False)

    def test_permission_scoring_is_rejected(self) -> None:
        self.permission_case("benchmark_scoring", True, False)

    def test_permission_missing_protected_key_is_rejected(self) -> None:
        self.permission_case("inspection", None, True)

    def test_permission_boolean_as_number_is_rejected(self) -> None:
        self.permission_case("normalization", 0, False)

    def test_permission_boolean_as_string_is_rejected(self) -> None:
        self.permission_case("normalization", "false", False)

    def test_permission_boolean_as_null_is_rejected(self) -> None:
        self.permission_case("normalization", None, False)

    def test_permission_extra_key_is_rejected(self) -> None:
        self.permission_case("invented_extra", False, False)

    def test_permission_inspection_false_is_rejected(self) -> None:
        self.permission_case("inspection", False, False)

    def test_metadata_product_binding_is_rejected(self) -> None:
        self.metadata_case("snapshot_version", "forged", False)

    def test_metadata_projection_binding_is_rejected(self) -> None:
        self.metadata_case("projection_version", "forged", False)

    def test_metadata_scope_binding_is_rejected(self) -> None:
        self.metadata_case("scope", "forged completeness", False)

    def test_metadata_authorship_binding_is_rejected(self) -> None:
        self.metadata_case("authorship", {"new_import": "personal human review"}, False)

    def test_metadata_source_manifest_binding_is_rejected(self) -> None:
        self.metadata_case("source_manifest", {}, False)

    def test_metadata_missing_permissions_binding_is_rejected(self) -> None:
        self.metadata_case("permissions", None, True)

    def two_units(self) -> tuple[Path, Path, str, str]:
        a, _, _ = invented(self.root / "A", 1, report="INVENTED_A")
        b, _, _ = invented(self.root / "B", 1, report="INVENTED_B")
        left, right = json.loads(a.read_bytes()), json.loads(b.read_bytes())
        left["documents"] += right["documents"]
        left["views"] += right["views"]
        a.write_text(json.dumps(left), encoding="utf-8")
        output = self.root / "union.sqlite"
        builder.build_snapshot(a, output)
        self.assertTrue(validation.validate(output, a)["success"])
        return a, output, left["views"][0]["sha256"], left["views"][1]["sha256"]

    def test_foreign_context_is_rejected_without_fk_failure(self) -> None:
        manifest, output, first, second = self.two_units()
        self.mutate(
            output,
            "UPDATE qualifiers SET context_key=(SELECT context_key "
            "FROM contexts WHERE unit_key=?) WHERE unit_key=?",
            (second, first),
        )
        self.reject_validation(manifest, output, "qualifier_projection")

    def test_assertion_unit_cannot_leak_across_units(self) -> None:
        manifest, output, first, second = self.two_units()
        self.mutate(output, "UPDATE assertions SET unit_key=? WHERE unit_key=?", (second, first))
        self.reject_validation(manifest, output, "assertion_projection")

    def test_equal_payload_cannot_substitute_a_differently_addressed_assertion(self) -> None:
        manifest, output = self.valid()
        self.mutate(
            output,
            "UPDATE assertion_links SET assertion_key=(SELECT assertion_key FROM "
            "assertions WHERE assertion_key LIKE '%/attachment_assertions/%' LIMIT 1) "
            "WHERE owner_key LIKE '%/qualifiers/%'",
        )
        self.reject_validation(manifest, output, "assertion_projection")

    def replace_scope_view(self, sql: str) -> tuple[Path, Path]:
        manifest, output = self.valid()
        with closing(sqlite3.connect(output)) as connection:
            original = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='v_cell_qualifiers'"
            ).fetchone()[0]
            connection.execute("DROP VIEW v_cell_qualifiers")
            connection.execute(sql.replace("{original_select}", original.split(" AS ", 1)[1]))
            connection.commit()
        return manifest, output

    def test_missing_scope_edges_are_independently_detected(self) -> None:
        manifest, output = self.replace_scope_view(
            "CREATE VIEW v_cell_qualifiers AS SELECT * FROM ({original_select}) WHERE 0"
        )
        self.reject_validation(manifest, output, "qualifier_scope_edges")

    def test_duplicate_scope_edges_are_independently_detected(self) -> None:
        manifest, output = self.replace_scope_view(
            "CREATE VIEW v_cell_qualifiers AS {original_select} UNION ALL {original_select}"
        )
        self.reject_validation(manifest, output, "qualifier_scope_edges")

    def test_extra_scope_edges_are_independently_detected(self) -> None:
        manifest, output = self.replace_scope_view(
            "CREATE VIEW v_cell_qualifiers AS SELECT c.cell_key,q.qualifier_key,q.kind,"
            "q.target_kind,col.column_role FROM cells c "
            "JOIN documentary_columns col USING(column_key)"
            " JOIN qualifiers q ON q.unit_key=c.unit_key WHERE c.cell_class='body'"
        )
        self.reject_validation(manifest, output, "qualifier_scope_edges")

    def test_unit_exposure_cannot_claim_new_completeness(self) -> None:
        manifest, output = self.valid()
        self.mutate(output, "UPDATE units SET exposure_json='{}'")
        self.reject_validation(manifest, output, "unit_metadata")

    def test_malformed_column_id_type_is_rejected(self) -> None:
        self.reject_input(1, {"kind": "column", "column_index": 1, "column_id": 1, "role": "count"})

    def test_table_scope_cannot_carry_contradictory_column_fields(self) -> None:
        self.reject_input(2, {"kind": "table_proposal", "column_id": "place"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
