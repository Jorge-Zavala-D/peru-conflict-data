"""Configured, source-addressed table extraction with no scientific interpretation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import struct
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]

VERSION = "SOURCE_ADDRESSED_TABLE_ENGINE_V001"
CONTRACT_VERSION = "SOURCE_ADDRESSED_TABLE_CONFIG_V001"
FAILURES = (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError)


class InputRejected(ValueError):
    """Configured evidence does not qualify the affected extraction component."""


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise InputRejected(detail)


def object_value(value: JsonValue, detail: str = "expected_object") -> JsonObject:
    require(isinstance(value, dict), detail)
    return cast(JsonObject, value)


def array_value(value: JsonValue, detail: str = "expected_array") -> list[JsonValue]:
    require(isinstance(value, list), detail)
    return cast(list[JsonValue], value)


def objects(value: JsonValue) -> list[JsonObject]:
    return [object_value(item) for item in array_value(value)]


def string(value: JsonValue, detail: str = "expected_nonempty_string") -> str:
    require(isinstance(value, str) and bool(value), detail)
    return cast(str, value)


def integer(value: JsonValue, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum, "invalid_integer")
    return cast(int, value)


def key_string(value: JsonObject, key: str) -> str:
    return string(value.get(key), "invalid_" + key)


def key_integer(value: JsonObject, key: str, minimum: int = 0) -> int:
    return integer(value.get(key), minimum)


def optional_objects(value: JsonObject, key: str) -> list[JsonObject]:
    return objects(value.get(key, []))


def keys(value: JsonObject, allowed: set[str], required: set[str]) -> None:
    require(required <= value.keys() <= allowed, "unexpected_or_missing_configuration_key")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def source_json(data: bytes) -> tuple[JsonValue, dict[str, str]]:
    """Strictly parse UTF-8 JSON while retaining original value tokens by pointer."""
    text = data.decode("utf-8")
    tokens: dict[str, str] = {}

    def invalid_constant(value: str) -> None:
        raise InputRejected("nonfinite_json_number:" + value)

    decoder = json.JSONDecoder(parse_constant=invalid_constant)

    def skip(index: int) -> int:
        while index < len(text) and text[index] in " \r\n\t":
            index += 1
        return index

    def read(index: int, pointer: str) -> tuple[JsonValue, int]:
        index = skip(index)
        require(index < len(text), "truncated_json")
        start = index
        if text[index] == "{":
            result: JsonObject = {}
            index = skip(index + 1)
            if index < len(text) and text[index] == "}":
                tokens[pointer] = text[start : index + 1]
                return result, index + 1
            while True:
                raw_key, index = decoder.raw_decode(text, index)
                key = cast(JsonValue, raw_key)
                require(isinstance(key, str), "nonstring_json_object_key")
                key = cast(str, key)
                require(
                    not any(0xD800 <= ord(char) <= 0xDFFF for char in key),
                    "unpaired_unicode_surrogate",
                )
                require(key not in result, "duplicate_json_object_key")
                index = skip(index)
                require(index < len(text) and text[index] == ":", "missing_json_colon")
                child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                result[key], index = read(index + 1, child)
                index = skip(index)
                require(index < len(text), "truncated_json_object")
                if text[index] == "}":
                    tokens[pointer] = text[start : index + 1]
                    return result, index + 1
                require(text[index] == ",", "missing_json_object_comma")
                index = skip(index + 1)
        if text[index] == "[":
            values: list[JsonValue] = []
            index = skip(index + 1)
            if index < len(text) and text[index] == "]":
                tokens[pointer] = text[start : index + 1]
                return values, index + 1
            while True:
                child, index = read(index, pointer + "/" + str(len(values)))
                values.append(child)
                index = skip(index)
                require(index < len(text), "truncated_json_array")
                if text[index] == "]":
                    tokens[pointer] = text[start : index + 1]
                    return values, index + 1
                require(text[index] == ",", "missing_json_array_comma")
                index = skip(index + 1)
        raw_value, end = decoder.raw_decode(text, index)
        value = cast(JsonValue, raw_value)
        require(not isinstance(value, (dict, list)), "unindexed_json_container")
        require(not isinstance(value, float) or math.isfinite(value), "nonfinite_json_number")
        require(
            not isinstance(value, str) or not any(0xD800 <= ord(char) <= 0xDFFF for char in value),
            "unpaired_unicode_surrogate",
        )
        tokens[pointer] = text[start:end]
        return value, end

    value, end = read(0, "")
    require(skip(end) == len(text), "trailing_json_content")
    return value, tokens


def strict_equal(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        other = cast(JsonObject, right)
        return left.keys() == other.keys() and all(
            strict_equal(value, other[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        other_list = cast(list[JsonValue], right)
        return len(left) == len(other_list) and all(
            strict_equal(a, b) for a, b in zip(left, other_list, strict=True)
        )
    return left == right


def pointer_value(value: JsonValue, pointer: str) -> JsonValue:
    require(
        pointer == "" or (pointer.startswith("/") and re.search(r"~(?![01])", pointer) is None),
        "invalid_json_pointer",
    )
    if not pointer:
        return value
    for encoded in pointer[1:].split("/"):
        part = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            require(part in value, "unresolved_json_pointer")
            value = value[part]
        elif isinstance(value, list):
            require(
                part.isascii()
                and part.isdecimal()
                and str(int(part)) == part
                and int(part) < len(value),
                "unresolved_json_pointer",
            )
            value = value[int(part)]
        else:
            raise InputRejected("unresolved_json_pointer")
    return value


def validate_assertions(
    spec: JsonObject, value: JsonValue | None = None, *, resolve: bool = False
) -> None:
    seen: set[str] = set()
    for assertion in optional_objects(spec, "assertions"):
        keys(assertion, {"pointer", "value"}, {"pointer", "value"})
        pointer = assertion.get("pointer")
        require(
            isinstance(pointer, str) and pointer not in seen,
            "duplicate_or_invalid_assertion_pointer",
        )
        pointer = cast(str, pointer)
        seen.add(pointer)
        if resolve:
            require(
                strict_equal(pointer_value(value, pointer), assertion["value"]),
                "artifact_assertion_mismatch",
            )


def validate_pin(spec: JsonObject) -> None:
    require(Path(key_string(spec, "path")).is_absolute(), "pinned_path_must_be_absolute")
    digest = key_string(spec, "sha256")
    require(
        len(digest) == 64 and all(char in "0123456789abcdef" for char in digest), "invalid_sha256"
    )
    key_integer(spec, "size_bytes")


def rectangle(
    value: JsonValue, width: int | None = None, height: int | None = None
) -> list[JsonValue]:
    coordinates = array_value(value)
    require(
        len(coordinates) == 4
        and all(
            type(number) is int or (type(number) is float and math.isfinite(number))
            for number in coordinates
        ),
        "invalid_bbox",
    )
    x0, y0, x1, y1 = [cast(int | float, number) for number in coordinates]
    require(x0 < x1 and y0 < y1, "invalid_bbox_order")
    if width is not None and height is not None:
        require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, "bbox_outside_frame")
    return coordinates


def validate_config(value: JsonValue) -> JsonObject:
    config = object_value(value)
    keys(
        config,
        {"contract_version", "profile_id", "source", "inputs", "artifacts", "frames", "layouts"},
        {"contract_version", "profile_id", "source", "inputs", "layouts"},
    )
    require(config.get("contract_version") == CONTRACT_VERSION, "unsupported_config_version")
    key_string(config, "profile_id")
    source = object_value(config.get("source"))
    keys(source, {"pdf_sha256", "report_number"}, {"pdf_sha256", "report_number"})
    require(
        re.fullmatch("[0-9a-f]{64}", key_string(source, "pdf_sha256")) is not None,
        "invalid_pdf_sha256",
    )
    key_integer(source, "report_number", 1)
    inputs: dict[str, JsonObject] = {}
    paths: set[str] = set()
    for item in objects(config.get("inputs")):
        keys(
            item,
            {
                "input_id",
                "physical_page",
                "path",
                "sha256",
                "size_bytes",
                "expected_table_count",
                "expected_status",
            },
            {"input_id", "physical_page", "path", "sha256", "size_bytes", "expected_table_count"},
        )
        name = key_string(item, "input_id")
        require(
            name not in inputs and key_string(item, "path") not in paths, "duplicate_input_identity"
        )
        validate_pin(item)
        key_integer(item, "physical_page", 1)
        key_integer(item, "expected_table_count")
        if "expected_status" in item:
            key_string(item, "expected_status")
        inputs[name] = item
        paths.add(key_string(item, "path"))
    require(bool(inputs), "missing_inputs")
    artifacts: dict[str, JsonObject] = {}
    for item in optional_objects(config, "artifacts"):
        keys(
            item,
            {"artifact_id", "kind", "path", "sha256", "size_bytes", "assertions"},
            {"artifact_id", "kind", "path", "sha256", "size_bytes"},
        )
        name = key_string(item, "artifact_id")
        require(
            name not in artifacts and key_string(item, "path") not in paths,
            "duplicate_artifact_identity",
        )
        require(item.get("kind") in ("image", "json"), "unsupported_artifact_kind")
        validate_pin(item)
        validate_assertions(item)
        require(
            item["kind"] == "json" or not item.get("assertions", []),
            "image_json_assertions_unsupported",
        )
        artifacts[name] = item
        paths.add(key_string(item, "path"))
    frames: dict[str, JsonObject] = {}
    for frame in optional_objects(config, "frames"):
        keys(
            frame,
            {
                "frame_id",
                "image_artifact_id",
                "physical_page",
                "width",
                "height",
                "coordinate_system",
                "origin",
                "units",
                "x_direction",
                "y_direction",
            },
            {
                "frame_id",
                "image_artifact_id",
                "physical_page",
                "width",
                "height",
                "coordinate_system",
                "origin",
                "units",
                "x_direction",
                "y_direction",
            },
        )
        name = key_string(frame, "frame_id")
        image = key_string(frame, "image_artifact_id")
        require(
            name not in frames and image in artifacts and artifacts[image]["kind"] == "image",
            "invalid_frame_identity",
        )
        for key in ("physical_page", "width", "height"):
            key_integer(frame, key, 1)
        require(
            all(
                frame.get(key) == expected
                for key, expected in {
                    "coordinate_system": "image_top_left_pixels_v1",
                    "origin": "top_left",
                    "units": "pixels",
                    "x_direction": "right",
                    "y_direction": "down",
                }.items()
            ),
            "unsupported_frame_convention",
        )
        frames[name] = frame
    anchor_ids: set[str] = set()

    def anchors(spec: JsonValue, page: int) -> None:
        for anchor in objects(spec):
            keys(
                anchor,
                {
                    "anchor_id",
                    "artifact_id",
                    "kind",
                    "frame_id",
                    "bbox",
                    "json_pointers",
                    "assertions",
                    "metadata",
                },
                {"anchor_id", "artifact_id", "kind"},
            )
            name = key_string(anchor, "anchor_id")
            artifact = key_string(anchor, "artifact_id")
            require(
                name not in anchor_ids and artifact in artifacts,
                "duplicate_or_invalid_anchor_identity",
            )
            anchor_ids.add(name)
            kind = anchor.get("kind")
            require(kind in ("image_box", "json_pointer"), "unsupported_anchor_kind")
            object_value(anchor.get("metadata", {}))
            validate_assertions(anchor)
            pointers = array_value(anchor.get("json_pointers", []))
            require(
                all(isinstance(pointer, str) for pointer in pointers)
                and len({cast(str, pointer) for pointer in pointers}) == len(pointers),
                "duplicate_or_invalid_anchor_pointer",
            )
            if "frame_id" in anchor:
                frame_id = key_string(anchor, "frame_id")
                require(
                    frame_id in frames and frames[frame_id]["physical_page"] == page,
                    "anchor_frame_page_mismatch",
                )
            if kind == "image_box":
                require(
                    artifacts[artifact]["kind"] == "image" and "frame_id" in anchor,
                    "image_anchor_requires_frame",
                )
                frame = frames[key_string(anchor, "frame_id")]
                require(
                    frame["image_artifact_id"] == artifact
                    and not pointers
                    and not anchor.get("assertions", []),
                    "image_anchor_frame_identity_mismatch",
                )
                rectangle(
                    anchor.get("bbox"), key_integer(frame, "width"), key_integer(frame, "height")
                )
            else:
                require(
                    artifacts[artifact]["kind"] == "json"
                    and bool(pointers)
                    and "bbox" not in anchor,
                    "invalid_json_pointer_anchor",
                )

    layout_ids: set[str] = set()
    row_ids: set[str] = set()
    addresses: set[tuple[str, int, int]] = set()
    fragment_ids: set[str] = set()
    layouts = objects(config.get("layouts"))
    require(bool(layouts), "missing_layouts")
    for layout in layouts:
        keys(
            layout,
            {
                "layout_id",
                "input_id",
                "table_index",
                "array_length",
                "expected_table_rows",
                "header_rows",
                "header_mask",
                "columns",
                "rows",
                "role",
                "ordinal_column",
                "fragments",
            },
            {
                "layout_id",
                "input_id",
                "table_index",
                "array_length",
                "expected_table_rows",
                "header_rows",
                "header_mask",
                "columns",
                "rows",
                "role",
            },
        )
        layout_id, input_id = key_string(layout, "layout_id"), key_string(layout, "input_id")
        require(
            layout_id not in layout_ids and input_id in inputs,
            "duplicate_or_invalid_layout_identity",
        )
        layout_ids.add(layout_id)
        require(
            layout.get("role") in ("primary", "context", "published_aggregate"),
            "unsupported_layout_role",
        )
        table_index, width, length = (
            key_integer(layout, "table_index"),
            key_integer(layout, "array_length", 1),
            key_integer(layout, "expected_table_rows", 1),
        )
        require(
            table_index < key_integer(inputs[input_id], "expected_table_count"),
            "configured_table_index_out_of_range",
        )
        header_rows = [integer(row) for row in array_value(layout.get("header_rows"))]
        require(
            bool(header_rows)
            and len(set(header_rows)) == len(header_rows)
            and all(row < length for row in header_rows),
            "invalid_header_rows",
        )
        mask: dict[tuple[int, int], JsonObject] = {}
        for entry in objects(layout.get("header_mask")):
            keys(entry, {"row", "column", "type", "value"}, {"row", "column", "type", "value"})
            row, column = key_integer(entry, "row"), key_integer(entry, "column")
            require(
                row in header_rows and column < width and (row, column) not in mask,
                "duplicate_or_out_of_range_header_mask",
            )
            kind, item = entry.get("type"), entry["value"]
            require(
                (kind == "named_string" and type(item) is str and item != "")
                or (kind == "empty_string" and type(item) is str and item == "")
                or (kind == "null" and item is None),
                "invalid_header_mask_type_or_value",
            )
            mask[row, column] = entry
        require(
            set(mask) == {(row, column) for row in header_rows for column in range(width)},
            "incomplete_header_mask",
        )
        field_ids: set[str] = set()
        columns: set[int] = set()
        for column in objects(layout.get("columns")):
            keys(
                column,
                {"field_id", "column_index", "label", "header_fragments", "header_joiner"},
                {"field_id", "column_index", "label", "header_fragments"},
            )
            name, index = key_string(column, "field_id"), key_integer(column, "column_index")
            require(
                name not in field_ids and index not in columns and index < width,
                "duplicate_or_invalid_column",
            )
            field_ids.add(name)
            columns.add(index)
            parts: list[str] = []
            fragment_addresses: set[tuple[int, int]] = set()
            for fragment in objects(column.get("header_fragments")):
                keys(fragment, {"row", "column"}, {"row", "column"})
                address = (key_integer(fragment, "row"), key_integer(fragment, "column"))
                require(
                    address in mask
                    and address not in fragment_addresses
                    and mask[address]["type"] == "named_string",
                    "invalid_header_fragment_address",
                )
                fragment_addresses.add(address)
                parts.append(key_string(mask[address], "value"))
            joiner = column.get("header_joiner", " ")
            require(
                isinstance(joiner, str)
                and bool(parts)
                and joiner.join(parts) == key_string(column, "label"),
                "header_reconstruction_label_mismatch",
            )
        require(bool(field_ids), "missing_columns")
        ordinal = layout.get("ordinal_column")
        if ordinal is not None:
            require(integer(ordinal) < width and ordinal not in columns, "invalid_ordinal_column")
        selected_rows: set[int] = set()
        for row in objects(layout.get("rows")):
            keys(
                row,
                {"row_id", "array_row_index", "sequence", "expected_ordinal", "field_anchors"},
                {"row_id", "array_row_index"},
            )
            row_id, index = key_string(row, "row_id"), key_integer(row, "array_row_index")
            require(
                row_id not in row_ids
                and index < length
                and index not in header_rows
                and index not in selected_rows,
                "duplicate_or_invalid_row",
            )
            row_ids.add(row_id)
            selected_rows.add(index)
            address = (input_id, table_index, index)
            require(address not in addresses, "row_selected_by_multiple_layouts")
            addresses.add(address)
            if "sequence" in row:
                key_integer(row, "sequence", 1)
            require(
                (ordinal is None and "expected_ordinal" not in row)
                or (ordinal is not None and type(row.get("expected_ordinal")) in (int, str)),
                "missing_or_invalid_expected_ordinal",
            )
            field_anchors = object_value(row.get("field_anchors", {}))
            require(field_anchors.keys() <= field_ids, "anchor_targets_unknown_field")
            for value in field_anchors.values():
                anchors(value, key_integer(inputs[input_id], "physical_page"))
        fragment_rows: set[int] = set()
        for fragment in optional_objects(layout, "fragments"):
            keys(
                fragment,
                {"fragment_id", "array_row_index", "column_index", "anchors"},
                {"fragment_id", "array_row_index", "column_index"},
            )
            name, row, column = (
                key_string(fragment, "fragment_id"),
                key_integer(fragment, "array_row_index"),
                key_integer(fragment, "column_index"),
            )
            require(
                name not in fragment_ids
                and row < length
                and column < width
                and row not in header_rows
                and row not in selected_rows
                and row not in fragment_rows,
                "duplicate_or_invalid_fragment",
            )
            fragment_ids.add(name)
            fragment_rows.add(row)
            address = (input_id, table_index, row)
            require(address not in addresses, "fragment_row_selected_multiple_times")
            addresses.add(address)
            anchors(fragment.get("anchors", []), key_integer(inputs[input_id], "physical_page"))
        require(
            set(header_rows) | selected_rows | fragment_rows == set(range(length)),
            "unplanned_table_row",
        )
    return config


def planned_field(
    layout: JsonObject, row: JsonValue, column: JsonValue, anchors: JsonValue
) -> JsonObject:
    return {
        "processing_status": "unprocessed",
        "state": None,
        "original_value": None,
        "type": None,
        "source_lexical_json_token": None,
        "typed_value_json": None,
        "typed_value_json_role": "encoded_derivative_of_decoded_source_value",
        "input_json_pointer": f"/tables/{layout.get('table_index')}/cells/{row}/{column}",
        "input_cell_present": None,
        "column_index": column,
        "source_identity": None,
        "header_reconstruction": None,
        "evidence_anchors": anchors,
        "image_cell_box": None,
    }


def plan(config: JsonObject) -> tuple[dict[str, list[JsonObject]], dict[str, list[JsonObject]]]:
    layers: dict[str, list[JsonObject]] = {
        "documentary_rows": [],
        "published_measurements": [],
        "continuation_fragments": [],
    }
    by_layout: dict[str, list[JsonObject]] = {}
    raw_inputs = config.get("inputs", [])
    pages: dict[str, JsonValue] = {}
    if isinstance(raw_inputs, list):
        pages = {
            str(item.get("input_id")): item.get("physical_page")
            for item in raw_inputs
            if isinstance(item, dict)
        }
    raw_layouts = config.get("layouts", [])
    if not isinstance(raw_layouts, list):
        return layers, by_layout
    for layout in raw_layouts:
        if not isinstance(layout, dict):
            continue
        name = str(layout.get("layout_id"))
        common: JsonObject = {
            "layout_id": layout.get("layout_id"),
            "input_id": layout.get("input_id"),
            "source_page": pages.get(str(layout.get("input_id"))),
            "source_role": layout.get("role"),
            "table_index": layout.get("table_index"),
            "processing_status": "unprocessed",
            "native_table_bbox": None,
        }
        rows: list[JsonObject] = []
        raw_rows, raw_columns = layout.get("rows", []), layout.get("columns", [])
        if isinstance(raw_rows, list) and isinstance(raw_columns, list):
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                fields: JsonObject = {}
                anchors = row.get("field_anchors", {})
                for column in raw_columns:
                    if isinstance(column, dict) and isinstance(column.get("field_id"), str):
                        field_id = cast(str, column["field_id"])
                        evidence: JsonValue = []
                        if isinstance(anchors, dict) and field_id in anchors:
                            evidence = anchors[field_id]
                        fields[field_id] = planned_field(
                            layout, row.get("array_row_index"), column.get("column_index"), evidence
                        )
                item: JsonObject = {
                    **common,
                    "row_id": row.get("row_id"),
                    "sequence": row.get("sequence"),
                    "array_row_index": row.get("array_row_index"),
                    "documentary_ordinal": None,
                    "ordinal_outcome": None,
                    "fields": fields,
                }
                rows.append(item)
                layers[
                    "published_measurements"
                    if layout.get("role") == "published_aggregate"
                    else "documentary_rows"
                ].append(item)
        by_layout[name] = rows
        raw_fragments = layout.get("fragments", [])
        if isinstance(raw_fragments, list):
            for fragment in raw_fragments:
                if isinstance(fragment, dict):
                    layers["continuation_fragments"].append(
                        {
                            **common,
                            "fragment_id": fragment.get("fragment_id"),
                            "array_row_index": fragment.get("array_row_index"),
                            "column_index": fragment.get("column_index"),
                            "context_only": True,
                            "creates_observation": False,
                            "field": planned_field(
                                layout,
                                fragment.get("array_row_index"),
                                fragment.get("column_index"),
                                fragment.get("anchors", []),
                            ),
                            "unselected_context_cells": [],
                        }
                    )
    return layers, by_layout


def pinned_bytes(spec: JsonObject, identity: JsonObject) -> bytes:
    raw = Path(key_string(spec, "path")).read_bytes()
    identity.update(sha256=sha256(raw), size_bytes=len(raw))
    require(identity["sha256"] == spec["sha256"], "input_sha256_mismatch")
    require(identity["size_bytes"] == spec["size_bytes"], "input_size_mismatch")
    return raw


def identity_for(spec: JsonObject, name: str) -> JsonObject:
    return {
        name: spec[name],
        "path": spec["path"],
        "expected_sha256": spec["sha256"],
        "expected_size_bytes": spec["size_bytes"],
        "sha256": None,
        "size_bytes": None,
        "processing_status": "input_rejected",
    }


def cell_outcome(
    row: list[JsonValue], column: int, pointer: str, tokens: dict[str, str]
) -> JsonObject:
    present = column < len(row)
    value = row[column] if present else None
    kind = (
        "missing"
        if not present
        else "null"
        if value is None
        else "string"
        if isinstance(value, str)
        else "boolean"
        if isinstance(value, bool)
        else "number"
        if isinstance(value, (int, float))
        else "array"
        if isinstance(value, list)
        else "object"
    )
    status = (
        "unavailable_missing_cell"
        if not present
        else "unavailable_null_cell"
        if value is None
        else "processed"
        if isinstance(value, str)
        else "invalid_cell_type"
    )
    return {
        "processing_status": status,
        "state": "observed" if isinstance(value, str) else None,
        "original_value": value,
        "type": kind,
        "source_lexical_json_token": tokens.get(pointer) if present else None,
        "typed_value_json": json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        if present
        else None,
        "input_json_pointer": pointer,
        "input_cell_present": present,
        "column_index": column,
    }


def validate_source(value: JsonValue, spec: JsonObject, source: JsonObject) -> JsonObject:
    table = object_value(value)
    require(
        table.get("source_sha256") == source["pdf_sha256"]
        and strict_equal(table.get("physical_page"), spec["physical_page"]),
        "source_identity_mismatch",
    )
    if "report_number" in table:
        require(
            strict_equal(table["report_number"], source["report_number"]),
            "source_report_number_mismatch",
        )
    key_string(table, "status")
    key_string(table, "authority")
    require(
        table.get("empty_table_result_certifies_absence") is False, "invalid_source_absence_claim"
    )
    if "expected_status" in spec:
        require(table["status"] == spec["expected_status"], "source_status_mismatch")
    require(
        len(array_value(table.get("tables"))) == spec["expected_table_count"],
        "source_table_count_mismatch",
    )
    return table


def validate_table(layout: JsonObject, source: JsonObject, report_number: JsonValue) -> JsonObject:
    table = object_value(array_value(source["tables"])[key_integer(layout, "table_index")])
    if "report_number" in table:
        require(strict_equal(table["report_number"], report_number), "table_report_number_mismatch")
    rectangle(table.get("bbox"))
    cells = array_value(table.get("cells"))
    width = key_integer(layout, "array_length")
    require(
        len(cells) == layout["expected_table_rows"]
        and all(isinstance(row, list) and len(row) <= width for row in cells),
        "table_shape_mismatch",
    )
    mask = {
        (key_integer(item, "row"), key_integer(item, "column")): item["value"]
        for item in objects(layout["header_mask"])
    }
    for row in array_value(layout["header_rows"]):
        index = integer(row)
        values = array_value(cells[index])
        require(len(values) == width, "header_array_length_mismatch")
        require(
            all(strict_equal(value, mask[index, column]) for column, value in enumerate(values)),
            "header_cells_mismatch",
        )
    selected = {key_integer(column, "column_index") for column in objects(layout["columns"])}
    ordinal = layout.get("ordinal_column")
    for row in objects(layout["rows"]):
        values = array_value(cells[key_integer(row, "array_row_index")])
        require(
            all(
                value is None
                for column, value in enumerate(values)
                if column not in selected and column != ordinal
            ),
            "unselected_data_column_nonnull",
        )
        if ordinal is not None:
            index = integer(ordinal)
            require(
                index < len(values) and strict_equal(values[index], row["expected_ordinal"]),
                "source_ordinal_mismatch",
            )
    return table


def anchors_available(anchors: JsonValue, artifacts: dict[str, JsonValue]) -> None:
    for anchor in objects(anchors):
        artifact_id = key_string(anchor, "artifact_id")
        require(artifact_id in artifacts, "anchor_artifact_rejected")
        if anchor["kind"] == "json_pointer":
            for pointer in array_value(anchor.get("json_pointers", [])):
                pointer_value(artifacts[artifact_id], cast(str, pointer))
            validate_assertions(anchor, artifacts[artifact_id], resolve=True)


def fill_field(
    field: JsonObject, cells: list[JsonValue], tokens: dict[str, str], identity: JsonObject
) -> None:
    field.update(
        cell_outcome(
            cells,
            key_integer(field, "column_index"),
            key_string(field, "input_json_pointer"),
            tokens,
        )
    )
    field["source_identity"] = identity
    for anchor in objects(field.get("evidence_anchors", [])):
        if anchor["kind"] == "image_box":
            field["image_cell_box"] = anchor["bbox"]
            break


def extract_layout(
    layout: JsonObject,
    table: JsonObject,
    tokens: dict[str, str],
    rows: list[JsonObject],
    fragments: list[JsonObject],
    identity: JsonObject,
    artifacts: dict[str, JsonValue],
) -> None:
    cells = array_value(table["cells"])
    for row in rows:
        for field in object_value(row["fields"]).values():
            anchors_available(object_value(field).get("evidence_anchors", []), artifacts)
    for fragment in fragments:
        anchors_available(object_value(fragment["field"]).get("evidence_anchors", []), artifacts)
    headers: dict[str, JsonObject] = {}
    for column in objects(layout["columns"]):
        parts: list[JsonValue] = []
        for address in objects(column["header_fragments"]):
            row, index = key_integer(address, "row"), key_integer(address, "column")
            pointer = f"/tables/{layout['table_index']}/cells/{row}/{index}"
            parts.append(
                {
                    "input_json_pointer": pointer,
                    "original_value": array_value(cells[row])[index],
                    "source_lexical_json_token": tokens[pointer],
                }
            )
        joiner = cast(str, column.get("header_joiner", " "))
        headers[key_string(column, "field_id")] = {
            "text": joiner.join(key_string(object_value(part), "original_value") for part in parts),
            "basis": "explicit_config_fragment_order",
            "fragments": parts,
        }
    plans = {key_string(row, "row_id"): row for row in objects(layout["rows"])}
    for row in rows:
        row["native_table_bbox"] = table["bbox"]
        values = array_value(cells[key_integer(row, "array_row_index")])
        for name, value in object_value(row["fields"]).items():
            field = object_value(value)
            fill_field(field, values, tokens, identity)
            field["header_reconstruction"] = headers[name]
        if layout.get("ordinal_column") is not None:
            ordinal = integer(layout["ordinal_column"])
            pointer = f"/tables/{layout['table_index']}/cells/{row['array_row_index']}/{ordinal}"
            outcome = cell_outcome(values, ordinal, pointer, tokens)
            row["documentary_ordinal"] = values[ordinal]
            row["ordinal_outcome"] = {
                key: outcome[key]
                for key in (
                    "original_value",
                    "type",
                    "typed_value_json",
                    "source_lexical_json_token",
                    "input_json_pointer",
                )
            }
            require(
                strict_equal(values[ordinal], plans[key_string(row, "row_id")]["expected_ordinal"]),
                "source_ordinal_mismatch",
            )
        row["processing_status"] = (
            "processed"
            if all(
                object_value(field)["processing_status"] == "processed"
                for field in object_value(row["fields"]).values()
            )
            else "partial"
        )
    for fragment in fragments:
        fragment["native_table_bbox"] = table["bbox"]
        row = key_integer(fragment, "array_row_index")
        values = array_value(cells[row])
        field = object_value(fragment["field"])
        fill_field(field, values, tokens, identity)
        fragment["processing_status"] = field["processing_status"]
        fragment["unselected_context_cells"] = [
            cell_outcome(
                values, column, f"/tables/{layout['table_index']}/cells/{row}/{column}", tokens
            )
            for column in range(key_integer(layout, "array_length"))
            if column != fragment["column_index"]
        ]


def atomic_exclusive_json(path: Path, payload: JsonObject) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def run(config_path: Path, output: Path) -> int:
    if not output.is_absolute():
        print("output_must_be_absolute", file=sys.stderr)
        return 64
    if output.exists() or output.is_symlink():
        print("output_already_exists", file=sys.stderr)
        return 73
    started = timestamp()
    receipt: JsonObject = {
        "version": VERSION,
        "config_version": CONTRACT_VERSION,
        "profile_id": None,
        "candidate_status": "input_rejected",
        "config_sha256": None,
        "input_identities": [],
        "artifact_identities": [],
        "documentary_rows": [],
        "published_measurements": [],
        "continuation_fragments": [],
        "components": [],
        "errors": [],
        "frames": [],
        "pdf_to_image_transform": None,
        "native_coordinate_claim": "serialized_native_coordinates_only_unqualified",
    }

    def error(scope: str, exc: Exception, **address: JsonValue) -> None:
        detail = "invalid_utf8_or_unicode" if isinstance(exc, UnicodeError) else str(exc)
        array_value(receipt["errors"]).append(
            {"scope": scope, **address, "error_type": type(exc).__name__, "detail": detail}
        )

    plans: dict[str, list[JsonObject]] = {}
    try:
        raw_config = config_path.read_bytes()
        receipt["config_sha256"] = sha256(raw_config)
        config_value, _ = source_json(raw_config)
        if isinstance(config_value, dict):
            layers, plans = plan(config_value)
            receipt.update({key: cast(JsonValue, value) for key, value in layers.items()})
            receipt["profile_id"] = config_value.get("profile_id")
        config = validate_config(config_value)
        receipt["frames"] = config.get("frames", [])
        source_identity = object_value(config["source"])
        sources: dict[str, tuple[JsonObject, dict[str, str], JsonObject]] = {}
        for spec in objects(config["inputs"]):
            identity = identity_for(spec, "input_id")
            identity["physical_page"] = spec["physical_page"]
            array_value(receipt["input_identities"]).append(identity)
            try:
                raw = pinned_bytes(spec, identity)
                value, tokens = source_json(raw)
                source = validate_source(value, spec, source_identity)
                identity["processing_status"] = "verified"
                sources[key_string(spec, "input_id")] = (source, tokens, identity)
            except FAILURES as exc:
                error("input", exc, input_id=spec["input_id"], page=spec["physical_page"])
        artifacts: dict[str, JsonValue] = {}
        for spec in optional_objects(config, "artifacts"):
            identity = identity_for(spec, "artifact_id")
            array_value(receipt["artifact_identities"]).append(identity)
            try:
                raw = pinned_bytes(spec, identity)
                value: JsonValue = None
                if spec["kind"] == "json":
                    value, _ = source_json(raw)
                    validate_assertions(spec, value, resolve=True)
                else:
                    require(
                        len(raw) >= 24
                        and raw[:8] == b"\x89PNG\r\n\x1a\n"
                        and raw[12:16] == b"IHDR",
                        "invalid_png_header",
                    )
                    width, height = struct.unpack(">II", raw[16:24])
                    for frame in optional_objects(config, "frames"):
                        if frame["image_artifact_id"] == spec["artifact_id"]:
                            require(
                                width == frame["width"] and height == frame["height"],
                                "image_frame_dimensions_mismatch",
                            )
                identity["processing_status"] = "verified"
                artifacts[key_string(spec, "artifact_id")] = value
            except FAILURES as exc:
                error("artifact", exc, artifact_id=spec["artifact_id"])
        for layout in objects(config["layouts"]):
            name = key_string(layout, "layout_id")
            component: JsonObject = {
                "layout_id": name,
                "input_id": layout["input_id"],
                "processing_status": "unprocessed",
            }
            array_value(receipt["components"]).append(component)
            if key_string(layout, "input_id") not in sources:
                component["reason"] = "input_rejected"
                continue
            source, tokens, input_identity = sources[key_string(layout, "input_id")]
            try:
                table = validate_table(layout, source, source_identity["report_number"])
                identity: JsonObject = {
                    **source_identity,
                    "page": input_identity["physical_page"],
                    "input_id": layout["input_id"],
                    "input_sha256": input_identity["sha256"],
                    "input_size_bytes": input_identity["size_bytes"],
                }
                fragments = [
                    object_value(fragment)
                    for fragment in array_value(receipt["continuation_fragments"])
                    if object_value(fragment)["layout_id"] == name
                ]
                extract_layout(layout, table, tokens, plans[name], fragments, identity, artifacts)
                component.update(
                    processing_status="processed",
                    native_table_bbox=table["bbox"],
                    source_processing_metadata={
                        key: source[key]
                        for key in ("status", "authority", "empty_table_result_certifies_absence")
                    },
                )
            except FAILURES as exc:
                error(
                    "layout",
                    exc,
                    layout_id=name,
                    input_id=layout["input_id"],
                    page=input_identity["physical_page"],
                )
    except FAILURES as exc:
        error("config", exc)
    rows = [
        object_value(row)
        for layer in ("documentary_rows", "published_measurements")
        for row in array_value(receipt[layer])
    ]
    fields = [object_value(field) for row in rows for field in object_value(row["fields"]).values()]
    fragments = [
        object_value(fragment) for fragment in array_value(receipt["continuation_fragments"])
    ]
    fields.extend(object_value(fragment["field"]) for fragment in fragments)
    statuses = Counter(key_string(field, "processing_status") for field in fields)
    if fields and statuses["processed"] == len(fields) and not receipt["errors"]:
        receipt["candidate_status"] = "processed"
    elif statuses["processed"]:
        receipt["candidate_status"] = "partial"
    receipt["counts"] = {
        "documentary_rows": len(array_value(receipt["documentary_rows"])),
        "documentary_fields": sum(
            len(object_value(object_value(row)["fields"]))
            for row in array_value(receipt["documentary_rows"])
        ),
        "published_measurements": len(array_value(receipt["published_measurements"])),
        "published_measurement_fields": sum(
            len(object_value(object_value(row)["fields"]))
            for row in array_value(receipt["published_measurements"])
        ),
        "continuation_fragments": len(fragments),
        "fragment_fields": len(fragments),
        "field_processing_statuses": {key: count for key, count in sorted(statuses.items())},
    }
    receipt["runtime"] = {
        "version": VERSION,
        "code_sha256": sha256(Path(__file__).read_bytes()),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "executable": sys.executable,
        "started_at_utc": started,
        "finished_at_utc": timestamp(),
    }
    try:
        atomic_exclusive_json(output, receipt)
    except UnicodeError:
        print("exclusive_output_write_failed:unicode_encoding_error", file=sys.stderr)
        return 73
    except OSError as exc:
        print("exclusive_output_write_failed:" + str(exc), file=sys.stderr)
        return 73
    print(
        json.dumps(
            {"candidate_status": receipt["candidate_status"], "output": str(output)},
            ensure_ascii=False,
        )
    )
    return 0 if receipt["candidate_status"] == "processed" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    return run(Path(args.config), Path(args.output))
