"""Public pipeline operations on complete invented native pages only."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from peru_conflicts.execution.native_documentary import VERSION, pipeline, receiver
from peru_conflicts.execution.native_documentary.io import FRAME, pin, read, write


def native_manifest(root: Path, layout: str) -> dict[str, Any]:
    rows = (
        [
            ["N.°", "Lugar", "Caso", "Situación"],
            ["1.", "Valle", "Petición", "Activo"],
            ["2.", "Isla", "Solicitud", "Diálogo"],
        ]
        if layout == "priority"
        else [["Región", "Total", "%"], ["Azul", "7", "35.0%"], ["TOTAL", "20", "100.0%"]]
    )
    xs = [30, 100, 260, 440] if layout == "priority" else [50, 280, 450]
    words: list[dict[str, Any]] = []
    text = ""
    for row_number, row in enumerate(rows):
        for x, token in zip(xs, row, strict=True):
            start = len(text)
            text += token
            words.append(
                {
                    "text": token,
                    "span": [start, len(text)],
                    "bbox": [
                        x,
                        30 + row_number * 15,
                        x + max(12, len(token) * 4),
                        39 + row_number * 15,
                    ],
                }
            )
            text += " \n"
    page = {
        "physical_page": 17,
        "width": 650,
        "height": 500,
        "text": text,
        "words": words,
        "layout_lines": [{"words": [word]} for word in words],
        "reference_sha256": "a" * 64,
        "representation_status": "native_text_present",
    }
    write(root / "native.json", page)
    return {
        "version": VERSION,
        "mode": "invented",
        "coordinate_representation": FRAME,
        "source": {"pdf_sha256": "b" * 64, "report_number": 999},
        "input": pin(root / "native.json")
        | {"physical_page": 17, "dimensions": [650, 500], "reference_sha256": "a" * 64},
    }


@pytest.mark.parametrize("layout", ["priority", "regional"])
def test_complete_invented_page_through_public_pipeline(tmp_path: Path, layout: str) -> None:
    manifest = native_manifest(tmp_path, layout)
    write(tmp_path / "manifest.json", manifest)
    assert (
        pipeline.main(
            [
                "--operation",
                "pipeline",
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--output",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    result = read(tmp_path / "run/run_result.json")
    assert result["calls"] == {
        "admission": 1,
        "regional": int(layout == "regional"),
        "priority": int(layout == "priority"),
        "engine": 1,
    }
    assert result["engine_status"] == "processed"
    assert read(tmp_path / "run/composition/engine_result.json")["candidate_status"] == "processed"
    assert not result["semantic_page_completeness"]


def test_no_dispatch_keeps_accounting_and_does_not_call_engine(tmp_path: Path) -> None:
    manifest = native_manifest(tmp_path, "priority")
    page = read(tmp_path / "native.json")
    # Rebind exact original spans after replacing an invented heading, not a value repair.
    page["text"] = page["text"].replace("Lugar", "Rumbo")
    page["words"][1]["text"] = "Rumbo"
    page["layout_lines"][1]["words"][0]["text"] = "Rumbo"
    write(tmp_path / "unknown.json", page)
    manifest["input"] = pin(tmp_path / "unknown.json") | {
        "physical_page": 17,
        "dimensions": [650, 500],
        "reference_sha256": "a" * 64,
    }
    result = pipeline.run_pipeline(manifest, tmp_path / "run")
    assert result["calls"] == {"admission": 1, "regional": 0, "priority": 0, "engine": 0}
    accounting = read(tmp_path / "run/composition/source_scope_accounting.json")
    assert accounting["source_words"] == len(page["words"])
    assert accounting["outside_adapter_words"] == len(page["words"])
    assert not result["source_negative_established"]


def test_actual_scope_cannot_gain_generation_from_receiving_authority(tmp_path: Path) -> None:
    manifest = native_manifest(tmp_path, "priority")
    manifest["mode"] = "actual"
    manifest["run_scope"] = {
        "allowed_operations": ["receive"],
        "permitted_native_sha256": [manifest["input"]["sha256"]],
        "permitted_physical_pages": [17],
        "output_root": str(tmp_path),
    }
    with pytest.raises(ValueError, match="operation_not_authorized"):
        pipeline.run_pipeline(manifest, tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()


def test_registry_is_known_layout_only_not_admission_input() -> None:
    assert receiver.registry()["unknown_or_competing"] == "no_dispatch"


def test_regional_generation_uses_separate_actual_scope_on_invented_words(tmp_path: Path) -> None:
    manifest = native_manifest(tmp_path, "regional")
    manifest["mode"] = "actual"
    manifest["run_scope"] = {
        "allowed_operations": ["pipeline", "compose"],
        "permitted_native_sha256": [manifest["input"]["sha256"]],
        "permitted_physical_pages": [17],
        "output_root": str(tmp_path),
        "allowed_adapters": ["regional"],
        "max_adapter_calls": 1,
        "max_engine_calls": 1,
    }
    result = pipeline.run_pipeline(manifest, tmp_path / "run")
    assert result["calls"] == {"admission": 1, "regional": 1, "priority": 0, "engine": 1}
    assert result["engine_status"] == "processed"


def test_failed_generator_entry_is_counted_and_not_retried(tmp_path: Path) -> None:
    manifest = native_manifest(tmp_path, "regional")
    with (
        patch.object(
            receiver, "scoped_regional", side_effect=RuntimeError("invented failure")
        ) as gen,
        pytest.raises(RuntimeError, match="invented failure"),
    ):
        pipeline.run_pipeline(manifest, tmp_path / "run")
    assert gen.call_count == 1
    calls = read(tmp_path / "run/invocation_accounting.json")["calls"]
    assert calls == {"admission": 1, "regional": 1, "priority": 0, "engine": 0}
    assert not (tmp_path / "run/composition/engine_config.json").exists()
