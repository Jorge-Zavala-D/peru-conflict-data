"""Read-only convenience exports; no scientific transformations or calculations."""

import csv
import hashlib
import html
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import queries as reader


def export(database: Path, folder: Path) -> dict[str, Any]:
    database = Path(database).resolve()
    folder = Path(folder)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = [
            dict(x)
            for x in connection.execute(
                reader.UNIT_ORDER_SQL
                + """
        SELECT u.physical_page,u.label,r.ordinal row_ordinal,r.row_class,
        r.documentary_role_json,r.row_key,rc.ordinal cell_ordinal,c.*,
        col.column_role,col.label_json,
        s.document_sha256,s.pointer,s.historical_record_sha256,s.storage_payload_sha256
        FROM cells c JOIN row_cells rc USING(cell_key) JOIN documentary_rows r USING(row_key)
        JOIN documentary_columns col USING(column_key) JOIN units u ON u.unit_key=c.unit_key
        JOIN manifest_order mo ON mo.unit_key=c.unit_key
        JOIN source_records s ON s.address=c.cell_key
        ORDER BY mo.ordinal,r.ordinal,rc.ordinal
        """
            )
        ]
    finally:
        connection.close()
    with (folder / "cells_long_utf8.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    results = {name: reader.query(database, name) for name in reader.QUERIES}
    with (folder / "sample_queries.json").open("x", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)

    def text(value: Any) -> str:
        return "" if value is None else html.escape(str(value)).replace("\n", "<br>")

    def table(records: list[dict[str, Any]], fields: list[str]) -> str:
        result = (
            "<table><thead><tr>"
            + "".join("<th>" + html.escape(f) + "</th>" for f in fields)
            + "</tr></thead><tbody>"
        )
        for record in records:
            result += (
                "<tr>" + "".join("<td>" + text(record.get(f)) + "</td>" for f in fields) + "</tr>"
            )
        return result + "</tbody></table>"

    priority: list[dict[str, Any]] = []
    for row in results["priority"]:
        priority.append(
            {
                "ordinal": row["ordinal"],
                **{
                    k: json.loads(row[f])
                    for k, f in [
                        ("Lugar", "Lugar_json"),
                        ("Caso", "Caso_json"),
                        ("Situación", "Situacion_json"),
                    ]
                },
                "original row address": row["row_key"],
                "context": row["context_key"],
            }
        )
    regional: list[dict[str, Any]] = []
    for row in results["regional"]:
        regional.append(
            {
                "ordinal": row["ordinal"],
                "documentary role": json.loads(row["documentary_role_json"]),
                **{
                    k: json.loads(row[f])
                    for k, f in [
                        ("category", "category_json"),
                        ("count", "count_json"),
                        ("percentage", "percentage_json"),
                    ]
                },
                "original row address": row["row_key"],
                "context": row["context_key"],
            }
        )
    body = """<!doctype html><html lang="en"><meta charset="utf-8">
    <title>Documentary inspection</title>
    <style>body{font:16px/1.5 system-ui;max-width:1200px;margin:2em auto;padding:0 1em}
    table{border-collapse:collapse;width:100%;margin:1em 0}
    td,th{border:1px solid #888;padding:.5em;vertical-align:top;overflow-wrap:anywhere}
    th{background:#eee;text-align:left}code{overflow-wrap:anywhere}</style>
    <h1>Selected documentary inspection snapshot</h1>
    <p>Noncanonical projection of supplied frozen context views. Not a complete report inventory,
    conflict-case/event database, scientific validation or release. Execution authority does not
    establish personal source review.</p>
    <p>Only display escaping and line-break rendering are applied here. Raw JSON values/types
    and original source bytes remain in SQLite. CSV is a convenience export, not canonical data.
    No arithmetic reconciliation or new interpretation is performed.</p>
    <h2>Priority documentary rows — selected priority profile</h2>"""
    for context_key, literal in dict.fromkeys(
        (row["context_key"], row["introduction_literal"]) for row in results["priority"]
    ):
        body += (
            "<p>Linked introduction "
            + text(context_key)
            + ", exact source text:</p><blockquote>"
            + text(literal)
            + "</blockquote>"
        )
    body += table(
        priority, ["ordinal", "Lugar", "Caso", "Situación", "original row address", "context"]
    )
    body += "<h2>Regional table — selected regional profile</h2>"
    for context_key, literal in dict.fromkeys(
        (row["context_key"], row["caption_literal"]) for row in results["regional"]
    ):
        body += (
            "<p>Linked caption "
            + text(context_key)
            + ", exact source text:</p><blockquote>"
            + text(literal)
            + "</blockquote>"
        )
    body += (
        "<p>The published TOTAL remains a separate documentary role, not a conflict case or "
        "recalculated aggregate. Column-scoped count/percentage qualifiers do not apply to the "
        "category column; reported-organization scope stays separate.</p>"
    )
    body += table(
        regional,
        [
            "ordinal",
            "documentary role",
            "category",
            "count",
            "percentage",
            "original row address",
            "context",
        ],
    )
    body += "<h2>Unresolved and unreviewed dependencies</h2>" + table(
        results["dependencies"], ["physical_page", "name", "state", "payload_json"]
    )
    body += "<h2>Permissions, attribution, exposure and coverage limits</h2>" + table(
        results["limits"], ["key", "value_json"]
    )
    body += (
        "<p>Inspection only. Normalization, automatic dispatch, scientific acceptance and "
        "benchmark scoring remain prohibited. Source-native own-text and coordinate frames "
        "are retained without PDF/image equivalence. Printed numbers remain source literals, "
        "not inferred aggregates or complete-inventory claims.</p></html>"
    )
    with (folder / "inspection_overview.html").open("x", encoding="utf-8") as handle:
        handle.write(body)
    with (folder / "queries.sql").open("x", encoding="utf-8") as handle:
        handle.write(
            "-- Read-only examples. Use the inspection query CLI; "
            "trace uses one bound ? parameter.\n"
        )
        for name, sql in reader.QUERIES.items():
            handle.write("\n-- " + name + "\n" + sql + ";\n")
    after = hashlib.sha256(database.read_bytes()).hexdigest()
    if before != after:
        raise ValueError("read-only export changed sealed database bytes")
    return {
        "database_sha256": after,
        "csv_records": len(rows),
        "body_cell_records": sum(r["cell_class"] == "body" for r in rows),
        "header_cell_records": sum(r["cell_class"] == "header" for r in rows),
        "query_counts": {k: len(v) for k, v in results.items()},
        "read_only_hash_unchanged": True,
        "display_only_changes": "HTML escaping/newline rendering; JSON/CSV retain raw strings.",
        "trace_fanout": (
            "Trace intentionally expands evidence/assertion links; body row and cell views do not."
        ),
    }
