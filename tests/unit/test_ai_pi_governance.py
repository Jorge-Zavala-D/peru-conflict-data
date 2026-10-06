"""Executable source-safe strategy, roadmap and additive-schema contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from peru_conflicts.acquisition.schema_export import export_acquisition_schemas
from peru_conflicts.benchmark.schema_export import export_benchmark_schemas
from peru_conflicts.discovery.schema_export import export_discovery_schemas
from peru_conflicts.execution.ai_pi import StrategyDecision, export_schema, schema_bytes
from peru_conflicts.execution.owner_assisted import export_manual_schema
from peru_conflicts.execution.setup_authority import export_real_schema
from peru_conflicts.execution.setup_bridge import export_setup_schema
from peru_conflicts.execution.setup_deployment import export_installation_schema
from peru_conflicts.manifest.schema_export import export_manifest_schemas
from peru_conflicts.schema_export import export_json_schemas

ROOT = Path(__file__).resolve().parents[2]


def test_active_strategy_and_historical_plan_are_unambiguous() -> None:
    decision = StrategyDecision.model_validate_json(
        (ROOT / "config/ai_pi/strategy_v1.json").read_bytes()
    )
    assert decision.real_execution_authorized is False
    for path in ("README.md", "AGENTS.md", "docs/ai_pi_strategy.md"):
        content = (ROOT / path).read_text(encoding="utf-8")
        assert decision.strategy_id in content
        assert "plan" in content.lower()
    roadmap = json.loads((ROOT / "config/ai_pi/roadmap_v1.json").read_bytes())
    assert (
        hashlib.sha256((ROOT / "docs/execution_plan.md").read_bytes()).hexdigest()
        == (roadmap["source_baseline"]["historical_plan_sha256"])
    )


def test_complete_successor_graph_crosswalk_and_metrics() -> None:
    roadmap = json.loads((ROOT / "config/ai_pi/roadmap_v1.json").read_bytes())
    tasks: dict[str, Any] = {card["id"]: card for card in roadmap["tasks"]}
    assert len(tasks) == len(roadmap["tasks"])
    required = {
        "objective",
        "inputs",
        "outputs",
        "dependencies",
        "technical_checks",
        "pi_validation",
        "completion",
        "exclusions",
        "resource_drivers",
        "next_handoff",
    }
    for card in tasks.values():
        assert required.issubset(card)
        assert set(card["dependencies"]).issubset(tasks)
        assert card["id"] not in card["dependencies"]
    pending = set(tasks)
    resolved: set[str] = set()
    while pending:
        ready = {name for name in pending if set(tasks[name]["dependencies"]) <= resolved}
        assert ready, "successor dependency cycle"
        pending -= ready
        resolved |= ready
    old = {entry["old_id"] for entry in roadmap["historical_crosswalk"]}
    assert {
        "M0",
        "M0.1",
        *(f"M{n}-{i:02d}" for n in range(1, 5) for i in range(1, 5)),
        *(f"M{n}" for n in range(5, 13)),
    } <= old
    for entry in roadmap["historical_crosswalk"]:
        assert set(entry["successors"]).issubset(tasks)
        assert entry["disposition"] and entry["reason"]
    assert roadmap["inherited_metric_dispositions"]
    for prefix in ("M2R", "M3R", "W1", *(f"M{i}R" for i in range(4, 13))):
        assert any(name.startswith(prefix + "-") for name in tasks)


def test_additive_schema_refs_resolve_and_complete_gate_detects_missing_and_drift(
    tmp_path: Path,
) -> None:
    schema = json.loads(schema_bytes())
    definitions = schema["$defs"]

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            mapping = cast(dict[str, Any], value)
            if "$ref" in mapping:
                assert str(mapping["$ref"]).removeprefix("#/$defs/") in definitions
            for child in mapping.values():
                walk(child)
        elif isinstance(value, list):
            for child in cast(list[Any], value):
                walk(child)

    walk(schema)
    for exporter in (
        export_json_schemas,
        export_discovery_schemas,
        export_acquisition_schemas,
        export_manifest_schemas,
        export_setup_schema,
        export_real_schema,
        export_installation_schema,
        export_manual_schema,
    ):
        exporter(tmp_path)
    export_benchmark_schemas(tmp_path / "benchmark")
    command = [
        sys.executable,
        str(ROOT / "scripts/export_schemas.py"),
        "--check",
        "--output",
        str(tmp_path),
    ]
    missing = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)
    assert missing.returncode == 1 and "AI/PI" in missing.stdout
    path = export_schema(tmp_path)
    current = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)
    assert current.returncode == 0, current.stdout + current.stderr
    path.write_bytes(b"{}\n")
    drift = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)
    assert drift.returncode == 1 and "AI/PI" in drift.stdout
