"""Read-only queries over supplied frozen documentary records."""

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

UNIT_ORDER_SQL = """WITH manifest_order AS (
 SELECT CAST(j.key AS INTEGER) AS ordinal,json_extract(j.value,'$.sha256') AS unit_key
 FROM snapshot_metadata m,json_each(m.value_json,'$.views') j
 WHERE m.key='source_manifest'
) """

QUERIES: dict[str, str] = {
    "units": UNIT_ORDER_SQL
    + """SELECT u.*,
 (SELECT count(*) FROM v_body_rows r WHERE r.unit_key=u.unit_key) body_rows,
 (SELECT count(*) FROM v_body_cells c WHERE c.unit_key=u.unit_key) body_cells,
 (SELECT count(*) FROM cells c
  WHERE c.unit_key=u.unit_key AND c.cell_class='header') header_cells,
 (SELECT count(*) FROM dependencies d WHERE d.unit_key=u.unit_key) dependencies
 FROM units u JOIN manifest_order mo USING(unit_key) ORDER BY mo.ordinal""",
    "priority": UNIT_ORDER_SQL
    + """SELECT r.ordinal,r.row_key,r.documentary_role_json,
 p.value_json Lugar_json,p.cell_key Lugar_address,
 c.value_json Caso_json,c.cell_key Caso_address,
 s.value_json Situacion_json,s.cell_key Situacion_address,x.context_key,
 (SELECT group_concat(exact_text,char(10)) FROM
  (SELECT g.exact_text FROM segments g
   WHERE g.owner_key=x.context_key ORDER BY g.ordinal)) introduction_literal
 FROM v_body_rows r JOIN manifest_order mo ON mo.unit_key=r.unit_key
 JOIN v_body_cells p ON p.row_key=r.row_key AND p.column_role='place_text'
 JOIN v_body_cells c ON c.row_key=r.row_key AND c.column_role='case_description'
 JOIN v_body_cells s ON s.row_key=r.row_key AND s.column_role='published_situation'
 JOIN contexts x ON x.unit_key=r.unit_key ORDER BY mo.ordinal,r.ordinal""",
    "regional": UNIT_ORDER_SQL
    + """SELECT r.ordinal,r.row_key,r.documentary_role_json,
 a.value_json category_json,b.value_json count_json,d.value_json percentage_json,x.context_key,
 (SELECT group_concat(exact_text,char(10)) FROM
  (SELECT g.exact_text FROM segments g
   WHERE g.owner_key=x.context_key ORDER BY g.ordinal)) caption_literal,
 (SELECT count(*) FROM dependencies dp
  WHERE dp.unit_key=r.unit_key AND dp.state='unknown') unknown_dependencies
 FROM v_body_rows r JOIN manifest_order mo ON mo.unit_key=r.unit_key
 JOIN v_body_cells a ON a.row_key=r.row_key AND a.column_role='category'
 JOIN v_body_cells b ON b.row_key=r.row_key AND b.column_role='count'
 JOIN v_body_cells d ON d.row_key=r.row_key AND d.column_role='percentage'
 JOIN contexts x ON x.unit_key=r.unit_key ORDER BY mo.ordinal,r.ordinal""",
    "dependencies": UNIT_ORDER_SQL
    + """SELECT u.physical_page,d.* FROM dependencies d
 JOIN units u USING(unit_key) JOIN manifest_order mo USING(unit_key)
 ORDER BY mo.ordinal,d.ordinal""",
    "limits": """SELECT key,value_json FROM snapshot_metadata
 WHERE key IN ('scope','permissions','authorship')
 UNION ALL SELECT 'unit:'||physical_page||':provenance',provenance_json FROM units
 UNION ALL SELECT 'unit:'||physical_page||':coverage-and-exposure',exposure_json FROM units
 UNION ALL SELECT 'unit:'||physical_page||':permissions',permissions_json FROM units""",
    "trace": """SELECT c.cell_key,c.value_type,c.value_json,s.document_sha256,s.pointer,
 s.historical_record_sha256,w.word_key,w.text,w.span_json,w.bbox_json,w.frame,
 l.kind evidence_kind,l.record_key evidence_address,x.context_key,
 a.source_record assertion_source,a.attribution_json,a.stage_presence,a.stage_json
 FROM cells c JOIN source_records s ON s.address=c.cell_key
 JOIN owner_words ow ON ow.owner_key=c.cell_key JOIN words w USING(word_key)
 LEFT JOIN word_links l USING(word_key) JOIN contexts x ON x.unit_key=c.unit_key
 LEFT JOIN assertion_links al ON al.owner_key=x.context_key
 LEFT JOIN assertions a USING(assertion_key) WHERE c.cell_key=?
 ORDER BY ow.ordinal,l.kind,l.ordinal,al.ordinal""",
}


def query(database: Path, name: str, cell: str | None = None) -> list[dict[str, Any]]:
    database = Path(database).resolve()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    c = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA query_only=ON")
        if name == "trace" and cell is None:
            cell = c.execute(
                UNIT_ORDER_SQL + "SELECT cell_key FROM v_body_cells c "
                "JOIN manifest_order mo USING(unit_key) "
                "ORDER BY mo.ordinal,row_ordinal,cell_ordinal LIMIT 1"
            ).fetchone()[0]
        result = [dict(r) for r in c.execute(QUERIES[name], (cell,) if name == "trace" else ())]
    finally:
        c.close()
    if hashlib.sha256(database.read_bytes()).hexdigest() != before:
        raise ValueError("read-only query changed sealed database bytes")
    return result
