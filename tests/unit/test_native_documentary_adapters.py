"""Known native adapters exercised only with invented words and geometry."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peru_conflicts.execution.native_documentary import priority, regional


def word(text: str, x: float, y: float, width: float = 12) -> dict[str, Any]:
    return {"text": text, "bbox": [x, y, x + width, y + 10], "span": [0, len(text)]}


def priority_page() -> dict[str, Any]:
    return {
        "physical_page": 41,
        "width": 250,
        "height": 200,
        "words": [
            word("N.°", 0, 10),
            word("Lugar", 40, 10, 25),
            word("Caso", 110, 10, 25),
            word("Situación", 190, 10, 45),
            word("1.", 2, 40, 8),
            word("Inventado", 40, 40, 35),
            word("Relato", 110, 40, 30),
            word("Pendiente", 190, 40, 40),
        ],
    }


def contract() -> dict[str, Any]:
    return {
        "mode": "invented",
        "source": {"pdf_sha256": "a" * 64, "report_number": 900001},
        "input": {"physical_page": 41, "sha256": "b" * 64, "dimensions": [250, 200]},
    }


def evidence(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(w) | {"word_index": i} for i, w in enumerate(page["words"])]


def test_priority_uses_whole_page_geometry_for_stop_without_accepting_context() -> None:
    page = priority_page()
    context = [{"bbox": w["bbox"]} for w in page["words"]]
    context.append({"bbox": [0, 80, 250, 90]})
    candidate, coverage = priority.discover(page, contract(), evidence(page), context)
    assert candidate["status"] == "processed"
    assert candidate["table_region"]["after_last_ordinal_gap"] == [50, 80]
    assert candidate["rows"][0]["row_id"] == "p041:ordinal-word-4"
    assert [c["value"] for c in candidate["rows"][0]["cells"]] == [
        "Inventado",
        "Relato",
        "Pendiente",
    ]
    assert len(coverage) == 8


def test_priority_retains_four_height_unanchored_neighbor_guard() -> None:
    page = priority_page()
    context = [{"bbox": w["bbox"]} for w in page["words"]]
    context.extend({"bbox": [x, 80, x + 10, 90]} for x in (40, 110, 190))
    candidate, coverage = priority.discover(page, contract(), evidence(page), context)
    assert candidate["status"] == "partial"
    assert candidate["unresolved"] == [
        {"kind": "possible_unanchored_continuation_after_stop", "context_word_indices": [8, 9, 10]}
    ]
    assert len(coverage) == 8


def test_priority_missing_status_is_null_and_multiline_status_stays_ambiguous() -> None:
    page = priority_page()
    page["words"].pop()
    context = [{"bbox": w["bbox"]} for w in page["words"]] + [{"bbox": [0, 100, 250, 110]}]
    candidate, _ = priority.discover(page, contract(), evidence(page), context)
    cell = candidate["rows"][0]["cells"][2]
    assert (cell["status"], cell["value"]) == ("unavailable_no_qualified_words", None)
    page = priority_page()
    page["words"].append(word("Otra", 190, 55, 20))
    context = [{"bbox": w["bbox"]} for w in page["words"]] + [{"bbox": [0, 100, 250, 110]}]
    candidate, _ = priority.discover(page, contract(), evidence(page), context)
    cell = candidate["rows"][0]["cells"][2]
    assert cell["status"] == "ambiguous_ownership"
    assert cell["value"] is None
    assert cell["reconstruction_if_unqualified"] == "Pendiente\nOtra"


def regional_page() -> dict[str, Any]:
    words = [
        word("Región", 0, 10, 30),
        word("Total", 100, 10, 25),
        word("%", 190, 10),
        word("Inventada", 0, 30, 35),
        word("7", 100, 30),
        word("12.5%", 190, 30, 30),
        word("Nota", 0, 50, 25),
        word("Segunda", 0, 70, 35),
        word("3", 100, 70),
        word("5%", 190, 70, 20),
    ]
    return {"physical_page": 41, "width": 250, "height": 200, "text": "invented", "words": words}


def test_regional_stops_at_first_unqualified_neighbor_and_reference_is_explicit() -> None:
    page = regional_page()
    words = evidence(page)
    spec = {"physical_page": 41, "layout_sha256": "b" * 64}
    result = regional.adapt_page(page, words, spec, contract()["source"], reference_text="invented")
    assert result["reference_text_identical_to_joined_word_text"] is True
    assert [[c["value"] for c in row["cells"]] for row in result["rows"]] == [
        ["Inventada", "7", "12.5%"],
    ]
    assert result["unresolved_components"][0]["reason"] == "not_a_complete_three_column_row"
    assert result["word_coverage"][7]["status"] == "unprocessed_after_first_stop"
    result = regional.adapt_page(page, words, spec, contract()["source"])
    assert result["reference_text_identical_to_joined_word_text"] is None


def test_scoped_priority_retains_original_memberships() -> None:
    page = priority_page()
    page["words"].insert(0, word("Contexto", 0, 0, 35))
    view = SimpleNamespace(
        region={"region_id": "invented-region"},
        ids=list(range(1, 9)),
        page=page,
        words=page["words"][1:],
        evidence=evidence(page)[1:],
        context=[{"bbox": w["bbox"]} for w in page["words"]] + [{"bbox": [0, 80, 250, 90]}],
        record={},
    )
    result = priority.scoped_priority(view, contract())
    assert result["rows"][0]["row_id"] == "p041:ordinal-word-5"
    assert [c["word_indices"] for c in result["rows"][0]["cells"]] == [[6], [7], [8]]
    assert result["view"]["boundary_context_access"]["text_access"] is False


def test_scoped_regional_preserves_membership_and_never_creates_reference(tmp_path: Path) -> None:
    page = regional_page()
    page["words"] = page["words"][:6]
    page["words"].insert(0, word("Contexto", 0, 0, 35))
    view = SimpleNamespace(
        region={"region_id": "invented-region"},
        ids=list(range(1, 7)),
        page=page,
        words=page["words"][1:],
        evidence=evidence(page)[1:],
        record={},
    )
    result = regional.scoped_regional(view, contract(), tmp_path)
    assert result["status"] == "processed"
    assert [c["word_indices"] for c in result["rows"][0]["cells"]] == [[4], [5], [6]]
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match="regional_generation_not_authorized"):
        regional.scoped_regional(view, contract() | {"mode": "actual"}, tmp_path)


def profile_fixture(tmp_path: Path, adapter: str) -> tuple[Path, Path]:
    from peru_conflicts.execution.native_documentary.io import pin, write

    page = priority_page() if adapter == "priority" else regional_page()
    if adapter == "regional":
        page["words"] = page["words"][:6]
    page["words"].append(word("Crédito", 0, 100, 250))
    text = ""
    for w in page["words"]:
        w["span"] = [len(text), len(text) + len(w["text"])]
        text += w["text"] + "\n"
    page["text"] = text
    page["layout_lines"] = [{"words": [w]} for w in page["words"]]
    native_path = tmp_path / "native.json"
    write(native_path, page)
    spec = contract()
    spec["input"] |= pin(native_path)
    spec["admission"] = {"sha256": "c" * 64}
    ids = list(range(len(page["words"]) - 1))
    view = SimpleNamespace(
        region={"region_id": "invented-region"},
        ids=ids,
        page=page,
        words=page["words"][:-1],
        evidence=evidence(page)[:-1],
        context=[{"bbox": w["bbox"]} for w in page["words"]],
        record={"word_indices": ids, "bbox": [0, 10, 250, 100]},
    )
    result = (
        priority.scoped_priority(view, spec)
        if adapter == "priority"
        else regional.scoped_regional(view, spec, tmp_path)
    )
    candidate_path = tmp_path / "composed_candidate.json"
    write(candidate_path, spec | {"results": [result]})
    source_evidence = evidence(page)
    for i, e in enumerate(source_evidence):
        e["layout_pointers"] = [f"/layout_lines/{i}/words/0"]
    evidence_path = tmp_path / "source_word_evidence.json"
    write(evidence_path, {"input": spec["input"], "words": source_evidence})
    rows = result["rows"]
    cells = [result["header"]["labels"]] + [
        ([r["ordinal"]["text"]] if adapter == "priority" else []) + [c["value"] for c in r["cells"]]
        for r in rows
    ]
    derivative_path = tmp_path / "table_derivative.json"
    write(
        derivative_path,
        {
            "source_sha256": spec["source"]["pdf_sha256"],
            "report_number": 900001,
            "physical_page": 41,
            "status": "region_scoped_native_word_derivative_v001",
            "authority": "invented documentary fixture",
            "empty_table_result_certifies_absence": False,
            "candidate": pin(candidate_path),
            "native_sha256": spec["input"]["sha256"],
            "tables": [
                {
                    "region_id": result["region_id"],
                    "bbox": [0, 10, 250, 100],
                    "cells": cells,
                    "adapter": adapter,
                    "row_ids": [r["row_id"] for r in rows],
                }
            ],
        },
    )
    write(
        tmp_path / "candidate_seal.json",
        {
            "files": [pin(p) for p in (candidate_path, derivative_path, evidence_path)],
        },
    )
    return candidate_path, derivative_path


@pytest.mark.parametrize("adapter", ["priority", "regional"])
def test_profile_preserves_source_anchors_and_reaches_unchanged_engine(
    tmp_path: Path,
    adapter: str,
) -> None:
    from peru_conflicts.execution import source_addressed_tables as engine
    from peru_conflicts.execution.native_documentary.io import pin, read
    from peru_conflicts.execution.native_documentary.profile import compile_profile

    candidate, derivative = profile_fixture(tmp_path, adapter)
    config_path = tmp_path / "config.json"
    config = compile_profile(candidate, derivative, config_path, pin(engine.__file__)["sha256"])
    assert config["artifacts"][0]["artifact_id"] == "native"
    assert engine.run(config_path, tmp_path / "engine.json") == 0
    output = read(tmp_path / "engine.json")
    assert output["candidate_status"] == "processed"
    assert (
        output["counts"]["documentary_rows" if adapter == "priority" else "published_measurements"]
        == 1
    )


def test_profile_rejects_engine_pin_before_reading_candidate(tmp_path: Path) -> None:
    from peru_conflicts.execution.native_documentary.profile import compile_profile

    with pytest.raises(ValueError, match="engine_identity_mismatch"):
        compile_profile(
            tmp_path / "missing.json",
            tmp_path / "missing2.json",
            tmp_path / "config.json",
            "0" * 64,
        )
    assert not (tmp_path / "config.json").exists()


@pytest.mark.parametrize("mutation", ["cell_value", "header_label"])
def test_profile_rejects_sealed_text_that_disagrees_with_native_words(
    tmp_path: Path,
    mutation: str,
) -> None:
    from peru_conflicts.execution.native_documentary.io import pin, read
    from peru_conflicts.execution.native_documentary.profile import build

    candidate_path, derivative_path = profile_fixture(tmp_path, "priority")
    candidate, derivative = read(candidate_path), read(derivative_path)
    if mutation == "cell_value":
        candidate["results"][0]["rows"][0]["cells"][0]["value"] = "Alterado"
        derivative["tables"][0]["cells"][1][1] = "Alterado"
    else:
        candidate["results"][0]["header"]["labels"][1] = "Alterado"
        derivative["tables"][0]["cells"][0][1] = "Alterado"
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    derivative["candidate"] = pin(candidate_path)
    derivative_path.write_text(json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
    seal_path = tmp_path / "candidate_seal.json"
    seal = read(seal_path)
    seal["files"] = [pin(item["path"]) for item in seal["files"]]
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    with pytest.raises(ValueError, match="failed_direct_validation"):
        build(tmp_path)
    audit = read(tmp_path / "direct_validation.json")
    assert audit["failed_checks"] > 0
    assert audit["generation_not_called"] is True
