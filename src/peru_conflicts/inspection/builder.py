"""Private bounded relational projection of frozen V001/V002 views; no generator imports."""

import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

VERSION = "DOCUMENTARY_SQLITE_PROJECTION_V001"
LIBRARY_VERSION = "DOCUMENTARY_INSPECTION_STORE_V001"
PERMISSIONS = dict(
    inspection=True,
    normalization=False,
    automatic_dispatch=False,
    scientific_acceptance=False,
    benchmark_scoring=False,
)


class RecordHashMismatch(ValueError):
    """A supplied addressed record conflicts with its required historical digest."""


def packed(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))
    )


def pointer(document: Any, path: str) -> Any:
    if path == "":
        return document
    if not path.startswith("/"):
        raise ValueError("invalid pointer root")
    current = document
    for part in path[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise ValueError("invalid pointer escape")
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", part):
                    raise ValueError("noncanonical pointer index")
                current = cast(list[Any], current)[int(part)]
            elif isinstance(current, dict):
                current = cast(dict[str, Any], current)[part]
            else:
                raise ValueError("pointer traverses scalar")
        except (KeyError, IndexError) as exc:
            raise ValueError("unresolved pointer: " + path) from exc
    return current


def address(digest: str, path: str = "") -> str:
    return "sha256:" + digest + "#" + path


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "array" if isinstance(value, list) else "object"


class Projection:
    def __init__(
        self, connection: sqlite3.Connection, manifest: dict[str, Any], manifest_base: Path
    ) -> None:
        self.c = connection
        self.manifest = manifest
        self.docs: dict[str, Any] = {}
        for item in manifest["documents"]:
            location = Path(item["path"])
            raw = (location if location.is_absolute() else manifest_base / location).read_bytes()
            if sha(raw) != item["sha256"]:
                raise ValueError("document hash mismatch: " + item["sha256"])
            old = self.c.execute(
                "SELECT raw_bytes,purposes_json FROM documents WHERE sha256=?", (item["sha256"],)
            ).fetchone()
            if old is not None:
                if old[0] != raw:
                    raise ValueError("conflicting document bytes")
                purposes = json.loads(old[1])
                for purpose in item.get("purposes", []):
                    if purpose not in purposes:
                        purposes.append(purpose)
                self.c.execute(
                    "UPDATE documents SET purposes_json=? WHERE sha256=?",
                    (packed(purposes), item["sha256"]),
                )
            else:
                self.docs[item["sha256"]] = strict_json(raw)
                self.c.execute(
                    "INSERT INTO documents VALUES(?,?,?,?)",
                    (
                        item["sha256"],
                        raw,
                        "original UTF-8 JSON bytes",
                        packed(item.get("purposes", [])),
                    ),
                )

    def record(self, key: str, expected: str | None = None) -> Any:
        match = re.fullmatch(r"sha256:([0-9a-f]{64})#(.*)", key)
        if not match or match[1] not in self.docs:
            raise ValueError("missing required document/address: " + key)
        digest, path = match.groups()
        value = pointer(self.docs[digest], path)
        payload = packed(value)
        storage = sha(payload.encode("utf-8"))
        if expected is not None and storage != expected:
            raise RecordHashMismatch("historical record hash mismatch: " + key)
        old = self.c.execute(
            "SELECT payload_json FROM source_records WHERE address=?", (key,)
        ).fetchone()
        if old and old[0] != payload:
            raise ValueError("conflicting addressed record")
        self.c.execute(
            "INSERT OR IGNORE INTO source_records VALUES(?,?,?,?,?,?,?)",
            (
                key,
                digest,
                path,
                payload,
                expected,
                "historical-json-sortkeys-utf8-compact-sha256" if expected else None,
                storage,
            ),
        )
        if expected:
            self.c.execute(
                "UPDATE source_records SET historical_record_sha256=?,"
                "historical_algorithm=? WHERE address=?",
                (expected, "historical-json-sortkeys-utf8-compact-sha256", key),
            )
        return value

    def link_words(self, owner: str, indices: list[int], metadata: bool = False) -> None:
        if len(indices) != len(set(indices)):
            raise ValueError("duplicate word membership")
        for order, index in enumerate(indices):
            if str(index) not in self.anchors:
                raise ValueError("missing required word binding")
            wk = self.anchors[str(index)]["source_address"]
            self.c.execute("INSERT INTO owner_words VALUES(?,?,?)", (owner, order, wk))
            if metadata:
                self.c.execute("INSERT INTO metadata_words VALUES(?,?,?)", (owner, order, wk))

    def word_link(self, word: str, ordinal: int, kind: str, record: str) -> None:
        existing = self.c.execute(
            "SELECT record_key FROM word_links WHERE word_key=? AND kind=? AND ordinal=?",
            (word, kind, ordinal),
        ).fetchone()
        if existing is not None and existing[0] != record:
            raise ValueError("incompatible repeated native-word evidence binding")
        if existing is None:
            self.c.execute("INSERT INTO word_links VALUES(?,?,?,?)", (word, ordinal, kind, record))

    def evidence(self, owner: str, refs: list[Any]) -> None:
        for i, ref in enumerate(refs):
            mapping = cast(dict[str, Any], ref) if isinstance(ref, dict) else {}
            key = mapping.get("source_address") if isinstance(ref, dict) else ref
            try:
                if not isinstance(key, str):
                    raise ValueError("missing optional source address")
                self.record(key, mapping.get("record_sha256"))
            except (ValueError, TypeError) as exc:
                if isinstance(exc, RecordHashMismatch):
                    raise
                self.c.execute(
                    "INSERT INTO unresolved_references VALUES(?,?,?,?)",
                    (owner, i, packed(ref), str(exc)),
                )
                continue
            self.c.execute(
                "INSERT INTO evidence_links VALUES(?,?,?,?)", (owner, i, key, packed(ref))
            )

    def segments(self, owner: str, payload: dict[str, Any], owner_path: str) -> set[int]:
        all_indices: list[int] = []
        native = self.docs[self.native]
        for i, segment in enumerate(payload.get("source_segments", [])):
            sk = address(self.view_sha, owner_path + "/source_segments/" + str(i))
            self.record(sk)
            span = segment["own_text_span"]
            if (
                len(span) != 2
                or any(type(x) is not int for x in span)
                or not 0 <= span[0] <= span[1] <= len(native["text"])
            ):
                raise ValueError("invalid own-text span")
            if (
                segment["span_frame"] != "/text"
                or native["text"][span[0] : span[1]] != segment["exact_text"]
            ):
                raise ValueError("source literal/span mismatch")
            indices = segment["word_indices"]
            expected_addresses = [address(self.native, "/words/" + str(x)) for x in indices]
            if segment.get("word_addresses") != expected_addresses:
                raise ValueError("source segment word addresses mismatch")
            self.c.execute(
                "INSERT INTO segments VALUES(?,?,?,?,?,?)",
                (sk, owner, i, segment["exact_text"], packed(span), segment["span_frame"]),
            )
            self.link_words(sk, indices)
            all_indices.extend(indices)
        return set(all_indices)

    def assertion_refs(self, owner: str, refs: list[dict[str, Any]], path: str) -> None:
        for i, ref in enumerate(refs):
            if ref.get("human_reviewed", False) is not False:
                raise ValueError("human review promotion")
            ak = address(self.view_sha, path + "/" + str(i))
            self.record(ak)
            source = ref["source_address"]
            self.record(source)
            self.c.execute(
                "INSERT INTO assertions VALUES(?,?,?,?,?,?,?)",
                (
                    ak,
                    self.unit,
                    source,
                    packed(ref.get("attribution")),
                    "present" if "stage" in ref else "absent",
                    packed(ref["stage"]) if "stage" in ref else None,
                    packed(ref),
                ),
            )
            self.c.execute("INSERT INTO assertion_links VALUES(?,?,?)", (owner, i, ak))

    def unit_view(self, spec: dict[str, Any]) -> None:
        self.view_sha = spec["sha256"]
        if self.c.execute("SELECT 1 FROM units WHERE view_sha256=?", (self.view_sha,)).fetchone():
            raise ValueError("duplicate selected view identity")
        self.unit = self.view_sha
        view = self.docs[self.view_sha]
        self.native = view["source"]["native_sha256"]
        native = self.docs[self.native]
        legacy = view["version"] == "SOURCE_BOUND_CONTEXT_ATTACHMENT_V001"
        if not legacy and view["version"] != "SOURCE_BOUND_CONTEXT_ATTACHMENT_V002":
            raise ValueError("unsupported view version")
        if view.get("permissions") != PERMISSIONS or any(
            type(v) is not bool for v in view["permissions"].values()
        ):
            raise ValueError("permission promotion or missing permission")
        if view.get("provenance", {}).get("owner_personal_source_rechecking", False) is not False:
            raise ValueError("human review promotion")
        if not view.get("cell_references"):
            raise ValueError("empty selected cell inventory")
        self.record(address(self.view_sha))
        self.c.execute(
            "INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.unit,
                spec["label"],
                self.view_sha,
                spec["request_sha256"],
                view["version"],
                view["source"]["physical_page"],
                view["source"]["pdf_sha256"],
                self.native,
                packed(view["source"]),
                packed(view.get("provenance", {})),
                packed(
                    {
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
                ),
                packed(view["permissions"]),
            ),
        )
        self.anchors = view["original_word_anchors"]
        for index, anchor in self.anchors.items():
            wk = anchor["source_address"]
            word = self.record(wk)
            if wk != address(self.native, "/words/" + index):
                raise ValueError("native word pointer/index mismatch")
            for field in ("text", "span", "bbox"):
                if packed(word[field]) != packed(anchor[field]):
                    raise ValueError("native word field mismatch")
            start, end = word["span"]
            if native["text"][start:end] != word["text"] or not 0 <= start <= end <= len(
                native["text"]
            ):
                raise ValueError("native own-text span mismatch")
            anchor_key = address(self.view_sha, "/original_word_anchors/" + index)
            self.record(anchor_key)
            frame = anchor.get("span_frame", "/text")
            if frame != "/text":
                raise ValueError("unsupported native own-text frame")
            values = (
                wk,
                self.native,
                int(index),
                word["text"],
                packed(word["span"]),
                packed(word["bbox"]),
                frame,
            )
            existing_word = self.c.execute("SELECT * FROM words WHERE word_key=?", (wk,)).fetchone()
            if existing_word is not None and tuple(existing_word) != values:
                raise ValueError("conflicting repeated native-word record")
            if existing_word is None:
                self.c.execute("INSERT INTO words VALUES(?,?,?,?,?,?,?)", values)
            self.c.execute("INSERT INTO unit_words VALUES(?,?,?)", (self.unit, wk, anchor_key))
            layouts = anchor.get(
                "layout_pointers", [anchor["layout_pointer"]] if "layout_pointer" in anchor else []
            )
            for i, path in enumerate(layouts):
                lk = address(self.native, path)
                layout = self.record(lk)
                if any(packed(layout[f]) != packed(word[f]) for f in ("text", "span", "bbox")):
                    raise ValueError("native layout binding mismatch")
                self.word_link(wk, i, "native_layout", lk)
            evidence_key = anchor.get("evidence_address")
            if legacy:
                evidence_key = view["inherited_word_evidence_address"] + "/" + index
            if evidence_key:
                self.record(evidence_key)
                self.word_link(wk, 0, "original_evidence", evidence_key)
        if legacy:
            roles = self.docs[spec["request_sha256"]]["column_roles"]
            headers = {
                x["column_index"]: x["value_inherited_unchanged"]
                for x in view["inherited_cells"]
                if x.get("row_kind") == "printed_header"
            }
            columns = [
                dict(id=role, source_index=index, role=role, display_label=headers.get(index, role))
                for role, index in sorted(roles.items(), key=lambda x: x[1])
            ]
        else:
            columns = view["columns"]
        if len(columns) != 3:
            raise ValueError("bounded profile requires three columns")
        if (
            len({col["id"] for col in columns}) != 3
            or len({col["source_index"] for col in columns}) != 3
        ):
            raise ValueError("duplicate declared column identity")
        expected_roles = (
            {"category", "count", "percentage"}
            if legacy
            else {"place_text", "case_description", "published_situation"}
        )
        if {col["role"] for col in columns} != expected_roles:
            raise ValueError("unsupported three-column documentary profile")
        column_keys: dict[Any, str] = {}
        for i, col in enumerate(columns):
            ck = (
                address(self.view_sha, "/columns/" + str(i))
                if not legacy
                else self.unit + ":declared-column:" + str(i)
            )
            column_keys[col["id"]] = ck
            column_keys[col["source_index"]] = ck
            self.c.execute(
                "INSERT INTO documentary_columns VALUES(?,?,?,?,?,?,?)",
                (
                    ck,
                    self.unit,
                    i,
                    col["source_index"],
                    col["role"],
                    packed(col.get("display_label")),
                    packed(col),
                ),
            )
        cells: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
        cell_words: set[int] = set()
        for i, ref in enumerate(view["cell_references"]):
            key = ref["source_address"]
            if self.c.execute("SELECT 1 FROM cells WHERE cell_key=?", (key,)).fetchone():
                raise ValueError("overlapping original cell across selected views is unsupported")
            cell = self.record(key, ref["record_sha256"])
            if legacy and packed(cell) != packed(view["inherited_cells"][i]):
                raise ValueError("inherited cell payload mismatch")
            value_field = "value_inherited_unchanged" if legacy else "value"
            if value_field not in cell:
                raise ValueError("missing required value")
            val = cell[value_field]
            if not legacy and (
                "display_value_inherited" not in ref
                or packed(ref["display_value_inherited"]) != packed(val)
            ):
                raise ValueError("inherited display/value mismatch")
            ck = column_keys[cell["column_index"]] if legacy else column_keys[ref["column_id"]]
            declared_index = self.c.execute(
                "SELECT source_index FROM documentary_columns WHERE column_key=?", (ck,)
            ).fetchone()[0]
            if cell["column_index"] != declared_index:
                raise ValueError("original cell/source column index mismatch")
            klass = "header" if legacy and cell.get("row_kind") == "printed_header" else "body"
            self.c.execute(
                "INSERT INTO cells VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    self.unit,
                    ck,
                    klass,
                    "present",
                    value_type(val),
                    packed(val),
                    val if isinstance(val, str) else None,
                    packed(ref),
                ),
            )
            indices = cell["word_indices"]
            if not legacy and ref["word_indices"] != indices:
                raise ValueError("cell word binding mismatch")
            if cell_words.intersection(indices):
                raise ValueError("substantive/header ownership conflict")
            cell_words.update(indices)
            self.link_words(key, indices)
            local = cell["cell_id"] if legacy else ref["descriptor_id"]
            if local in cells:
                raise ValueError("duplicate cell descriptor")
            cells[local] = (key, cell, ref)
        groups = view["inherited_grouping"] if legacy else view["row_references"]
        used: set[str] = set()
        if not groups:
            raise ValueError("empty grouping")
        for i, group in enumerate(groups):
            key = (
                view["inherited_grouping_address"] + "/" + str(i)
                if legacy
                else group["source_address"]
            )
            row = self.record(key, None if legacy else group["record_sha256"])
            if legacy and packed(row) != packed(group):
                raise ValueError("grouping payload mismatch")
            members = group["ordered_cell_ids"] if legacy else group["ordered_cell_descriptor_ids"]
            if len(members) != 3 or any(x not in cells or x in used for x in members):
                raise ValueError("grouping conflict")
            klass = "header" if legacy and row.get("row_kind") == "printed_header" else "body"
            role = row.get("row_kind") if legacy else row.get("role")
            self.c.execute(
                "INSERT INTO documentary_rows VALUES(?,?,?,?,?,?,?)",
                (key, self.unit, i, packed(row.get("row_id")), klass, packed(role), packed(group)),
            )
            for pos, member in enumerate(members):
                cell_key, cell, ref = cells[member]
                if (
                    self.c.execute(
                        "SELECT column_key FROM cells WHERE cell_key=?", (cell_key,)
                    ).fetchone()[0]
                    != column_keys[columns[pos]["id"]]
                ):
                    raise ValueError("ordered grouping/column conflict")
                if not legacy and (
                    cell_key != key + "/cells/" + str(pos)
                    or packed(row["cells"][pos]) != packed(cell)
                ):
                    raise ValueError("row/cell grouping mismatch")
                self.c.execute("INSERT INTO row_cells VALUES(?,?,?)", (key, pos, cell_key))
                used.add(member)
        if used != set(cells):
            raise ValueError("grouping omitted cells")
        metadata_words: set[int] = set()
        for i, ref in enumerate(view.get("documentary_metadata", [])):
            key = ref["source_address"]
            self.record(key, ref["record_sha256"])
            self.c.execute(
                "INSERT INTO documentary_metadata VALUES(?,?,?,?,?)",
                (key, self.unit, i, ref["kind"], packed(ref)),
            )
            indices = ref["word_indices"]
            if metadata_words.intersection(indices) or cell_words.intersection(indices):
                raise ValueError("header/ordinal ownership conflict")
            metadata_words.update(indices)
            self.link_words(key, indices, metadata=True)
        ctx = address(self.view_sha, "/context_node")
        self.record(ctx)
        self.c.execute(
            "INSERT INTO contexts VALUES(?,?,?,?)",
            (
                ctx,
                self.unit,
                view["context_node"].get("kind", "caption"),
                "legacy V001 contract caption" if legacy else "declared V002 kind",
            ),
        )
        context_words = self.segments(ctx, view["context_node"], "/context_node")
        if context_words.intersection(cell_words | metadata_words):
            raise ValueError("non-cell context ownership conflict")
        attachments = view["attachment_assertions"]
        if legacy:
            if attachments.get("human_reviewed", False) is not False:
                raise ValueError("human review promotion")
            self.assertion_refs(ctx, attachments["assertions"], "/attachment_assertions/assertions")
        else:
            self.assertion_refs(ctx, attachments, "/attachment_assertions")
        for i, qualifier in enumerate(view["qualifiers"]):
            qpath = "/qualifiers/" + str(i)
            qk = address(self.view_sha, qpath)
            self.record(qk)
            target = qualifier["target"]
            if target["kind"] not in ("table_proposal", "column", "reported_organization"):
                raise ValueError("unsupported declared qualifier target")
            target_column = None
            if target["kind"] == "column":
                target_column = column_keys.get(target.get("column_index", target.get("column_id")))
                if target_column is None:
                    raise ValueError("missing qualifier column scope")
                column_role = self.c.execute(
                    "SELECT column_role FROM documentary_columns WHERE column_key=?",
                    (target_column,),
                ).fetchone()[0]
                if target.get("role", column_role) != column_role:
                    raise ValueError("qualifier column role/scope mismatch")
            if "source_address" in target:
                self.record(target["source_address"])
            self.c.execute(
                "INSERT INTO qualifiers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    qk,
                    self.unit,
                    ctx,
                    i,
                    qualifier["kind"],
                    target["kind"],
                    target_column,
                    packed(target),
                    qualifier.get("display_text"),
                    packed(qualifier.get("display_is_contiguous_source_quote")),
                    packed(qualifier.get("resolution")),
                ),
            )
            # A preserved qualifier may cite a header (e.g. %) outside the caption.
            self.segments(qk, qualifier, qpath)
            app = qualifier["applicability"]
            if isinstance(app, dict):
                app_mapping = cast(dict[str, Any], app)
                if app_mapping.get("human_reviewed", False) is not False:
                    raise ValueError("human review promotion")
                self.assertion_refs(
                    qk, app_mapping["assertions"], qpath + "/applicability/assertions"
                )
            else:
                self.assertion_refs(qk, app, qpath + "/applicability")
        for i, dep in enumerate(view["dependencies"]):
            dk = address(self.view_sha, "/dependencies/" + str(i))
            self.record(dk)
            if dep["state"] not in (
                "unknown",
                "confirmed_none",
                "reported_empty",
                "absent_field",
                "unreviewed_interpretation",
            ):
                raise ValueError("unsupported dependency state")
            self.c.execute(
                "INSERT INTO dependencies VALUES(?,?,?,?,?,?)",
                (dk, self.unit, i, dep["name"], dep["state"], packed(dep)),
            )
            self.evidence(dk, dep.get("evidence_refs", []))
        for i, ref in enumerate(view.get("linked_contextual_limits", [])):
            owner = address(self.view_sha, "/linked_contextual_limits/" + str(i))
            self.record(owner)
            self.evidence(owner, [ref])


def build_snapshot(manifest_path: Path, output: Path) -> dict[str, Any]:
    """Exclusive single-file publication after transaction/closed-stage validation.

    Failed stage is retained at the path reported in the exception, never published.
    This does not promise atomic publication of the whole delivery directory.
    """
    if not __debug__:
        raise RuntimeError("optimized Python is unsupported for validated snapshot builds")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    manifest = strict_json(Path(manifest_path).read_bytes())
    if (
        not isinstance(manifest.get("snapshot_version"), str)
        or not manifest["snapshot_version"].strip()
        or manifest.get("projection_version") != VERSION
    ):
        raise ValueError("manifest version mismatch")
    stage = Path(tempfile.mkdtemp(prefix="s27-db-")) / "stage.sqlite"
    connection = sqlite3.connect(stage)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ValueError("foreign keys unavailable")
        connection.execute("PRAGMA journal_mode=DELETE")
        schema = (
            files("peru_conflicts.inspection").joinpath("schema.sql").read_text(encoding="utf-8")
        )
        connection.executescript("BEGIN IMMEDIATE;\n" + schema)
        projection = Projection(connection, manifest, manifest_path.resolve().parent)
        for key, value in {
            "snapshot_version": manifest["snapshot_version"],
            "projection_version": VERSION,
            "authorship": manifest["authorship"],
            "scope": (
                "Only selected frozen documentary records; no full-report completeness "
                "certification; rows are not canonical cases/events."
            ),
            "permissions": PERMISSIONS,
            "source_manifest": manifest,
        }.items():
            connection.execute("INSERT INTO snapshot_metadata VALUES(?,?)", (key, packed(value)))
        for spec in manifest["views"]:
            projection.unit_view(spec)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("foreign key violation")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise ValueError(str(exc) + "; incomplete stage retained: " + str(stage)) from exc
    finally:
        connection.close()
    reader = sqlite3.connect(stage.as_uri() + "?mode=ro", uri=True)
    try:
        if (
            reader.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or reader.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("closed-stage SQLite validation failed: " + str(stage))
    finally:
        reader.close()
    from .validation import validate

    validation = validate(stage, manifest_path)
    try:
        with stage.open("rb") as src, output.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    except Exception as exc:
        actual_size = output.stat().st_size if output.is_file() else None
        raise OSError(
            f"exclusive publication failed; actual output={output}; bytes={actual_size}; "
            f"validated stage={stage}"
        ) from exc
    published_digest = sha(output.read_bytes())
    if published_digest != validation["database_sha256"]:
        raise OSError(
            f"published output differs from validated stage; output={output}; stage={stage}"
        )
    return {
        "output": str(output),
        "sha256": published_digest,
        "stage": str(stage),
        "sqlite": sqlite3.sqlite_version,
        "library_version": LIBRARY_VERSION,
        "closed_stage_independent_validation": True,
    }
