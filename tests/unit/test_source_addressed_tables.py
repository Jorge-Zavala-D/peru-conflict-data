"""Public CLI checks using invented table bytes and source addresses only."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import subprocess
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "extract_source_addressed_tables.py"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invented_config(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "invented-table.json"
    write_json(
        source,
        {
            "source_sha256": "a" * 64,
            "physical_page": 41,
            "status": "invented-table-status",
            "authority": "invented-test-authority",
            "empty_table_result_certifies_absence": False,
            "tables": [
                {
                    "cells": [
                        ["Invented label", "Invented note"],
                        ["Invented A", "line one\nline two"],
                    ],
                    "bbox": [0, 0, 100, 50],
                }
            ],
        },
    )
    return {
        "contract_version": "SOURCE_ADDRESSED_TABLE_CONFIG_V001",
        "profile_id": "invented-single-header",
        "source": {"pdf_sha256": "a" * 64, "report_number": 900001},
        "inputs": [
            {
                "input_id": "invented-input",
                "physical_page": 41,
                "path": str(source),
                "sha256": sha256(source),
                "size_bytes": source.stat().st_size,
                "expected_table_count": 1,
            }
        ],
        "artifacts": [],
        "frames": [],
        "layouts": [
            {
                "layout_id": "invented-layout",
                "input_id": "invented-input",
                "table_index": 0,
                "array_length": 2,
                "expected_table_rows": 2,
                "header_rows": [0],
                "header_mask": [
                    {"row": 0, "column": 0, "type": "named_string", "value": "Invented label"},
                    {"row": 0, "column": 1, "type": "named_string", "value": "Invented note"},
                ],
                "columns": [
                    {
                        "field_id": "label",
                        "column_index": 0,
                        "label": "Invented label",
                        "header_fragments": [{"row": 0, "column": 0}],
                        "header_joiner": " ",
                    },
                    {
                        "field_id": "note",
                        "column_index": 1,
                        "label": "Invented note",
                        "header_fragments": [{"row": 0, "column": 1}],
                        "header_joiner": " ",
                    },
                ],
                "rows": [
                    {
                        "row_id": "INVENTED_ROW_1",
                        "array_row_index": 1,
                        "sequence": 1,
                        "field_anchors": {},
                    }
                ],
                "role": "primary",
                "fragments": [],
            }
        ],
    }


def run_cli(
    tmp_path: Path, config: dict[str, Any], *, output_name: str = "candidate.json"
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path]:
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    output = tmp_path / output_name
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--config", str(config_path), "--output", str(output)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert output.is_file(), result.stderr or result.stdout
    candidate: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
    return result, candidate, output


def test_actual_cli_single_header_preserves_multiline(tmp_path: Path) -> None:
    completed, candidate, _ = run_cli(tmp_path, invented_config(tmp_path))
    assert completed.returncode == 0, completed.stderr
    assert candidate["candidate_status"] == "processed"
    assert len(candidate["documentary_rows"]) == 1
    row = candidate["documentary_rows"][0]
    assert row["row_id"] == "INVENTED_ROW_1"
    field = row["fields"]["note"]
    assert field["processing_status"] == "processed"
    assert field["state"] == "observed"
    assert field["original_value"] == "line one\nline two"
    assert field["typed_value_json"] == '"line one\\nline two"'
    assert field["source_lexical_json_token"] == '"line one\\nline two"'


def replace_input(
    config: dict[str, Any], index: int, mutate: Callable[[dict[str, Any]], None]
) -> None:
    descriptor = config["inputs"][index]
    path = Path(descriptor["path"])
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    write_json(path, document)
    descriptor.update(sha256=sha256(path), size_bytes=path.stat().st_size)


def rewrite_input_bytes(config: dict[str, Any], index: int, raw: bytes) -> None:
    descriptor = config["inputs"][index]
    path = Path(descriptor["path"])
    path.write_bytes(raw)
    descriptor.update(sha256=sha256(path), size_bytes=path.stat().st_size)


def rich_config(tmp_path: Path) -> dict[str, Any]:
    config = invented_config(tmp_path)
    config["profile_id"] = "invented-multiple-layouts"
    primary = config["layouts"][0]
    aggregate = copy.deepcopy(primary)
    primary.update(
        array_length=6,
        expected_table_rows=4,
        header_rows=[0, 1],
        ordinal_column=0,
        columns=[
            {
                "field_id": "label",
                "column_index": 1,
                "label": "Invented label",
                "header_fragments": [{"row": 0, "column": 1}, {"row": 1, "column": 1}],
                "header_joiner": " ",
            },
            {
                "field_id": "note",
                "column_index": 4,
                "label": "Current note",
                "header_fragments": [{"row": 0, "column": 4}, {"row": 1, "column": 4}],
                "header_joiner": " ",
            },
        ],
        rows=[
            {
                "row_id": "INVENTED_PRIMARY_1",
                "array_row_index": 2,
                "sequence": 1,
                "expected_ordinal": "17",
                "field_anchors": {},
            }
        ],
        fragments=[
            {
                "fragment_id": "INVENTED_FRAGMENT_1",
                "array_row_index": 3,
                "column_index": 1,
                "anchors": [],
            }
        ],
    )
    headers = [["", "Invented", None, "", "Current", None], [None, "label", "", None, "note", ""]]
    primary["header_mask"] = [
        {
            "row": row,
            "column": column,
            "type": "null" if value is None else "empty_string" if value == "" else "named_string",
            "value": value,
        }
        for row, cells in enumerate(headers)
        for column, value in enumerate(cells)
    ]

    def populate(document: dict[str, Any]) -> None:
        document["tables"][0]["cells"] = [
            *headers,
            ["17", "Á  invented\nsecond line", None, None, "bad-day/00/not-a-date", None],
            [None, "invented continuation", None, "other context", None, None],
        ]

    replace_input(config, 0, populate)
    second = copy.deepcopy(config["inputs"][0])
    second.update(
        input_id="invented-second",
        physical_page=42,
        path=str(tmp_path / "invented-second.json"),
        expected_table_count=2,
    )
    write_json(
        Path(second["path"]),
        {
            "source_sha256": "a" * 64,
            "physical_page": 42,
            "status": "invented-table-status",
            "authority": "invented-test-authority",
            "empty_table_result_certifies_absence": False,
            "tables": [
                {
                    "cells": [
                        *headers,
                        ["18", "Invented context", None, None, "literal context", None],
                    ],
                    "bbox": [2, 3, 90, 60],
                },
                {
                    "cells": [["Invented measure", "Invented total"], ["Invented summary", "3"]],
                    "bbox": [2, 70, 90, 90],
                },
            ],
        },
    )
    second.update(
        sha256=sha256(Path(second["path"])), size_bytes=Path(second["path"]).stat().st_size
    )
    config["inputs"].append(second)
    context = copy.deepcopy(primary)
    context.update(
        layout_id="invented-context",
        input_id="invented-second",
        role="context",
        expected_table_rows=3,
        rows=[
            {
                "row_id": "INVENTED_CONTEXT_1",
                "array_row_index": 2,
                "sequence": 2,
                "expected_ordinal": "18",
                "field_anchors": {},
            }
        ],
        fragments=[],
    )
    aggregate.update(
        layout_id="invented-aggregate",
        input_id="invented-second",
        table_index=1,
        role="published_aggregate",
        rows=[{"row_id": "INVENTED_AGGREGATE_1", "array_row_index": 1, "field_anchors": {}}],
    )
    for index, (field, label) in enumerate(
        (("measure", "Invented measure"), ("total", "Invented total"))
    ):
        aggregate["columns"][index].update(field_id=field, label=label)
        aggregate["header_mask"][index]["value"] = label
    config["layouts"].extend((context, aggregate))
    return config


def png_bytes(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * width * 3) * height))
        + chunk(b"IEND", b"")
    )


def add_anchors(tmp_path: Path, config: dict[str, Any]) -> None:
    image = tmp_path / "invented-image.png"
    image.write_bytes(png_bytes(80, 60))
    grid = tmp_path / "invented-grid.json"
    write_json(grid, {"physical_page": 41, "row": {"bbox": [1, 2, 20, 10]}})
    config["artifacts"] = [
        {
            "artifact_id": "invented-image",
            "kind": "image",
            "path": str(image),
            "sha256": sha256(image),
            "size_bytes": image.stat().st_size,
            "assertions": [],
        },
        {
            "artifact_id": "invented-grid",
            "kind": "json",
            "path": str(grid),
            "sha256": sha256(grid),
            "size_bytes": grid.stat().st_size,
            "assertions": [{"pointer": "/physical_page", "value": 41}],
        },
    ]
    config["frames"] = [
        {
            "frame_id": "invented-pixels",
            "image_artifact_id": "invented-image",
            "physical_page": 41,
            "width": 80,
            "height": 60,
            "coordinate_system": "image_top_left_pixels_v1",
            "origin": "top_left",
            "units": "pixels",
            "x_direction": "right",
            "y_direction": "down",
        }
    ]
    first = {
        "anchor_id": "invented-box-one",
        "artifact_id": "invented-image",
        "kind": "image_box",
        "frame_id": "invented-pixels",
        "bbox": [1, 2, 20, 10],
        "json_pointers": [],
        "assertions": [],
        "metadata": {"purpose": "invented evidence"},
    }
    second = {**first, "anchor_id": "invented-box-two", "bbox": [2, 3, 25, 11]}
    pointer: dict[str, Any] = {
        "anchor_id": "invented-grid-anchor",
        "artifact_id": "invented-grid",
        "kind": "json_pointer",
        "json_pointers": ["/row/bbox"],
        "assertions": [{"pointer": "/physical_page", "value": 41}],
        "metadata": {},
    }
    config["layouts"][0]["rows"][0]["field_anchors"] = {"label": [first, second, pointer]}


def selected_field(candidate: dict[str, Any], field_id: str = "note") -> dict[str, Any]:
    field: dict[str, Any] = candidate["documentary_rows"][0]["fields"][field_id]
    return field


def test_actual_cli_separates_primary_context_aggregate_fragment_and_ordinal(
    tmp_path: Path,
) -> None:
    config = rich_config(tmp_path)
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 0, completed.stderr
    assert candidate["candidate_status"] == "processed"
    assert [row["source_role"] for row in candidate["documentary_rows"]] == ["primary", "context"]
    assert len(candidate["published_measurements"]) == 1
    assert len(candidate["continuation_fragments"]) == 1
    primary = candidate["documentary_rows"][0]
    assert primary["documentary_ordinal"] == "17"
    assert set(primary["fields"]) == {"label", "note"}
    assert "case_id" not in primary and "canonical_id" not in primary
    assert selected_field(candidate)["original_value"] == "bad-day/00/not-a-date"
    assert candidate["published_measurements"][0]["fields"]["total"]["original_value"] == "3"
    fragment = candidate["continuation_fragments"][0]
    assert fragment["context_only"] is True
    assert fragment["creates_observation"] is False
    assert fragment["field"]["original_value"] == "invented continuation"
    assert fragment["native_table_bbox"] == [0, 0, 100, 50]
    assert any(
        cell["original_value"] == "other context" for cell in fragment["unselected_context_cells"]
    )


def test_actual_cli_preserves_multiple_image_and_grid_anchors(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    add_anchors(tmp_path, config)
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 0, completed.stderr
    field = selected_field(candidate, "label")
    assert candidate["documentary_rows"][0]["native_table_bbox"] == [0, 0, 100, 50]
    assert candidate["native_coordinate_claim"] == "serialized_native_coordinates_only_unqualified"
    assert candidate["pdf_to_image_transform"] is None
    assert candidate["frames"][0]["coordinate_system"] == "image_top_left_pixels_v1"
    anchors = field["evidence_anchors"]
    assert [anchor["anchor_id"] for anchor in anchors] == [
        "invented-box-one",
        "invented-box-two",
        "invented-grid-anchor",
    ]
    assert anchors[0]["bbox"] == [1, 2, 20, 10]
    assert anchors[1]["bbox"] == [2, 3, 25, 11]
    assert anchors[2]["json_pointers"] == ["/row/bbox"]
    assert field["image_cell_box"] is not None


@pytest.mark.parametrize(
    ("value", "status", "kind", "state"),
    [
        (None, "unavailable_null_cell", "null", None),
        ("", "processed", "string", "observed"),
        (False, "invalid_cell_type", "boolean", None),
        (0, "invalid_cell_type", "number", None),
    ],
)
def test_actual_cli_distinguishes_null_empty_false_and_zero(
    tmp_path: Path, value: Any, status: str, kind: str, state: str | None
) -> None:
    config = invented_config(tmp_path)
    replace_input(
        config, 0, lambda document: document["tables"][0]["cells"][1].__setitem__(1, value)
    )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == (0 if status == "processed" else 2)
    field = selected_field(candidate)
    assert field["processing_status"] == status
    assert field["type"] == kind
    assert field["state"] == state
    assert type(field["original_value"]) is type(value)
    assert field["original_value"] == value
    assert field["source_lexical_json_token"] == json.dumps(value, ensure_ascii=False)


def test_actual_cli_missing_cell_remains_missing(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    replace_input(config, 0, lambda document: document["tables"][0]["cells"][1].pop())
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    field = selected_field(candidate)
    assert field["processing_status"] == "unavailable_missing_cell"
    assert field["type"] == "missing"
    assert field["state"] is None
    assert field["source_lexical_json_token"] is None


def test_actual_cli_keeps_source_escapes_separate_from_typed_unicode(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    value = "á  repeated spaces\nsecond line"
    path = Path(config["inputs"][0]["path"])
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    document["tables"][0]["cells"][1][1] = value
    rewrite_input_bytes(
        config, 0, json.dumps(document, ensure_ascii=True, indent=2).encode("utf-8")
    )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 0
    field = selected_field(candidate)
    assert field["original_value"] == value
    assert field["source_lexical_json_token"] == json.dumps(value, ensure_ascii=True)
    assert field["typed_value_json"] == json.dumps(value, ensure_ascii=False)
    assert field["source_lexical_json_token"] != field["typed_value_json"]


@pytest.mark.parametrize(
    "failure",
    [
        "hash",
        "page",
        "pdf",
        "table",
        "input_id",
        "duplicate_row",
        "duplicate_field",
        "duplicate_input",
        "missing_header_mask",
        "duplicate_header_mask",
    ],
)
def test_actual_cli_rejects_wrong_identity_and_configuration(tmp_path: Path, failure: str) -> None:
    config = invented_config(tmp_path)
    layout = config["layouts"][0]
    if failure == "hash":
        config["inputs"][0]["sha256"] = "b" * 64
    elif failure == "page":
        replace_input(config, 0, lambda document: document.__setitem__("physical_page", 99))
    elif failure == "pdf":
        replace_input(config, 0, lambda document: document.__setitem__("source_sha256", "b" * 64))
    elif failure == "table":
        layout["table_index"] = 7
    elif failure == "input_id":
        layout["input_id"] = "unconfigured-input"
    elif failure == "duplicate_row":
        layout["rows"].append(copy.deepcopy(layout["rows"][0]))
    elif failure == "duplicate_field":
        layout["columns"].append(copy.deepcopy(layout["columns"][0]))
    elif failure == "duplicate_input":
        config["inputs"].append(copy.deepcopy(config["inputs"][0]))
    elif failure == "missing_header_mask":
        layout["header_mask"].pop()
    else:
        layout["header_mask"].append(copy.deepcopy(layout["header_mask"][0]))
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] == "input_rejected"
    assert candidate["errors"]


@pytest.mark.parametrize(
    "failure",
    [
        "coordinate_system",
        "page",
        "dimensions",
        "artifact_id",
        "artifact_hash",
        "anchor_frame",
        "anchor_outside",
        "pointer",
        "assertion",
        "duplicate_anchor",
    ],
)
def test_actual_cli_rejects_unbound_evidence(tmp_path: Path, failure: str) -> None:
    config = invented_config(tmp_path)
    add_anchors(tmp_path, config)
    anchors = config["layouts"][0]["rows"][0]["field_anchors"]["label"]
    if failure == "coordinate_system":
        config["frames"][0]["coordinate_system"] = "unqualified_native"
    elif failure == "page":
        config["frames"][0]["physical_page"] = 99
    elif failure == "dimensions":
        config["frames"][0]["width"] = 999
    elif failure == "artifact_id":
        config["frames"][0]["image_artifact_id"] = "unconfigured-image"
    elif failure == "artifact_hash":
        config["artifacts"][0]["sha256"] = "b" * 64
    elif failure == "anchor_frame":
        anchors[0]["frame_id"] = "unconfigured-frame"
    elif failure == "anchor_outside":
        anchors[0]["bbox"] = [1, 2, 999, 10]
    elif failure == "pointer":
        anchors[2]["json_pointers"] = ["/not-present"]
    elif failure == "assertion":
        anchors[2]["assertions"][0]["value"] = 999
    else:
        anchors.append(copy.deepcopy(anchors[0]))
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] in ("partial", "input_rejected")
    assert candidate["errors"]
    if candidate["documentary_rows"]:
        assert selected_field(candidate, "label")["processing_status"] != "processed"


def test_actual_cli_partial_layout_retains_all_planned_cells(tmp_path: Path) -> None:
    config = rich_config(tmp_path)
    replace_input(
        config,
        0,
        lambda document: document["tables"][0]["cells"][2].__setitem__(2, "unexpected filler"),
    )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] == "partial"
    assert len(candidate["documentary_rows"]) == 2
    assert len(candidate["published_measurements"]) == 1
    assert len(candidate["continuation_fragments"]) == 1
    assert all(
        field["processing_status"] != "processed"
        for field in candidate["documentary_rows"][0]["fields"].values()
    )
    assert all(
        field["processing_status"] == "processed"
        for field in candidate["documentary_rows"][1]["fields"].values()
    )
    assert any(error["scope"] == "layout" for error in candidate["errors"])


@pytest.mark.parametrize("failure", ["header_null_empty", "header_named", "ordinal"])
def test_actual_cli_header_types_and_ordinals_do_not_coalesce(tmp_path: Path, failure: str) -> None:
    config = rich_config(tmp_path)
    if failure == "header_null_empty":
        replace_input(
            config, 0, lambda document: document["tables"][0]["cells"][0].__setitem__(2, "")
        )
    elif failure == "header_named":
        replace_input(
            config,
            0,
            lambda document: document["tables"][0]["cells"][0].__setitem__(1, "different label"),
        )
    else:
        replace_input(
            config, 0, lambda document: document["tables"][0]["cells"][2].__setitem__(0, "18")
        )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] == "partial"
    assert selected_field(candidate)["state"] is None


@pytest.mark.parametrize(
    "failure", ["duplicate_key", "nan", "infinity", "invalid_unicode", "invalid_utf8"]
)
def test_actual_cli_strict_input_json_does_not_create_observations(
    tmp_path: Path, failure: str
) -> None:
    config = invented_config(tmp_path)
    raw = Path(config["inputs"][0]["path"]).read_bytes()
    if failure == "duplicate_key":
        raw = raw.replace(
            b'"status": "invented-table-status"',
            b'"status": "invented-table-status", "status": "second invented status"',
        )
    else:
        replacement = {
            "nan": b"NaN",
            "infinity": b"Infinity",
            "invalid_unicode": b'"\\ud800"',
            "invalid_utf8": b'"\xff"',
        }[failure]
        raw = raw.replace(b'"line one\\nline two"', replacement)
    rewrite_input_bytes(config, 0, raw)
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] == "input_rejected"
    assert selected_field(candidate)["state"] is None
    assert selected_field(candidate)["type"] is None
    assert selected_field(candidate)["processing_status"] != "processed"
    assert any(error["scope"] == "input" for error in candidate["errors"])


def test_actual_cli_payload_is_deterministic_and_output_is_exclusive(tmp_path: Path) -> None:
    config = rich_config(tmp_path)
    first, first_candidate, output = run_cli(tmp_path, config)
    second, second_candidate, _ = run_cli(tmp_path, config, output_name="second-candidate.json")
    assert first.returncode == second.returncode == 0
    assert {key: value for key, value in first_candidate.items() if key != "runtime"} == {
        key: value for key, value in second_candidate.items() if key != "runtime"
    }
    original_bytes = output.read_bytes()
    collision, _, _ = run_cli(tmp_path, config)
    assert collision.returncode != 0
    assert output.read_bytes() == original_bytes


def test_actual_cli_preserves_mathematically_finite_huge_native_integer(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    native_bbox = [0, 0, 10**400, 50]
    replace_input(
        config, 0, lambda document: document["tables"][0].__setitem__("bbox", native_bbox)
    )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 0, completed.stderr
    assert candidate["candidate_status"] == "processed"
    assert candidate["documentary_rows"][0]["native_table_bbox"] == native_bbox
    assert candidate["native_coordinate_claim"] == "serialized_native_coordinates_only_unqualified"
    assert candidate["pdf_to_image_transform"] is None


def test_actual_cli_rejects_huge_image_box_with_a_receipt(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    add_anchors(tmp_path, config)
    config["layouts"][0]["rows"][0]["field_anchors"]["label"][0]["bbox"] = [1, 2, 10**400, 10]
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] in ("partial", "input_rejected")
    assert candidate["errors"]
    if candidate["documentary_rows"]:
        assert selected_field(candidate, "label")["processing_status"] != "processed"


def test_actual_cli_accepts_root_json_pointer_anchor(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    add_anchors(tmp_path, config)
    config["layouts"][0]["rows"][0]["field_anchors"]["label"][2]["json_pointers"] = [""]
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 0, completed.stderr
    assert candidate["candidate_status"] == "processed"
    assert selected_field(candidate, "label")["evidence_anchors"][2]["json_pointers"] == [""]


def test_actual_cli_rejects_boolean_native_box_coordinate(tmp_path: Path) -> None:
    config = invented_config(tmp_path)
    replace_input(
        config, 0, lambda document: document["tables"][0].__setitem__("bbox", [0, 0, True, 50])
    )
    completed, candidate, _ = run_cli(tmp_path, config)
    assert completed.returncode == 2
    assert candidate["candidate_status"] == "input_rejected"
    assert selected_field(candidate)["processing_status"] != "processed"
