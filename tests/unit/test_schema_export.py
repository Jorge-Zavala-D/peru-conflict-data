from __future__ import annotations

import json
from pathlib import Path

from peru_conflicts.models import MODEL_REGISTRY, SCHEMA_VERSION
from peru_conflicts.schema_export import export_json_schemas, schemas_are_current


def test_export_writes_one_strict_schema_per_registered_model(tmp_path: Path) -> None:
    written = export_json_schemas(tmp_path)

    assert {path.stem.removesuffix(".schema") for path in written} == set(MODEL_REGISTRY)
    assert all(path.parent == tmp_path / f"v{SCHEMA_VERSION}" for path in written)
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False


def test_schema_export_is_deterministic_and_checkable(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    current = tmp_path / f"v{SCHEMA_VERSION}"
    first = {path.name: path.read_bytes() for path in current.glob("*.schema.json")}

    export_json_schemas(tmp_path)
    second = {path.name: path.read_bytes() for path in current.glob("*.schema.json")}

    assert first == second
    assert schemas_are_current(tmp_path) is True


def test_schema_export_preserves_prior_version_directories(tmp_path: Path) -> None:
    historical = tmp_path / "v0.0.9" / "report.schema.json"
    historical.parent.mkdir()
    historical.write_text('{"historical": true}\n', encoding="utf-8")

    export_json_schemas(tmp_path)

    assert historical.read_text(encoding="utf-8") == '{"historical": true}\n'


def test_probabilistic_provenance_requirement_is_present_in_json_schema(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)
    schema_path = tmp_path / f"v{SCHEMA_VERSION}" / "provenance.schema.json"
    rendered = json.loads(schema_path.read_text(encoding="utf-8"))

    assert {
        "if": {
            "properties": {"extraction_method": {"const": "probabilistic_model"}},
            "required": ["extraction_method"],
        },
        "then": {"required": ["model_invocation"]},
    } in rendered["allOf"]


def test_schema_check_detects_drift(tmp_path: Path) -> None:
    written = export_json_schemas(tmp_path)
    written[0].write_text("{}\n", encoding="utf-8")

    assert schemas_are_current(tmp_path) is False


def test_schema_exports_indicator_and_report_identity_safety_conditions(tmp_path: Path) -> None:
    export_json_schemas(tmp_path)

    report_month = json.loads(
        (tmp_path / f"v{SCHEMA_VERSION}" / "report_month.schema.json").read_text(encoding="utf-8")
    )
    report = json.loads(
        (tmp_path / f"v{SCHEMA_VERSION}" / "report.schema.json").read_text(encoding="utf-8")
    )

    assert len(report_month["allOf"]) == 2
    assert len(report["allOf"]) == 2
    source_guard, derived_guard = report_month["allOf"]
    assert source_guard["if"]["properties"]["indicator_basis"]["const"] == "source_reported"
    assert derived_guard["if"]["properties"]["indicator_basis"]["const"] == "derived"
    assert {
        "document_visible",
        "official_metadata",
    } == set(
        report["allOf"][0]["then"]["properties"]["report_number_evidence_types"]["contains"]["enum"]
    )
