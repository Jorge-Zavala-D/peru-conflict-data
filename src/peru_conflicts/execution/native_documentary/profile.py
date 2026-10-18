"""Compile sealed documentary cells for the unchanged source-addressed engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from peru_conflicts.execution import source_addressed_tables as engine

from .io import FRAME, box_union, pin, read, require, write


def _checked_inputs(
    candidate_path: Path,
    derivative_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], Path]:
    root = candidate_path.parent
    evidence_path = root / "source_word_evidence.json"
    sealed = read(root / "candidate_seal.json")
    sealed_paths: set[Path] = set()
    for item in sealed["files"]:
        current = pin(item["path"])
        require(
            all(current[k] == item[k] for k in ("sha256", "size_bytes")), "changed_sealed_output"
        )
        sealed_paths.add(Path(item["path"]).resolve())
    require(
        all(p.resolve() in sealed_paths for p in (candidate_path, derivative_path, evidence_path)),
        "missing_sealed_compiler_input",
    )
    candidate, derivative = read(candidate_path), read(derivative_path)
    require(derivative["candidate"] == pin(candidate_path), "derivative_candidate_mismatch")
    native_path = Path(candidate["input"]["path"])
    native_identity = pin(native_path)
    require(
        all(native_identity[k] == candidate["input"][k] for k in ("sha256", "size_bytes")),
        "native_identity_mismatch",
    )
    native = read(native_path)
    source_evidence = read(evidence_path)
    require(source_evidence["input"] == candidate["input"], "evidence_input_mismatch")
    evidence: list[dict[str, Any]] = source_evidence["words"]
    require(len(evidence) == len(native["words"]), "evidence_population_mismatch")
    for i, item in enumerate(evidence):
        require(item["word_index"] == i, "evidence_original_index_mismatch")
        require(
            all(item[k] == native["words"][i][k] for k in ("text", "span", "bbox")),
            "evidence_native_word_mismatch",
        )
        for pointer in item["layout_pointers"]:
            require(
                engine.pointer_value(native, pointer) == native["words"][i],
                "evidence_layout_pointer_mismatch",
            )
    return candidate, derivative, native, evidence, evidence_path


def _direct_validation(
    candidate: dict[str, Any],
    derivative: dict[str, Any],
    native: dict[str, Any],
    candidate_path: Path,
    derivative_path: Path,
) -> dict[str, Any]:
    """Check frozen memberships and transfers without discovering rows or calling adapters."""
    checks: list[dict[str, Any]] = []

    def check(ok: bool, name: str, address: str) -> None:
        checks.append({"pass": bool(ok), "check": name, "address": address})

    check(
        derivative["source_sha256"] == candidate["source"]["pdf_sha256"],
        "source_identity",
        "source_sha256",
    )
    check(
        derivative["physical_page"] == candidate["input"]["physical_page"], "physical_page", "input"
    )
    check(derivative["native_sha256"] == candidate["input"]["sha256"], "native_identity", "input")
    results: list[dict[str, Any]] = candidate["results"]
    check(len({r["region_id"] for r in results}) == len(results), "unique_regions", "results")
    expected_tables: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for result in results:
        selected = [r for r in result["rows"] if r["status"] == "accepted"]
        if result["status"] == "processed" and selected:
            expected_tables.append((result, selected))
        allowed = set(result["view"]["word_indices"])
        header = result["header"]
        if header is not None:
            check(
                set(header["word_indices"]) <= allowed
                and header["labels"]
                == [native["words"][i]["text"] for i in header["word_indices"]],
                "literal_header_transfer",
                result["region_id"],
            )
        for row in selected:
            address = row["row_id"]
            if result["adapter"] == "priority":
                ordinal = row["ordinal"]
                check(
                    ordinal["word_index"] in allowed
                    and ordinal["text"] == native["words"][ordinal["word_index"]]["text"],
                    "original_ordinal",
                    address,
                )
            for c in row["cells"]:
                ids = c["word_indices"]
                check(
                    c["status"] == "processed" and bool(ids) and set(ids) <= allowed,
                    "admitted_processed_cell",
                    address + ":" + c["field"],
                )
                check(
                    [i for line in c["line_word_indices"] for i in line] == ids,
                    "original_line_membership",
                    address + ":" + c["field"],
                )
                value = "\n".join(
                    " ".join(native["words"][i]["text"] for i in line)
                    for line in c["line_word_indices"]
                )
                check(c["value"] == value, "literal_word_transfer", address + ":" + c["field"])
                check(
                    c["bbox"] == box_union([native["words"][i]["bbox"] for i in ids]),
                    "source_word_union",
                    address + ":" + c["field"],
                )
    check(len(derivative["tables"]) == len(expected_tables), "derivative_table_count", "tables")
    for table, (result, selected) in zip(derivative["tables"], expected_tables, strict=False):
        values = [result["header"]["labels"]] + [
            ([row["ordinal"]["text"]] if result["adapter"] == "priority" else [])
            + [c["value"] for c in row["cells"]]
            for row in selected
        ]
        check(
            table["region_id"] == result["region_id"] and table["cells"] == values,
            "derivative_exact_cells",
            result["region_id"],
        )
    failures = [item for item in checks if not item["pass"]]
    return {
        "version": "NATIVE_DOCUMENTARY_DIRECT_TRANSFER_VALIDATION_V001",
        "candidate": pin(candidate_path),
        "derivative": pin(derivative_path),
        "passed_checks": len(checks) - len(failures),
        "failed_checks": len(failures),
        "failures": failures,
        "generation_not_called": True,
        "scientific_validation": False,
    }


def _build(candidate_path: Path, derivative_path: Path) -> dict[str, Any]:
    candidate, derivative, native, evidence, evidence_path = _checked_inputs(
        candidate_path,
        derivative_path,
    )
    validation_path = candidate_path.parent / "direct_validation.json"
    audit = _direct_validation(candidate, derivative, native, candidate_path, derivative_path)
    if validation_path.exists():
        existing = read(validation_path)
        require(existing == audit, "audit_not_current_inputs")
    else:
        write(validation_path, audit)
    require(
        audit["failed_checks"] == 0 and audit["generation_not_called"], "failed_direct_validation"
    )
    source = candidate["source"]
    config: dict[str, Any] = {
        "contract_version": "SOURCE_ADDRESSED_TABLE_CONFIG_V001",
        "profile_id": "source-native-documentary-pipeline-v001",
        "source": {"pdf_sha256": source["pdf_sha256"], "report_number": source["report_number"]},
        "inputs": [
            {
                "input_id": "composed",
                "physical_page": candidate["input"]["physical_page"],
                **pin(derivative_path),
                "expected_table_count": len(derivative["tables"]),
                "expected_status": "region_scoped_native_word_derivative_v001",
            }
        ],
        "artifacts": [],
        "layouts": [],
    }
    for artifact_id, path in (
        ("native", Path(candidate["input"]["path"])),
        ("candidate", candidate_path),
        ("evidence", evidence_path),
        ("validation", validation_path),
    ):
        config["artifacts"].append({"artifact_id": artifact_id, "kind": "json", **pin(path)})
    for ti, table in enumerate(derivative["tables"]):
        ri, result = next(
            (i, r)
            for i, r in enumerate(candidate["results"])
            if r["region_id"] == table["region_id"]
        )
        priority = result["adapter"] == "priority"
        head = result["header"]
        selected = [(i, r) for i, r in enumerate(result["rows"]) if r["status"] == "accepted"]
        require(bool(selected), "derivative_without_accepted_rows")
        layout: dict[str, Any] = {
            "layout_id": result["region_id"],
            "input_id": "composed",
            "table_index": ti,
            "array_length": len(head["labels"]),
            "expected_table_rows": len(table["cells"]),
            "header_rows": [0],
            "header_mask": [
                {"row": 0, "column": i, "type": "named_string", "value": label}
                for i, label in enumerate(head["labels"])
            ],
            "columns": [
                {
                    "field_id": c["field"],
                    "column_index": c["column_index"],
                    "label": head["labels"][c["column_index"]],
                    "header_fragments": [{"row": 0, "column": c["column_index"]}],
                }
                for c in selected[0][1]["cells"]
            ],
            "role": "primary" if priority else "published_aggregate",
            "rows": [],
        }
        if priority:
            layout["ordinal_column"] = 0
        for seq, (rindex, row) in enumerate(selected, 1):
            anchors: dict[str, Any] = {}
            for ci, c in enumerate(row["cells"]):
                pointers = [f"/words/{i}" for i in c["word_indices"]]
                pointers += [
                    p
                    for i in c["word_indices"]
                    for p in cast("list[str]", evidence[i]["layout_pointers"])
                ]
                anchors[c["field"]] = [
                    {
                        "anchor_id": f"t{ti}_r{seq}_c{ci}_native",
                        "artifact_id": "native",
                        "kind": "json_pointer",
                        "json_pointers": pointers,
                        "assertions": [
                            {"pointer": f"/words/{i}", "value": native["words"][i]}
                            for i in c["word_indices"]
                        ],
                        "metadata": {
                            "coordinate_representation": FRAME,
                            "recorded_native_dimensions": candidate["input"]["dimensions"],
                            "native_word_union": c["bbox"],
                            "PDF_or_image_equivalence": False,
                            "span_frame": "original native JSON /text",
                            "admission_sha256": candidate["admission"]["sha256"],
                            "region_id": result["region_id"],
                            "joining_policy": "U+0020 between words; U+000A between geometry lines",
                            "canonical_identity_created": False,
                        },
                    },
                    {
                        "anchor_id": f"t{ti}_r{seq}_c{ci}_sealed",
                        "artifact_id": "candidate",
                        "kind": "json_pointer",
                        "json_pointers": [
                            f"/results/{ri}/rows/{rindex}/cells/{ci}",
                            f"/results/{ri}/view",
                        ],
                        "assertions": [
                            {
                                "pointer": f"/results/{ri}/rows/{rindex}/cells/{ci}/status",
                                "value": "processed",
                            }
                        ],
                    },
                ]
            item = {
                "row_id": row["row_id"],
                "array_row_index": seq,
                "sequence": seq,
                "field_anchors": anchors,
            }
            if priority:
                item["expected_ordinal"] = row["ordinal"]["text"]
            layout["rows"].append(item)
        config["layouts"].append(layout)
    require(bool(config["layouts"]), "no_qualified_derivative")
    engine.validate_config(config)
    return config


def build(root: Path) -> dict[str, Any]:
    """Compile an existing sealed output bundle, without running the engine."""
    return _build(root / "composed_candidate.json", root / "table_derivative.json")


def compile_profile(
    candidate_path: Path,
    derivative_path: Path,
    output_path: Path,
    engine_sha256: str,
) -> dict[str, Any]:
    """Pin the installed unchanged engine and exclusively write its strict configuration."""
    require(pin(engine.__file__)["sha256"] == engine_sha256, "engine_identity_mismatch")
    config = _build(candidate_path, derivative_path)
    write(output_path, config)
    return config
