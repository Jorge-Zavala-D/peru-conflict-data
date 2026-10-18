"""Invented inputs only; exercise the actual public receiving operation."""

import hashlib
import json
import tempfile
import unittest
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from peru_conflicts.execution.context_attachment import (
    attach_context,
    inspection_markdown,
    record_hash,
    write_view,
)


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def fixture(regional: bool = False) -> tuple[dict[str, Any], dict[str, bytes]]:
    texts = [
        "Intro",
        "scope",
        "March",
        "2021",
        "cases",
        "Place",
        "Case",
        "Situation",
        "1.",
        "Town",
        "Issue",
        "New",
    ]
    if regional:
        texts[5:8] = ["Category", "Total", "%"]
        texts[9:12] = ["North", "3", "25%"]
    words: list[dict[str, Any]] = []
    cursor = 0
    for index, text in enumerate(texts):
        words.append(
            {
                "text": text,
                "span": [cursor, cursor + len(text)],
                "bbox": [index * 10, 0, index * 10 + 8, 8],
            }
        )
        cursor += len(text) + 1
    native = {
        "physical_page": 9,
        "width": 200,
        "height": 300,
        "text": " ".join(texts),
        "words": words,
        "layout_lines": [{"words": words}],
    }
    cells = [
        {
            "column_index": i,
            "word_indices": [9 + i],
            "value": texts[9 + i],
            "status": "inherited",
            "line_word_indices": [[9 + i]],
            "value_origin": "invented original literal",
        }
        for i in range(3)
    ]
    proposal = {
        "rows": [{"original_row": "invented-1", "cells": cells, "status": "inherited"}],
        "header": {"word_indices": [5, 6, 7]},
        "ordinals": [{"word_index": 8}],
    }
    roles = (
        ["category", "count", "percentage"]
        if regional
        else ["place_text", "case_description", "published_situation"]
    )
    columns = [
        {"id": "col-" + str(i), "role": role, "source_index": i, "display_label": texts[5 + i]}
        for i, role in enumerate(roles)
    ]

    def ref(pointer: str) -> dict[str, str]:
        return {"document": "proposal", "pointer": pointer}

    descriptor = {
        "status": "lossless_receiving_descriptor_not_original_fields",
        "cells": [
            {
                "id": "dc" + str(i),
                "record_ref": ref("/rows/0/cells/" + str(i)),
                "row_id": "dr0",
                "column_id": "col-" + str(i),
                "value_key": "value",
            }
            for i in range(3)
        ],
        "rows": [
            {
                "id": "dr0",
                "record_ref": ref("/rows/0"),
                "ordered_cell_ids": ["dc0", "dc1", "dc2"],
                "grouping_format": "embedded_cells",
            }
        ],
        "metadata": [
            {"kind": "header", "record_ref": ref("/header"), "word_indices": [5, 6, 7]},
            {"kind": "ordinal", "record_ref": ref("/ordinals/0"), "word_indices": [8]},
        ],
        "word_evidence": [
            {
                "word_index": i,
                "record_ref": {"document": "native", "pointer": "/words/" + str(i)},
                "layout_pointers": ["/layout_lines/0/words/" + str(i)],
            }
            for i in range(12)
        ],
    }
    kind = "subject" if regional else "introductory_scope"
    assertion = {
        "status": "exposed_AI_interpretation",
        "attribution": "Codex AI",
        "stage": "new_attachment_interpretation",
        "context_segments": [[0, 1, 2, 3, 4]],
        "supports": [{"kind": kind, "target": "table_proposal", "segments": [[0, 1]]}],
    }
    assertions = {
        "attachment": assertion,
        "unknown": {"status": "unknown", "attribution": "Codex AI"},
        "none": {
            "status": "confirmed_none",
            "attribution": "invented evidence",
            "statement": "explicit none",
        },
        "empty": {"status": "reported_empty", "attribution": "invented evidence", "value": ""},
        "absent": {"status": "absent_field", "attribution": "invented schema evidence"},
        "unreviewed": {"status": "unreviewed_interpretation", "attribution": "Codex AI"},
    }
    profile = {
        "version": "SOURCE_BOUND_CONTEXT_ROLE_PROFILE_V001",
        "name": "regional_quantitative" if regional else "priority_documentary",
        "columns": columns,
    }
    objects: dict[str, Any] = {
        "native": native,
        "proposal": proposal,
        "descriptor": descriptor,
        "assertions": assertions,
        "profile": profile,
    }
    documents = {k: encoded(v) for k, v in objects.items()}
    request = {
        "contract": "SOURCE_BOUND_CONTEXT_ATTACHMENT_V002",
        "documents": {},
        "native_document": "native",
        "pdf_sha256": "a" * 64,
        "physical_page": 9,
        "descriptor_ref": {"document": "descriptor", "pointer": ""},
        "profile_ref": {"document": "profile", "pointer": ""},
        "context": {
            "kind": "caption" if regional else "introductory_paragraph",
            "segments": [[0, 1, 2, 3, 4]],
        },
        "attachment_assertion_refs": [{"document": "assertions", "pointer": "/attachment"}],
        "qualifiers": [
            {
                "kind": kind,
                "target": "table_proposal",
                "segments": [[0, 1]],
                "assertion_refs": [{"document": "assertions", "pointer": "/attachment"}],
            }
        ],
        "dependencies": [
            {
                "name": "scope_population",
                "state": "unknown",
                "evidence_refs": [{"document": "assertions", "pointer": "/unknown"}],
            }
        ],
        "lineage": {
            "cells": "inherited exposed Codex-AI proposal",
            "physical_page_prior_role": "context",
        },
        "execution_authority": "owner authorized developmental materialization, "
        "not personal source review",
        "alternative_completeness": False,
    }
    refresh(request, documents)
    return request, documents


def refresh(request: dict[str, Any], documents: dict[str, bytes]) -> None:
    request["documents"] = {
        k: {"sha256": hashlib.sha256(v).hexdigest()} for k, v in documents.items()
    }


def mutate(
    request: dict[str, Any],
    documents: dict[str, bytes],
    name: str,
    change: Callable[[dict[str, Any]], Any],
) -> None:
    value = json.loads(documents[name])
    change(value)
    documents[name] = encoded(value)
    refresh(request, documents)


class AttachmentTests(unittest.TestCase):
    def test_text_only_positive_preserves_originals_and_metadata(self) -> None:
        q, d = fixture()
        before = deepcopy(d)
        v = attach_context(q, d)
        self.assertEqual(d, before)
        self.assertEqual(
            [c["display_value_inherited"] for c in v["cell_references"]], ["Town", "Issue", "New"]
        )
        self.assertEqual(len(v["row_references"]), 1)
        self.assertEqual([m["kind"] for m in v["documentary_metadata"]], ["header", "ordinal"])
        self.assertEqual(v["context_node"]["kind"], "introductory_paragraph")
        self.assertEqual(v["qualifiers"][0]["resolution"], "attached_for_inspection_only")
        text = inspection_markdown(v)
        self.assertIn("| Place | Case | Situation |", text)
        self.assertIn("| Town | Issue | New |", text)
        self.assertNotIn("count measurements", text)

    def test_regional_scoped_compatibility(self) -> None:
        q, d = fixture(True)
        supports = [
            {"kind": "count_unit", "target": "count_column", "segments": [[4]]},
            {"kind": "percentage_sign", "target": "percentage_column", "segments": [[7]]},
        ]
        mutate(q, d, "assertions", lambda a: a["attachment"]["supports"].extend(supports))
        q["qualifiers"] += [
            dict(s, assertion_refs=q["attachment_assertion_refs"]) for s in supports
        ]
        v = attach_context(q, d)
        self.assertEqual(v["context_node"]["kind"], "caption")
        self.assertEqual(v["qualifiers"][1]["target"]["role"], "count")
        self.assertEqual(v["qualifiers"][2]["target"]["role"], "percentage")
        self.assertNotIn("count_unit", v["cell_references"][0])
        q["qualifiers"][1]["target"] = "table_proposal"
        with self.assertRaisesRegex(ValueError, "target_scope"):
            attach_context(q, d)

    def test_unsupported_and_missing_semantic_support_keep_literals(self) -> None:
        q, d = fixture()
        q["qualifiers"] += [
            {
                "kind": "count_unit",
                "target": "count_column",
                "segments": [[4]],
                "assertion_refs": q["attachment_assertion_refs"],
            },
            {
                "kind": "arbitrary_role",
                "target": "table_proposal",
                "segments": [[1]],
                "assertion_refs": [],
            },
        ]
        mutate(q, d, "assertions", lambda a: a["attachment"].update(supports=[]))
        v = attach_context(q, d)
        self.assertTrue(all(x["target"] is None for x in v["qualifiers"]))
        self.assertEqual(len(v["cell_references"]), 3)

    def test_literal_cue_and_AI_applicability_are_distinct(self) -> None:
        q, d = fixture(True)
        support = {"kind": "reporting_period", "target": "table_proposal", "segments": [[2, 3]]}
        mutate(q, d, "assertions", lambda a: a["attachment"]["supports"].append(support))
        q["qualifiers"].append(dict(support, assertion_refs=q["attachment_assertion_refs"]))
        item = attach_context(q, d)["qualifiers"][1]
        self.assertEqual(item["source_segments"][0]["exact_text"], "March 2021")
        self.assertEqual(item["applicability"][0]["status"], "exposed_AI_interpretation")
        self.assertNotIn("start_date", item)

    def test_dependency_states_do_not_collapse(self) -> None:
        q, d = fixture()
        for key, state in [
            ("none", "confirmed_none"),
            ("empty", "reported_empty"),
            ("absent", "absent_field"),
            ("unreviewed", "unreviewed_interpretation"),
        ]:
            q["dependencies"].append(
                {
                    "name": key,
                    "state": state,
                    "evidence_refs": [{"document": "assertions", "pointer": "/" + key}],
                }
            )
        v = attach_context(q, d)
        self.assertEqual(
            [x["state"] for x in v["dependencies"]],
            [
                "unknown",
                "confirmed_none",
                "reported_empty",
                "absent_field",
                "unreviewed_interpretation",
            ],
        )
        self.assertNotIn("exact_reported_value", v["dependencies"][0])
        self.assertEqual(v["dependencies"][2]["exact_reported_value"], "")

    def test_discontiguous_display_is_not_source_quote(self) -> None:
        q, d = fixture()
        q["qualifiers"][0].update(segments=[[0], [4]], display_text="Intro … cases")
        v = attach_context(q, d)
        item = v["qualifiers"][0]
        self.assertEqual([s["exact_text"] for s in item["source_segments"]], ["Intro", "cases"])
        self.assertFalse(item["display_is_contiguous_source_quote"])
        q["qualifiers"][0]["exact_contiguous_text"] = "Intro … cases"
        with self.assertRaisesRegex(ValueError, "contiguous_claim"):
            attach_context(q, d)

    def test_bad_hash_and_pointer_rejected(self) -> None:
        q, d = fixture()
        q["documents"]["native"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            attach_context(q, d)
        for pointer in [
            "/rows/-1/cells/0",
            "/rows/00/cells/0",
            "/rows/9/cells/0",
            "/rows/0/cells/nope",
            "/rows/0/cells/0/~2",
        ]:
            q, d = fixture()
            mutate(
                q,
                d,
                "descriptor",
                lambda a, pointer=pointer: a["cells"][0]["record_ref"].update(pointer=pointer),
            )
            with self.assertRaisesRegex(ValueError, "reference_unresolved"):
                attach_context(q, d)

    def test_body_conflict_not_solved_by_context_assertion(self) -> None:
        for index in [0, 8, 10, 999, -1]:
            q, d = fixture()
            mutate(
                q,
                d,
                "proposal",
                lambda a, index=index: a["rows"][0]["cells"][0].update(word_indices=[index]),
            )
            with self.assertRaises(ValueError):
                attach_context(q, d)

    def test_profile_cannot_invent_role_or_scope(self) -> None:
        q, d = fixture()
        mutate(q, d, "profile", lambda p: p["columns"][0].update(role="anything"))
        with self.assertRaisesRegex(ValueError, "profile_roles"):
            attach_context(q, d)
        q, d = fixture()
        q["qualifiers"][0]["target"] = "case_column"
        with self.assertRaisesRegex(ValueError, "target_scope"):
            attach_context(q, d)

    def test_attribution_and_permissions_cannot_upgrade(self) -> None:
        q, d = fixture()
        q["permissions"] = {"scientific_acceptance": True, "automatic_dispatch": True}
        v = attach_context(q, d)
        self.assertEqual(
            v["permissions"],
            {
                "inspection": True,
                "normalization": False,
                "automatic_dispatch": False,
                "scientific_acceptance": False,
                "benchmark_scoring": False,
            },
        )
        q["human_reviewed"] = True
        with self.assertRaisesRegex(ValueError, "evidence_reclassification"):
            attach_context(q, d)
        q, d = fixture()
        mutate(
            q,
            d,
            "assertions",
            lambda a: a["attachment"].update(attribution="Jorge Zavala", status="human_reviewed"),
        )
        with self.assertRaisesRegex(ValueError, "evidence_reclassification"):
            attach_context(q, d)

    def test_grouping_is_preserved_not_repaired(self) -> None:
        q, d = fixture()
        mutate(q, d, "descriptor", lambda a: a["rows"][0]["ordered_cell_ids"].reverse())
        with self.assertRaisesRegex(ValueError, "grouping_binding"):
            attach_context(q, d)

    def test_exclusive_output_never_overwrites(self) -> None:
        q, d = fixture()
        v = attach_context(q, d)
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "view.json"
            write_view(v, path)
            raw = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_view(v, path)
            self.assertEqual(path.read_bytes(), raw)


def legacy_fixture() -> tuple[dict[str, Any], dict[str, bytes]]:
    strings = [
        "Table",
        "X",
        "North",
        "COUNT",
        "March",
        "2021",
        "cases",
        "Category",
        "Total",
        "%",
        "Area",
        "8",
        "75%",
    ]
    words: list[dict[str, Any]] = []
    position = 0
    for i, literal in enumerate(strings):
        words.append(
            {
                "text": literal,
                "span": [position, position + len(literal)],
                "bbox": [i * 10, 0, i * 10 + 8, 8],
            }
        )
        position += len(literal) + 1
    native = {
        "physical_page": 9,
        "width": 200,
        "height": 300,
        "text": " ".join(strings),
        "words": words,
        "layout_lines": [{"words": words}],
    }
    cells = [
        {
            "cell_id": "local-cell-" + str(i),
            "evidence_pointer": "/unused/" + str(i),
            "row_id": "header" if i < 3 else "row1",
            "row_kind": "printed_header" if i < 3 else "category",
            "column_index": i % 3,
            "word_indices": [i + 7],
            "value_inherited_unchanged": strings[i + 7],
            "reconstruction_rule": "original single word",
            "bbox_union_not_PDF_cell_boundary": words[i + 7]["bbox"],
            "qualification": "invented source word union",
            "authorship": "inherited exposed Codex-AI proposal",
        }
        for i in range(6)
    ]
    grouping = [
        {
            "row_id": "header",
            "row_kind": "printed_header",
            "ordered_cell_ids": ["local-cell-0", "local-cell-1", "local-cell-2"],
            "status": "inherited proposal",
        },
        {
            "row_id": "row1",
            "row_kind": "category",
            "ordered_cell_ids": ["local-cell-3", "local-cell-4", "local-cell-5"],
            "status": "inherited proposal",
        },
    ]
    dossier = {
        "inherited_cells": cells,
        "inherited_grouping": grouping,
        "limits": {"status": "unknown"},
        "word_evidence": {
            str(i): dict(
                word_index=i,
                source_pointer="/words/" + str(i),
                layout_pointer=f"/layout_lines/0/words/{i}",
                **w,
            )
            for i, w in enumerate(words)
        },
    }
    propositions = {
        "propositions": [
            {
                "status": "exposed_AI_interpretation",
                "claim": "caption associated with table",
                "attribution": "exposed Codex AI",
            }
        ],
        "unknown": {"status": "unknown", "value": None},
        "none": {
            "status": "confirmed_none",
            "statement": "Explicitly no restriction",
            "attribution": "invented evidence",
        },
        "empty": {"status": "reported_empty", "value": "", "attribution": "invented evidence"},
    }
    objects: dict[str, Any] = {"native": native, "dossier": dossier, "propositions": propositions}
    documents = {
        key: json.dumps(value, ensure_ascii=False).encode() for key, value in objects.items()
    }
    ref = {"document": "propositions", "pointer": "/propositions/0"}
    request = {
        "contract": "SOURCE_BOUND_CONTEXT_ATTACHMENT_V001",
        "documents": {},
        "native_document": "native",
        "pdf_sha256": "a" * 64,
        "physical_page": 9,
        "cells_ref": {"document": "dossier", "pointer": "/inherited_cells"},
        "grouping_ref": {"document": "dossier", "pointer": "/inherited_grouping"},
        "word_evidence_ref": {"document": "dossier", "pointer": "/word_evidence"},
        "caption_word_indices": list(range(7)),
        "column_roles": {"category": 0, "count": 1, "percentage": 2},
        "attachment_assertion_refs": [ref],
        "execution_authority": "owner authorized developmental representation, "
        "not personal source review",
        "qualifiers": [
            {
                "kind": "subject",
                "segments": [[3]],
                "target": "table_proposal",
                "assertion_refs": [ref],
            },
            {
                "kind": "reporting_period",
                "segments": [[4, 5]],
                "target": "table_proposal",
                "assertion_refs": [ref],
                "qualification": "literal month/year, applicability inherited AI; no dates",
            },
            {
                "kind": "geographic_breakdown",
                "segments": [[2]],
                "target": "reported_organization",
                "assertion_refs": [ref],
            },
            {
                "kind": "count_unit",
                "segments": [[6]],
                "target": "count_column",
                "assertion_refs": [ref],
            },
            {
                "kind": "percentage_sign",
                "segments": [[9]],
                "target": "percentage_column",
                "assertion_refs": [ref],
            },
        ],
        "dependencies": [
            {
                "name": "population",
                "state": "unknown",
                "evidence_refs": [{"document": "propositions", "pointer": "/unknown"}],
            }
        ],
        "context_link_refs": [{"document": "dossier", "pointer": "/limits"}],
        "alternative_completeness": False,
    }
    refresh(request, documents)
    return request, documents


def adapted_fixture() -> tuple[dict[str, Any], dict[str, bytes]]:
    request, documents = legacy_fixture()
    dossier = json.loads(documents["dossier"])
    cells = dossier["inherited_cells"]
    groups = dossier["inherited_grouping"]

    def ref(p: str) -> dict[str, str]:
        return {"document": "dossier", "pointer": p}

    descriptor = {
        "cells": [
            {
                "id": "d" + c["cell_id"],
                "record_ref": ref("/inherited_cells/" + str(i)),
                "row_id": "d" + c["row_id"],
                "column_id": "col-" + str(c["column_index"]),
                "value_key": "value_inherited_unchanged",
            }
            for i, c in enumerate(cells)
        ],
        "rows": [
            {
                "id": "d" + g["row_id"],
                "record_ref": ref("/inherited_grouping/" + str(i)),
                "ordered_cell_ids": ["d" + cid for cid in g["ordered_cell_ids"]],
                "grouping_format": "ordered_original_ids",
            }
            for i, g in enumerate(groups)
        ],
        "metadata": [],
        "word_evidence": [
            {
                "word_index": int(i),
                "record_ref": ref("/word_evidence/" + i),
                "layout_pointers": [w["layout_pointer"]],
            }
            for i, w in dossier["word_evidence"].items()
        ],
    }
    profile = {
        "version": "SOURCE_BOUND_CONTEXT_ROLE_PROFILE_V001",
        "name": "regional_quantitative",
        "columns": [
            {"id": "col-" + str(index), "role": role, "source_index": index, "display_label": role}
            for role, index in request["column_roles"].items()
        ],
    }
    proposition = {
        "status": "inherited_proposal",
        "attribution": "Codex AI",
        "stage": "inherited_attachment_interpretation",
        "context_segments": [request["caption_word_indices"]],
        "supports": [
            {k: q[k] for k in ["kind", "target", "segments"]} for q in request["qualifiers"]
        ],
    }
    propositions = json.loads(documents["propositions"])
    propositions["propositions"] = [proposition]
    dependency_receiving = {
        "status": "unknown",
        "attribution": "Codex AI",
        "stage": "new invented compatibility descriptor declaration, not historical attribution",
        "inherited_state_ref": {"document": "propositions", "pointer": "/unknown"},
    }
    documents["dependency_receiving"] = json.dumps(dependency_receiving).encode()
    request["dependencies"][0]["evidence_refs"] = [
        {"document": "dependency_receiving", "pointer": ""}
    ]
    for name, value in [
        ("descriptor", descriptor),
        ("profile", profile),
        ("propositions", propositions),
    ]:
        documents[name] = json.dumps(value).encode()
    request.update(
        contract="SOURCE_BOUND_CONTEXT_ATTACHMENT_V002",
        descriptor_ref={"document": "descriptor", "pointer": ""},
        profile_ref={"document": "profile", "pointer": ""},
        context={"kind": "caption", "segments": [request["caption_word_indices"]]},
        lineage={"cells": "inherited invented V001 fixture"},
    )
    request["documents"] = {
        k: {"sha256": hashlib.sha256(v).hexdigest()} for k, v in documents.items()
    }
    return request, documents


class CompatibilityTests(unittest.TestCase):
    def test_existing_regional_populations_and_scopes(self) -> None:
        q, d = adapted_fixture()
        view = attach_context(q, d)
        old_cells = json.loads(d["dossier"])["inherited_cells"]
        self.assertEqual(
            [c["record_sha256"] for c in view["cell_references"]],
            [record_hash(c) for c in old_cells],
        )
        self.assertEqual(len(view["row_references"]), 2)
        self.assertEqual(
            [q["resolution"] for q in view["qualifiers"]], ["attached_for_inspection_only"] * 5
        )
        self.assertEqual(view["qualifiers"][3]["target"]["role"], "count")
        self.assertEqual(view["qualifiers"][4]["target"]["role"], "percentage")

    def test_V001_source_and_membership_protections(self) -> None:
        for mode in [
            "bad_hash",
            "duplicate_context",
            "duplicate_body",
            "bad_cell",
            "bad_layout",
            "human_upgrade",
            "complete_universe",
        ]:
            with self.subTest(mode=mode):
                q, d = adapted_fixture()
                if mode == "bad_hash":
                    q["documents"]["native"]["sha256"] = "0" * 64
                if mode == "duplicate_context":
                    q["context"]["segments"][0].append(10)
                if mode == "duplicate_body":
                    doc = json.loads(d["dossier"])
                    doc["inherited_cells"][4]["word_indices"] = [10]
                    d["dossier"] = json.dumps(doc).encode()
                if mode == "bad_cell":
                    q["descriptor_ref"]["pointer"] = "/missing"
                if mode == "bad_layout":
                    doc = json.loads(d["descriptor"])
                    doc["word_evidence"][0]["layout_pointers"] = ["/layout_lines/0/words/-1"]
                    d["descriptor"] = json.dumps(doc).encode()
                if mode == "human_upgrade":
                    q["human_reviewed"] = True
                if mode == "complete_universe":
                    q["alternative_completeness"] = True
                if mode not in ["bad_hash"]:
                    q["documents"] = {
                        k: {"sha256": hashlib.sha256(v).hexdigest()} for k, v in d.items()
                    }
                with self.assertRaises(ValueError):
                    attach_context(q, d)


class BoundaryDetails(unittest.TestCase):
    def test_inherited_joining_syntax_is_not_reconstructed(self) -> None:
        q, d = fixture()
        mutate(
            q,
            d,
            "proposal",
            lambda p: p["rows"][0]["cells"][1].update(
                value="Issue\n(qualifier)", value_origin="Inherited inserted joining syntax"
            ),
        )
        v = attach_context(q, d)
        self.assertEqual(v["cell_references"][1]["display_value_inherited"], "Issue\n(qualifier)")
        self.assertFalse(v["cell_references"][1]["display_value_is_contiguous_source_quote"])
        self.assertIn("Issue<br>(qualifier)", inspection_markdown(v))

    def test_native_evidence_identity_cannot_be_relabelled(self) -> None:
        q, d = fixture()
        mutate(q, d, "native", lambda n: n["words"][9].update(word_index=9, physical_page=100))
        with self.assertRaisesRegex(ValueError, "inherited_word_identity"):
            attach_context(q, d)

    def test_header_and_ordinal_ownership_are_not_substantive_cells(self) -> None:
        q, d = fixture()
        v = attach_context(q, d)
        self.assertEqual(len(v["cell_references"]), 3)
        self.assertEqual(len(v["documentary_metadata"]), 2)
        mutate(q, d, "descriptor", lambda p: p["metadata"][1].update(word_indices=[9]))
        with self.assertRaisesRegex(ValueError, "metadata_binding"):
            attach_context(q, d)

    def test_sources_and_previous_views_cannot_be_overwritten(self) -> None:
        q, d = fixture()
        v = attach_context(q, d)
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "native.json"
            source.write_bytes(d["native"])
            with self.assertRaises(FileExistsError):
                write_view(v, source)
            self.assertEqual(source.read_bytes(), d["native"])

    def test_dependency_does_not_upgrade_missing_evidence_to_known(self) -> None:
        q, d = fixture()
        q["dependencies"][0]["state"] = "confirmed_none"
        with self.assertRaisesRegex(ValueError, "dependency_evidence"):
            attach_context(q, d)

    def test_strict_json_and_incomplete_alternative_universe(self) -> None:
        q, d = fixture()
        q["alternative_completeness"] = True
        with self.assertRaisesRegex(ValueError, "alternative_completeness"):
            attach_context(q, d)
        q, d = fixture()
        d["native"] = b'{"words": [], "words": []}'
        refresh(q, d)
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            attach_context(q, d)
