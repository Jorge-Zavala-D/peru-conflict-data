"""Independent read-only preservation checks. Does not import or call the builder."""

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, cast

from .policy import PERMISSIONS, PROFILE_ROLES, QUALIFIER_TARGETS, SCOPE, VERSION


def canonical(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def resolve(documents: dict[str, Any], key: str) -> Any:
    match = re.fullmatch(r"sha256:([0-9a-f]{64})#(.*)", key)
    assert match and match[1] in documents, ("unresolved required address", key)
    value = documents[match[1]]
    path = match[2]
    assert not path or path.startswith("/"), ("pointer root", key)
    if path:
        for token in path[1:].split("/"):
            assert not re.search(r"~(?![01])", token), ("pointer escape", key)
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                assert re.fullmatch(r"0|[1-9][0-9]*", token), ("pointer array index", key)
                value = cast(list[Any], value)[int(token)]
            else:
                value = cast(dict[str, Any], value)[token]
    return value


def _validate(
    c: sqlite3.Connection, database: Path, manifest_path: Path, check_external: bool = True
) -> dict[str, Any]:
    database = Path(database).resolve()
    before = digest(database.read_bytes())
    manifest = json.loads(Path(manifest_path).read_bytes())
    c.execute("PRAGMA query_only=ON")
    assert c.execute("PRAGMA integrity_check").fetchall()[0][0] == "ok"
    assert not c.execute("PRAGMA foreign_key_check").fetchall()
    assert (
        isinstance(manifest.get("snapshot_version"), str)
        and manifest["snapshot_version"].strip()
        and manifest.get("projection_version") == VERSION
    ), "snapshot_metadata: supplied manifest version"
    expected_metadata = {
        "snapshot_version": manifest["snapshot_version"],
        "projection_version": VERSION,
        "authorship": manifest["authorship"],
        "scope": SCOPE,
        "permissions": PERMISSIONS,
        "source_manifest": manifest,
    }
    metadata_rows = {
        r["key"]: r["value_json"] for r in c.execute("SELECT * FROM snapshot_metadata")
    }
    assert set(metadata_rows) == set(expected_metadata), "snapshot_metadata: protected key set"
    for name, expected_value in expected_metadata.items():
        assert metadata_rows[name] == canonical(expected_value), ("snapshot_metadata", name)
    docs: dict[str, Any] = {}
    originals: list[dict[str, Any]] = []
    for item in manifest["documents"]:
        row = c.execute(
            "SELECT raw_bytes FROM documents WHERE sha256=?", (item["sha256"],)
        ).fetchone()
        assert row and digest(row[0]) == item["sha256"], ("document hash", item["sha256"])
        if check_external:
            location = Path(item["path"])
            assert (
                location if location.is_absolute() else manifest_path.resolve().parent / location
            ).read_bytes() == row[0], ("external bytes changed", item["sha256"])
        docs[item["sha256"]] = json.loads(row[0])
        originals.append(
            {
                "sha256": item["sha256"],
                "bytes": len(row[0]),
                "external_byte_equality": check_external,
            }
        )
    assert c.execute("SELECT count(*) FROM documents").fetchone()[0] == len(
        {x["sha256"] for x in manifest["documents"]}
    )
    for digest_key in docs:
        purposes: list[Any] = []
        for item in manifest["documents"]:
            if item["sha256"] == digest_key:
                for purpose in item.get("purposes", []):
                    if purpose not in purposes:
                        purposes.append(purpose)
        stored_purposes = c.execute(
            "SELECT purposes_json FROM documents WHERE sha256=?", (digest_key,)
        ).fetchone()[0]
        assert stored_purposes == canonical(purposes), ("document purpose lineage", digest_key)
    source_ledger: list[dict[str, Any]] = []
    for row in c.execute("SELECT * FROM source_records ORDER BY address"):
        original = resolve(docs, row["address"])
        assert row["address"] == "sha256:" + row["document_sha256"] + "#" + row["pointer"]
        assert row["payload_json"] == canonical(original), ("payload roundtrip", row["address"])
        assert row["storage_payload_sha256"] == digest(row["payload_json"].encode()), (
            "storage digest",
            row["address"],
        )
        if row["historical_record_sha256"] is not None:
            assert row["historical_algorithm"] == "historical-json-sortkeys-utf8-compact-sha256"
            assert row["historical_record_sha256"] == digest(canonical(original).encode()), (
                "historical digest",
                row["address"],
            )
        source_ledger.append(dict(row))
    # The ledger stores identities/digests, not another copy of the source payloads.
    for item in source_ledger:
        item.pop("payload_json")
    units: list[dict[str, Any]] = []
    cell_ledger: list[dict[str, Any]] = []
    row_ledger: list[dict[str, Any]] = []
    expected_permissions = PERMISSIONS
    expected_scope_edges: list[tuple[str, str, str, str, str]] = []
    assert len({spec["sha256"] for spec in manifest["views"]}) == len(manifest["views"])
    assert c.execute("SELECT count(*) FROM units").fetchone()[0] == len(manifest["views"])
    for spec in manifest["views"]:
        view = docs[spec["sha256"]]
        uid = spec["sha256"]
        assert view["version"] in PROFILE_ROLES, "unsupported view profile"
        legacy = view["version"] == "SOURCE_BOUND_CONTEXT_ATTACHMENT_V001"
        unit = c.execute("SELECT * FROM units WHERE unit_key=?", (uid,)).fetchone()
        assert (
            unit
            and unit["view_sha256"] == spec["sha256"]
            and unit["request_sha256"] == spec["request_sha256"]
        )
        assert (
            unit["native_sha256"] == view["source"]["native_sha256"]
            and unit["pdf_sha256"] == view["source"]["pdf_sha256"]
        )
        assert unit["source_json"] == canonical(view["source"]) and unit[
            "provenance_json"
        ] == canonical(view["provenance"])
        expected_exposure = {
            k: v
            for k, v in view.items()
            if k
            not in (
                "original_word_anchors",
                "inherited_cells",
                "inherited_grouping",
                "cell_references",
                "row_references",
                "context_node",
                "qualifiers",
                "dependencies",
                "documentary_metadata",
                "attachment_assertions",
            )
        }
        assert (
            unit["label"] == spec["label"]
            and unit["version"] == view["version"]
            and unit["physical_page"] == view["source"]["physical_page"]
            and unit["exposure_json"] == canonical(expected_exposure)
        ), "unit_metadata: source/exposure binding"
        assert (
            unit["permissions_json"]
            == canonical(view["permissions"])
            == canonical(expected_permissions)
        )
        assert view["provenance"].get("owner_personal_source_rechecking") is False
        declared_columns = c.execute(
            "SELECT * FROM documentary_columns WHERE unit_key=? ORDER BY ordinal", (uid,)
        ).fetchall()
        assert len(declared_columns) == 3
        if legacy:
            roles = docs[spec["request_sha256"]]["column_roles"]
            header_labels = {
                x["column_index"]: x["value_inherited_unchanged"]
                for x in view["inherited_cells"]
                if x.get("row_kind") == "printed_header"
            }
            expected_columns = [
                {"id": k, "source_index": v, "role": k, "display_label": header_labels.get(v, k)}
                for k, v in sorted(roles.items(), key=lambda x: x[1])
            ]
        else:
            expected_columns = view["columns"]
        assert (
            len(expected_columns) == 3
            and {x["role"] for x in expected_columns} == PROFILE_ROLES[view["version"]]
            and all(
                isinstance(x["id"], str)
                and x["id"]
                and type(x["source_index"]) is int
                and x["source_index"] >= 0
                for x in expected_columns
            )
            and len({x["id"] for x in expected_columns}) == 3
            and len({x["source_index"] for x in expected_columns}) == 3
        ), "qualifier_scope: original column profile"
        original_columns: dict[str, tuple[str, dict[str, Any]]] = {}
        for position, (col, expected_col) in enumerate(
            zip(declared_columns, expected_columns, strict=True)
        ):
            expected_key = (
                "sha256:" + uid + "#/columns/" + str(position)
                if not legacy
                else uid + ":declared-column:" + str(position)
            )
            original_columns[expected_col["id"]] = (expected_key, expected_col)
            assert (
                col["payload_json"] == canonical(expected_col)
                and col["source_index"] == expected_col["source_index"]
                and col["column_role"] == expected_col["role"]
                and col["column_key"] == expected_key
                and col["unit_key"] == uid
                and col["ordinal"] == position
            ), "qualifier_projection: declared column binding"
            assert col["label_json"] == canonical(expected_col["display_label"])
        assert c.execute("SELECT count(*) FROM cells WHERE unit_key=?", (uid,)).fetchone()[
            0
        ] == len(view["cell_references"])
        cells: dict[str, str] = {}
        original_body_columns: dict[str, tuple[str, str]] = {}
        for i, ref in enumerate(view["cell_references"]):
            key = ref["source_address"]
            payload = resolve(docs, key)
            cell = c.execute("SELECT * FROM cells WHERE cell_key=?", (key,)).fetchone()
            assert cell and cell["unit_key"] == uid and cell["ledger_json"] == canonical(ref)
            assert cell["cell_class"] == (
                "header" if legacy and payload.get("row_kind") == "printed_header" else "body"
            )
            original_column = (
                next(
                    (
                        x
                        for x in original_columns.values()
                        if x[1]["source_index"] == payload["column_index"]
                    ),
                    None,
                )
                if legacy
                else original_columns.get(ref["column_id"])
            )
            assert original_column is not None, "qualifier_projection: original cell column"
            column_key, column_payload = original_column
            assert (
                type(payload["column_index"]) is int
                and payload["column_index"] == column_payload["source_index"]
                and cell["column_key"] == column_key
            ), "qualifier_projection: cell column binding"
            if not (legacy and payload.get("row_kind") == "printed_header"):
                original_body_columns[key] = (column_key, column_payload["role"])
            assert digest(canonical(payload).encode()) == ref["record_sha256"]
            if legacy:
                assert canonical(payload) == canonical(view["inherited_cells"][i])
            field = "value_inherited_unchanged" if legacy else "value"
            assert field in payload and cell["value_presence"] == "present"
            value = payload[field]
            kind = (
                "null"
                if value is None
                else "boolean"
                if type(value) is bool
                else "string"
                if isinstance(value, str)
                else "number"
                if isinstance(value, (int, float))
                else "array"
                if isinstance(value, list)
                else "object"
            )
            assert cell["value_type"] == kind and cell["value_json"] == canonical(value)
            assert cell["display_text"] == (value if isinstance(value, str) else None)
            if not legacy:
                assert canonical(ref["display_value_inherited"]) == canonical(value)
            words = c.execute(
                "SELECT w.word_index FROM owner_words ow JOIN words w USING(word_key) "
                "WHERE owner_key=? ORDER BY ow.ordinal",
                (key,),
            ).fetchall()
            assert [x[0] for x in words] == payload["word_indices"]
            cells[payload["cell_id"] if legacy else ref["descriptor_id"]] = key
            cell_ledger.append(
                {
                    "unit": uid,
                    "address": key,
                    "historical_record_sha256": ref["record_sha256"],
                    "class": cell["cell_class"],
                    "value_presence": cell["value_presence"],
                    "value_type": kind,
                    "value_json": cell["value_json"],
                    "word_count": len(words),
                }
            )
        groups = view["inherited_grouping"] if legacy else view["row_references"]
        assert c.execute(
            "SELECT count(*) FROM documentary_rows WHERE unit_key=?", (uid,)
        ).fetchone()[0] == len(groups)
        for i, ref in enumerate(groups):
            key = (
                view["inherited_grouping_address"] + "/" + str(i)
                if legacy
                else ref["source_address"]
            )
            payload = resolve(docs, key)
            stored = c.execute("SELECT * FROM documentary_rows WHERE row_key=?", (key,)).fetchone()
            assert (
                stored
                and stored["unit_key"] == uid
                and stored["ordinal"] == i
                and stored["ledger_json"] == canonical(ref)
            )
            assert stored["local_label_json"] == canonical(payload.get("row_id"))
            assert stored["documentary_role_json"] == canonical(
                payload.get("row_kind") if legacy else payload.get("role")
            )
            assert stored["row_class"] == (
                "header" if legacy and payload.get("row_kind") == "printed_header" else "body"
            )
            if legacy:
                assert canonical(payload) == canonical(ref)
            else:
                assert digest(canonical(payload).encode()) == ref["record_sha256"]
            wanted = [
                cells[x]
                for x in ref["ordered_cell_ids" if legacy else "ordered_cell_descriptor_ids"]
            ]
            actual = [
                x[0]
                for x in c.execute(
                    "SELECT cell_key FROM row_cells WHERE row_key=? ORDER BY ordinal", (key,)
                )
            ]
            assert actual == wanted, ("ordered membership", key)
            row_ledger.append(
                {
                    "unit": uid,
                    "address": key,
                    "record_storage_digest": digest(canonical(payload).encode()),
                    "ordered_cells": actual,
                    "row_class": stored["row_class"],
                    "documentary_role_json": stored["documentary_role_json"],
                }
            )
        metadata = view.get("documentary_metadata", [])
        assert c.execute(
            "SELECT count(*) FROM documentary_metadata WHERE unit_key=?", (uid,)
        ).fetchone()[0] == len(metadata)
        for i, ref in enumerate(metadata):
            stored = c.execute(
                "SELECT * FROM documentary_metadata WHERE metadata_key=?", (ref["source_address"],)
            ).fetchone()
            assert (
                stored
                and stored["kind"] == ref["kind"]
                and stored["ledger_json"] == canonical(ref)
                and stored["ordinal"] == i
            )
            actual = [
                x[0]
                for x in c.execute(
                    "SELECT w.word_index FROM metadata_words mw JOIN words w USING(word_key) "
                    "WHERE metadata_key=? ORDER BY mw.ordinal",
                    (ref["source_address"],),
                )
            ]
            assert actual == ref["word_indices"]
        anchors = view["original_word_anchors"]
        assert c.execute("SELECT count(*) FROM unit_words WHERE unit_key=?", (uid,)).fetchone()[
            0
        ] == len(anchors)
        for index, anchor in anchors.items():
            row = c.execute(
                "SELECT * FROM words WHERE word_key=?", (anchor["source_address"],)
            ).fetchone()
            original = resolve(docs, anchor["source_address"])
            assert (
                row
                and row["text"] == anchor["text"] == original["text"]
                and row["word_index"] == int(index)
            )
            assert row["span_json"] == canonical(anchor["span"]) == canonical(original["span"])
            assert row["bbox_json"] == canonical(anchor["bbox"]) == canonical(original["bbox"])
            assert (
                docs[unit["native_sha256"]]["text"][anchor["span"][0] : anchor["span"][1]]
                == anchor["text"]
            )
            layouts = anchor.get(
                "layout_pointers", [anchor["layout_pointer"]] if "layout_pointer" in anchor else []
            )
            actual = [
                x[0]
                for x in c.execute(
                    "SELECT record_key FROM word_links WHERE word_key=? "
                    "AND kind='native_layout' ORDER BY ordinal",
                    (anchor["source_address"],),
                )
            ]
            assert actual == ["sha256:" + unit["native_sha256"] + "#" + p for p in layouts]
        ctx = "sha256:" + uid + "#/context_node"
        context = c.execute("SELECT * FROM contexts WHERE unit_key=?", (uid,)).fetchone()
        assert (
            context
            and context["context_key"] == ctx
            and context["kind"] == view["context_node"].get("kind", "caption")
        )
        owners = [(ctx, view["context_node"])]
        assert c.execute("SELECT count(*) FROM qualifiers WHERE unit_key=?", (uid,)).fetchone()[
            0
        ] == len(view["qualifiers"])
        for i, qualifier in enumerate(view["qualifiers"]):
            key = "sha256:" + uid + "#/qualifiers/" + str(i)
            q = c.execute("SELECT * FROM qualifiers WHERE qualifier_key=?", (key,)).fetchone()
            target = qualifier["target"]
            rule = QUALIFIER_TARGETS[view["version"]].get(qualifier["kind"])
            expected_target_kind = "unresolved"
            expected_target_column = None
            if target is None:
                assert qualifier.get("resolution") == (
                    "unresolved_missing_semantic_support"
                    if rule is not None
                    else "unresolved_unsupported_attachment"
                ), "qualifier_scope: invalid unresolved target"
            else:
                assert isinstance(target, dict), "qualifier_scope: original target object"
                target = cast(dict[str, Any], target)
                assert rule is not None and target.get("kind") == rule[0], (
                    "qualifier_scope: original kind/profile target"
                )
                expected_target_kind = target["kind"]
                if expected_target_kind == "column":
                    bound = next(x for x in original_columns.values() if x[1]["role"] == rule[1])
                    expected_target_column, original_column_payload = bound
                    assert (
                        type(target.get("column_index")) is int
                        and target["column_index"] == original_column_payload["source_index"]
                        and target.get("role") == original_column_payload["role"]
                        and (
                            "column_id" not in target
                            or target["column_id"] == original_column_payload["id"]
                        )
                    ), "qualifier_scope: original column identity/role"
                else:
                    assert not any(
                        field in target for field in ("column_index", "column_id", "role")
                    ), "qualifier_scope: original non-column target"
            assert (
                q
                and q["unit_key"] == uid
                and q["context_key"] == ctx
                and q["ordinal"] == i
                and q["target_json"] == canonical(qualifier["target"])
                and q["kind"] == qualifier["kind"]
                and q["target_kind"] == expected_target_kind
                and q["target_column"] == expected_target_column
            ), ("qualifier_projection", key)
            assert q["display_text"] == qualifier.get("display_text") and q[
                "contiguous_json"
            ] == canonical(qualifier.get("display_is_contiguous_source_quote"))
            assert q["resolution_json"] == canonical(qualifier.get("resolution"))
            for cell_key, (column_key, column_role) in original_body_columns.items():
                if expected_target_kind == "table_proposal" or (
                    expected_target_kind == "column" and expected_target_column == column_key
                ):
                    expected_scope_edges.append(
                        (cell_key, key, qualifier["kind"], expected_target_kind, column_role)
                    )
            app = qualifier["applicability"]
            refs = cast(dict[str, Any], app)["assertions"] if isinstance(app, dict) else app
            owners.append((key, qualifier))
            check_assertions(
                c,
                key,
                uid,
                key + ("/applicability/assertions" if isinstance(app, dict) else "/applicability"),
                refs,
            )
        attachments = view["attachment_assertions"]
        attachments = (
            cast(dict[str, Any], attachments)["assertions"]
            if isinstance(attachments, dict)
            else attachments
        )
        check_assertions(
            c,
            ctx,
            uid,
            "sha256:"
            + uid
            + "#/attachment_assertions"
            + ("/assertions" if isinstance(view["attachment_assertions"], dict) else ""),
            attachments,
        )
        for owner, payload in owners:
            segs = c.execute(
                "SELECT * FROM segments WHERE owner_key=? ORDER BY ordinal", (owner,)
            ).fetchall()
            assert len(segs) == len(payload.get("source_segments", []))
            for stored, segment in zip(segs, payload.get("source_segments", []), strict=True):
                assert (
                    stored["exact_text"] == segment["exact_text"]
                    and stored["own_span_json"] == canonical(segment["own_text_span"])
                    and stored["span_frame"] == segment["span_frame"]
                )
                actual = [
                    x[0]
                    for x in c.execute(
                        "SELECT word_key FROM owner_words WHERE owner_key=? ORDER BY ordinal",
                        (stored["segment_key"],),
                    )
                ]
                assert actual == segment["word_addresses"]
        deps = c.execute(
            "SELECT * FROM dependencies WHERE unit_key=? ORDER BY ordinal", (uid,)
        ).fetchall()
        assert len(deps) == len(view["dependencies"])
        for stored, dep in zip(deps, view["dependencies"], strict=True):
            assert (
                stored["payload_json"] == canonical(dep)
                and stored["state"] == dep["state"]
                and stored["name"] == dep["name"]
            )
            check_evidence(c, stored["dependency_key"], dep.get("evidence_refs", []))
        for i, ref in enumerate(view.get("linked_contextual_limits", [])):
            check_evidence(c, "sha256:" + uid + "#/linked_contextual_limits/" + str(i), [ref])
        units.append(
            {
                "unit_key": uid,
                "physical_page": unit["physical_page"],
                "view_version": unit["version"],
                "body_rows": c.execute(
                    "SELECT count(*) FROM documentary_rows WHERE unit_key=? AND row_class='body'",
                    (uid,),
                ).fetchone()[0],
                "body_cells": c.execute(
                    "SELECT count(*) FROM cells WHERE unit_key=? AND cell_class='body'", (uid,)
                ).fetchone()[0],
                "header_cells": c.execute(
                    "SELECT count(*) FROM cells WHERE unit_key=? AND cell_class='header'", (uid,)
                ).fetchone()[0],
                "metadata_records": len(metadata),
                "distinct_bound_words": len(anchors),
                "context_words": sum(
                    len(x["word_indices"]) for x in view["context_node"]["source_segments"]
                ),
                "qualifiers": len(view["qualifiers"]),
                "dependencies": len(deps),
            }
        )
    counts = {
        name: c.execute("SELECT count(*) FROM " + name).fetchone()[0]
        for name in [
            "units",
            "documentary_rows",
            "cells",
            "row_cells",
            "documentary_metadata",
            "metadata_words",
            "contexts",
            "qualifiers",
            "dependencies",
            "words",
            "source_records",
            "assertions",
            "unresolved_references",
            "v_body_rows",
            "v_body_cells",
        ]
    }
    for assertion in c.execute("SELECT * FROM assertions"):
        ref = json.loads(assertion["payload_json"])
        assert assertion["source_record"] == ref["source_address"] and assertion[
            "attribution_json"
        ] == canonical(ref.get("attribution"))
        assert assertion["stage_presence"] == ("present" if "stage" in ref else "absent")
        assert assertion["stage_json"] == (canonical(ref["stage"]) if "stage" in ref else None)
        assert ref.get("human_reviewed", False) is False
    expected_edges = Counter(expected_scope_edges)
    actual_edges = Counter(tuple(r) for r in c.execute("SELECT * FROM v_cell_qualifiers"))
    assert actual_edges == expected_edges, (
        "qualifier_scope_edges",
        {
            "missing": list((expected_edges - actual_edges).elements()),
            "extra": list((actual_edges - expected_edges).elements()),
        },
    )
    assert counts["v_body_rows"] == len([x for x in row_ledger if x["row_class"] == "body"])
    assert counts["v_body_cells"] == len([x for x in cell_ledger if x["class"] == "body"])
    assert not c.execute(
        "SELECT row_key FROM v_body_rows GROUP BY row_key HAVING count(*)!=1"
    ).fetchall()
    assert not c.execute(
        "SELECT cell_key FROM v_body_cells GROUP BY cell_key HAVING count(*)!=1"
    ).fetchall()
    expected = manifest.get("expected_accounting", {})
    actual = {
        "units": counts["units"],
        "body_rows": counts["v_body_rows"],
        "body_cells": counts["v_body_cells"],
        "header_cells": sum(u["header_cells"] for u in units),
        "contexts": counts["contexts"],
        "qualifiers": counts["qualifiers"],
        "dependencies": counts["dependencies"],
        "priority_heading_anchors": c.execute(
            "SELECT count(*) FROM metadata_words JOIN documentary_metadata "
            "USING(metadata_key) WHERE kind='header'"
        ).fetchone()[0],
        "priority_ordinals": c.execute(
            "SELECT count(*) FROM documentary_metadata WHERE kind='ordinal'"
        ).fetchone()[0],
    }
    for key, value in expected.items():
        if key in actual:
            assert actual[key] == value, ("accounting mismatch", key, actual[key], value)
    assert digest(database.read_bytes()) == before, "read-only validation modified sealed bytes"
    return {
        "success": True,
        "database_sha256": before,
        "integrity_check": "ok",
        "foreign_key_violations": [],
        "original_documents": originals,
        "units": units,
        "storage_counts": counts,
        "accounting": actual,
        "cell_ledger": cell_ledger,
        "row_ledger": row_ledger,
        "addressed_record_ledger": source_ledger,
        "comparison": (
            "Engineering semantic and byte preservation, not scientific accuracy. "
            "All source record types/presence retained."
        ),
        "read_only_hash_unchanged": True,
        "builder_or_generator_calls": 0,
    }


def check_assertions(
    c: sqlite3.Connection, owner: str, unit: str, prefix: str, refs: list[dict[str, Any]]
) -> None:
    rows = c.execute(
        "SELECT a.*,l.ordinal AS link_ordinal FROM assertion_links l JOIN assertions a "
        "USING(assertion_key) WHERE owner_key=? ORDER BY l.ordinal",
        (owner,),
    ).fetchall()
    assert len(rows) == len(refs), "assertion_projection: link population"
    for i, (row, original) in enumerate(zip(rows, refs, strict=True)):
        assert (
            row["assertion_key"] == prefix + "/" + str(i)
            and row["unit_key"] == unit
            and row["link_ordinal"] == i
            and row["payload_json"] == canonical(original)
            and row["source_record"] == original["source_address"]
            and row["attribution_json"] == canonical(original.get("attribution"))
            and row["stage_presence"] == ("present" if "stage" in original else "absent")
            and row["stage_json"] == (canonical(original["stage"]) if "stage" in original else None)
            and original.get("human_reviewed", False) is False
        ), "assertion_projection: identity/unit/source attribution"


def check_evidence(c: sqlite3.Connection, owner: str, refs: list[Any]) -> None:
    linked = {
        r["ordinal"]: r
        for r in c.execute("SELECT * FROM evidence_links WHERE owner_key=?", (owner,))
    }
    unresolved = {
        r["ordinal"]: r
        for r in c.execute("SELECT * FROM unresolved_references WHERE owner_key=?", (owner,))
    }
    assert not set(linked).intersection(unresolved) and len(linked) + len(unresolved) == len(refs)
    for i, ref in enumerate(refs):
        row = linked.get(i, unresolved.get(i))
        assert row and row["reference_json"] == canonical(ref)
        if i in linked:
            assert row["source_record"] == (ref["source_address"] if isinstance(ref, dict) else ref)


def validate(database: Path, manifest_path: Path, check_external: bool = True) -> dict[str, Any]:
    if not __debug__:
        raise RuntimeError("optimized Python is unsupported for independent validation")
    database = Path(database).resolve()
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return _validate(connection, database, manifest_path, check_external)
    finally:
        connection.close()
