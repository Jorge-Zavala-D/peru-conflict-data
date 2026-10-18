"""Strict retained-native evidence I/O, without grouping or scientific admission."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, NoReturn, cast

FRAME = "retained_native_page_words_region_v001"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def pin(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def parse_bytes(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def invalid(_: str) -> NoReturn:
        raise ValueError("nonfinite_json_number")

    return cast(
        "dict[str, Any]",
        json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid),
    )


def read(path: str | Path) -> dict[str, Any]:
    return parse_bytes(Path(path).read_bytes())


def write(path: str | Path, value: dict[str, Any]) -> None:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def box_union(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def load_native(contract: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Hash and parse one buffer, retaining exact word/span/layout identities."""
    require(
        contract["version"] == "M2R05_NATIVE_REGION_ADMISSION_CONTRACT_V001", "unsupported_contract"
    )
    require(contract["coordinate_representation"] == FRAME, "unsupported_coordinate_representation")
    require(contract["rules_version"] == "NATIVE_GEOMETRIC_REGION_RULES_V001", "unsupported_rules")
    spec = contract["input"]
    raw = Path(spec["path"]).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == spec["sha256"], "native_hash_mismatch")
    require(
        isinstance(contract["source"]["pdf_sha256"], str)
        and len(contract["source"]["pdf_sha256"]) == 64,
        "invalid_source_pdf_identity",
    )
    page = parse_bytes(raw)
    require(page["physical_page"] == spec["physical_page"], "unauthorized_physical_page")
    require(
        [page["width"], page["height"]] == spec["dimensions"]
        and all(
            type(value) in (int, float) and math.isfinite(value) and value > 0
            for value in spec["dimensions"]
        ),
        "native_dimension_mismatch",
    )
    require(page["reference_sha256"] == spec["reference_sha256"], "reference_identity_mismatch")
    require(page["representation_status"] == "native_text_present", "unsupported_native_status")
    require(
        isinstance(page["text"], str)
        and isinstance(page["words"], list)
        and isinstance(page["layout_lines"], list),
        "malformed_native_page",
    )
    lookup: dict[str, int] = {}
    evidence: list[dict[str, Any]] = []
    words = cast("list[Any]", page["words"])
    for index, raw_word in enumerate(words):
        require(isinstance(raw_word, dict), "missing_null_or_empty_word")
        word = cast("dict[str, Any]", raw_word)
        require(
            isinstance(word.get("text"), str) and bool(word["text"]),
            "missing_null_or_empty_word",
        )
        require(
            not any(0xD800 <= ord(char) <= 0xDFFF for char in word["text"]), "invalid_unicode_word"
        )
        raw_bbox: object = word.get("bbox")
        raw_span: object = word.get("span")
        require(
            isinstance(raw_bbox, list) and len(cast("list[object]", raw_bbox)) == 4,
            "malformed_native_geometry",
        )
        bbox = cast("list[float]", raw_bbox)
        require(
            all(type(value) in (int, float) and math.isfinite(value) for value in bbox),
            "malformed_native_geometry",
        )
        require(
            0 <= bbox[0] < bbox[2] <= page["width"] and 0 <= bbox[1] < bbox[3] <= page["height"],
            "native_geometry_out_of_bounds",
        )
        require(
            isinstance(raw_span, list) and len(cast("list[object]", raw_span)) == 2,
            "invalid_native_span",
        )
        span = cast("list[int]", raw_span)
        require(
            all(type(value) is int for value in span)
            and 0 <= span[0] < span[1] <= len(page["text"]),
            "invalid_native_span",
        )
        require(page["text"][span[0] : span[1]] == word["text"], "native_span_not_own_text")
        key = json.dumps(word, sort_keys=True, ensure_ascii=False)
        require(key not in lookup, "duplicate_native_word")
        lookup[key] = index
        evidence.append(
            {
                "word_index": index,
                "source_pointer": f"/words/{index}",
                "text": word["text"],
                "span": span,
                "bbox": bbox,
                "layout_pointers": [],
                "native_sha256": spec["sha256"],
                "physical_page": spec["physical_page"],
                "coordinate_representation": FRAME,
            }
        )
    lines = cast("list[Any]", page["layout_lines"])
    for line_index, raw_line in enumerate(lines):
        require(isinstance(raw_line, dict), "invalid_layout_line")
        line = cast("dict[str, Any]", raw_line)
        require(isinstance(line.get("words"), list), "invalid_layout_line")
        for position, word in enumerate(line["words"]):
            key = json.dumps(word, sort_keys=True, ensure_ascii=False)
            require(key in lookup, "unknown_layout_word")
            evidence[lookup[key]]["layout_pointers"].append(
                f"/layout_lines/{line_index}/words/{position}"
            )
    require(
        all(len(item["layout_pointers"]) == 1 for item in evidence),
        "missing_or_duplicate_layout_membership",
    )
    return page, evidence
