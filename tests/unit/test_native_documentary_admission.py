"""Invented pages only; geometry admission is not scientific validation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


def _page(entries: list[tuple[str, list[float]]]) -> dict[str, Any]:
    text = ""
    words: list[dict[str, Any]] = []
    for value, bbox in entries:
        start = len(text)
        text += value
        words.append({"text": value, "span": [start, len(text)], "bbox": bbox})
        text += " "
    return {
        "physical_page": 7,
        "width": 600,
        "height": 900,
        "reference_sha256": "b" * 64,
        "representation_status": "native_text_present",
        "text": text,
        "words": words,
        "layout_lines": [{"words": [copy.deepcopy(word)]} for word in words],
    }


def _table(y: int = 60, rows: int = 4) -> list[tuple[str, list[float]]]:
    return [
        (f"陌生{row}{column}", [x, y + 16 * row, x + 28, y + 16 * row + 8])
        for row in range(rows)
        for column, x in enumerate((50, 220, 430))
    ]


def _prose(
    y: int = 300, lines: int = 4, x: int = 45, width: int = 500
) -> list[tuple[str, list[float]]]:
    return [
        (
            f"Δ{row}_{column}",
            [
                x + column * width / 8,
                y + 11 * row,
                x + column * width / 8 + width / 10,
                y + 11 * row + 8,
            ],
        )
        for row in range(lines)
        for column in range(8)
    ]


def _contract(tmp_path: Path, page: dict[str, Any]) -> dict[str, Any]:
    from peru_conflicts.execution.native_documentary.io import FRAME

    source = tmp_path / "invented-native.json"
    raw = json.dumps(page, ensure_ascii=False).encode()
    source.write_bytes(raw)
    return {
        "version": "M2R05_NATIVE_REGION_ADMISSION_CONTRACT_V001",
        "source": {"report_number": 999, "pdf_sha256": "a" * 64},
        "input": {
            "path": str(source),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "physical_page": 7,
            "dimensions": [600, 900],
            "reference_sha256": "b" * 64,
        },
        "coordinate_representation": FRAME,
        "rules_version": "NATIVE_GEOMETRIC_REGION_RULES_V001",
    }


def test_populated_page_keeps_prose_and_tabular_coverage_separate() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    page = _page(_table() + _prose())
    regions, _, _, coverage, accepted, unresolved, _ = admit(page)
    assert [region["classification"] for region in regions] == [
        "candidate_tabular_region",
        "candidate_prose_region",
    ]
    assert len(coverage) == 44
    assert len(accepted) == 44
    assert unresolved == {}
    assert all(region["source_negative_established"] is False for region in regions)


def test_strict_json_read_and_exclusive_write(tmp_path: Path) -> None:
    from peru_conflicts.execution.native_documentary.io import read, write

    path = tmp_path / "invented.json"
    write(path, {"literal": "¡Árbol  ñ!\n¿qué?"})
    original = path.read_bytes()
    assert read(path) == {"literal": "¡Árbol  ñ!\n¿qué?"}
    with pytest.raises(FileExistsError):
        write(path, {"literal": "replacement"})
    assert path.read_bytes() == original


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_json_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path: Path, raw: bytes) -> None:
    from peru_conflicts.execution.native_documentary.io import read

    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        read(path)


def test_native_loader_retains_unicode_spans_and_layout_pointers(tmp_path: Path) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native, pin

    page = _page([("¡Árbol  ñ!\n¿qué?", [40, 50, 120, 58])])
    contract = _contract(tmp_path, page)
    loaded, evidence = load_native(contract)
    assert loaded == page
    assert evidence[0]["text"] == "¡Árbol  ñ!\n¿qué?"
    assert evidence[0]["span"] == [0, 16]
    assert evidence[0]["layout_pointers"] == ["/layout_lines/0/words/0"]
    assert evidence[0]["native_sha256"] == pin(contract["input"]["path"])["sha256"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("version", "unsupported", "unsupported_contract"),
        ("coordinate_representation", "image_pixels", "unsupported_coordinate_representation"),
        ("rules_version", "changed", "unsupported_rules"),
    ],
)
def test_native_loader_rejects_foreign_contract(
    tmp_path: Path, field: str, value: str, reason: str
) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    contract = _contract(tmp_path, _page(_table()))
    contract[field] = value
    with pytest.raises(ValueError, match=reason):
        load_native(contract)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("sha256", "0" * 64, "native_hash_mismatch"),
        ("physical_page", 8, "unauthorized_physical_page"),
        ("dimensions", [601, 900], "native_dimension_mismatch"),
        ("reference_sha256", "c" * 64, "reference_identity_mismatch"),
    ],
)
def test_native_loader_rejects_mismatched_pins(
    tmp_path: Path, field: str, value: Any, reason: str
) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    contract = _contract(tmp_path, _page(_table()))
    contract["input"][field] = value
    with pytest.raises(ValueError, match=reason):
        load_native(contract)


@pytest.mark.parametrize("bbox", [None, [1, 2, 0, 4], [0, 2, 700, 4], [False, 2, 3, 4], [1, 2, 3]])
def test_native_loader_rejects_malformed_geometry(tmp_path: Path, bbox: Any) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    page = _page(_table())
    page["words"][0]["bbox"] = bbox
    with pytest.raises(ValueError, match="geometry"):
        load_native(_contract(tmp_path, page))


@pytest.mark.parametrize("span", [[0, 1], [-1, 2], [0, 500], [True, 2], [0, 0]])
def test_native_loader_rejects_invalid_spans(tmp_path: Path, span: list[int]) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    page = _page(_table())
    page["words"][0]["span"] = span
    with pytest.raises(ValueError, match="span"):
        load_native(_contract(tmp_path, page))


@pytest.mark.parametrize(
    "fault", ["duplicate_word", "missing_line", "duplicate_line", "unknown_word"]
)
def test_native_loader_rejects_incomplete_or_duplicate_layout(tmp_path: Path, fault: str) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    page = _page(_table())
    if fault == "duplicate_word":
        page["words"].append(copy.deepcopy(page["words"][0]))
    elif fault == "missing_line":
        page["layout_lines"].pop()
    elif fault == "duplicate_line":
        page["layout_lines"].append(copy.deepcopy(page["layout_lines"][0]))
    else:
        page["layout_lines"][0]["words"][0]["text"] = "foreign"
    with pytest.raises(ValueError):
        load_native(_contract(tmp_path, page))


def test_geometry_does_not_consult_body_or_heading_text() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    page = _page([("heading", [200, 35, 270, 43]), *_table()])
    before = admit(page)
    for word in page["words"]:
        del word["text"]
    del page["text"]
    after = admit(page)
    assert before == after


def test_missing_leading_word_does_not_invent_rows_or_fields() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    entries = _table()
    entries.pop(6)
    regions, _, _, coverage, _, _, _ = admit(_page(entries))
    assert [item["word_index"] for item in coverage] == list(range(11))
    assert all("rows" not in region and "fields" not in region for region in regions)


def test_adjacent_aligned_blocks_retain_competing_ownership() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    page = _page([*_table(rows=3), ("context", [180, 130, 230, 138]), *_table(y=180, rows=3)])
    regions, _, hypotheses, coverage, accepted, unresolved, ambiguities = admit(page)
    assert len(regions) == 3
    assert any(len(hypothesis["region_ids"]) == 3 for hypothesis in hypotheses)
    assert accepted == {}
    assert len(unresolved) == 19
    assert all(word["accepted_region_owner"] is None for word in coverage)
    assert ambiguities["boundary_hypotheses"] == hypotheses


def test_spanning_text_abstains_without_claiming_box_overlap() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    page = _page(_table(rows=6) + _prose(y=84, lines=1))
    regions, _, _, _, _, unresolved, ambiguities = admit(page)
    assert any(region["classification"] == "ambiguous_region" for region in regions)
    assert unresolved
    assert ambiguities["native_word_box_overlaps"] == []


def test_retained_box_overlap_is_explicit_and_abstains() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    page = _page([*_table(), ("overlap", [51, 60, 76, 68])])
    regions, _, _, coverage, accepted, unresolved, ambiguities = admit(page)
    assert ambiguities["native_word_box_overlaps"] == [
        {
            "word_indices": [0, 12],
            "kind": "retained_word_bbox_overlap_not_automatically_shared_ownership",
        }
    ]
    assert regions[0]["classification"] == "ambiguous_region"
    assert accepted == {}
    assert len(unresolved) == 13
    assert all(word["accepted_region_owner"] is None for word in coverage)


@pytest.mark.parametrize("text", [None, ""])
def test_missing_word_text_is_not_a_negative_source_result(tmp_path: Path, text: Any) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    page = _page(_table())
    page["words"][0]["text"] = text
    with pytest.raises(ValueError, match="missing_null_or_empty_word"):
        load_native(_contract(tmp_path, page))


def test_loader_hashes_and_parses_one_retained_buffer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.execution.native_documentary.io import load_native

    page = _page(_table())
    contract = _contract(tmp_path, page)
    source = Path(contract["input"]["path"])
    raw = source.read_bytes()
    calls: list[Path] = []

    def read_once(path: Path) -> bytes:
        assert path == source
        calls.append(path)
        assert len(calls) == 1
        return raw

    monkeypatch.setattr(Path, "read_bytes", read_once)
    loaded, _ = load_native(contract)
    assert loaded == page
    assert calls == [source]


def test_two_column_flow_and_hanging_list_do_not_become_tables() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    flow = _prose(y=70, lines=6, x=30, width=240) + _prose(y=70, lines=6, x=330, width=240)
    listing: list[tuple[str, list[float]]] = []
    for row in range(4):
        y = 60 + 16 * row
        listing.append((f"{row + 1}.", [40, y, 48, y + 8]))
        listing.extend(
            (f"text{col}", [90 + 42 * col, y, 120 + 42 * col, y + 8]) for col in range(3)
        )
    for entries in (flow, listing):
        regions, _, _, _, _, _, _ = admit(_page(entries))
        assert all(region["classification"] != "candidate_tabular_region" for region in regions)


def test_geometry_sorting_and_empty_page_are_explicit() -> None:
    from peru_conflicts.execution.native_documentary.admission import admit

    entries = _table() + _prose()
    forward = admit(_page(entries))[0]
    reverse = admit(_page(list(reversed(entries))))[0]
    assert [(region["bbox"], region["classification"]) for region in forward] == [
        (region["bbox"], region["classification"]) for region in reverse
    ]
    empty = admit(_page([]))
    assert empty[:6] == ([], [], [], [], {}, {})
