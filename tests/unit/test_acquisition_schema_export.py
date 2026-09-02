from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

DISCOVERY_V030_TREE_SHA256 = "00cbf40848c24d24eea454e25682061d5725abe01c24c6479ffa6d30fffd821b"
ACQUISITION_V010_TREE_SHA256 = "b1029c80de6bbb5f293407070ed165936ff892d436018273f5e5b60dd74f2c61"
ACQUISITION_V020_TREE_SHA256 = "da6f39205d0bc473bfb6b80ff7dab424b7bf8f8d9ce4fa04113813fa4b65b485"
V010_SCHEMA_FILENAMES = {
    "pilot_acquisition_plan.schema.json",
    "dry_run_result.schema.json",
    "network_authorization_artifact.schema.json",
    "acquisition_attempt_receipt.schema.json",
    "acquisition_failure_receipt.schema.json",
    "operational_ledger_record.schema.json",
}
V020_SCHEMA_FILENAMES = {
    "network_authorization_artifact.schema.json",
    "authorization_registry.schema.json",
    "storage_namespace_marker.schema.json",
    "execution_tree_manifest.schema.json",
    "durable_ledger_record.schema.json",
    "authorization_use_index_record.schema.json",
}


def _schema_tree_digest(version_dir: Path) -> str:
    rows = [
        f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(version_dir.glob("*.schema.json"))
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_acquisition_schema_export_module_exists() -> None:
    try:
        specification = importlib.util.find_spec("peru_conflicts.acquisition.schema_export")
    except ModuleNotFoundError:
        specification = None
    assert specification is not None


def test_discovery_v030_remains_immutable_while_acquisition_is_added() -> None:
    repo_root = Path(__file__).parents[2]
    assert (
        _schema_tree_digest(repo_root / "schemas" / "discovery" / "v0.3.0")
        == DISCOVERY_V030_TREE_SHA256
    )


def test_acquisition_v010_snapshot_digest_is_retained() -> None:
    repo_root = Path(__file__).parents[2]
    assert (
        _schema_tree_digest(repo_root / "schemas" / "acquisition" / "v0.1.0")
        == ACQUISITION_V010_TREE_SHA256
    )


def test_acquisition_v020_snapshot_digest_is_pinned() -> None:
    repo_root = Path(__file__).parents[2]
    assert (
        _schema_tree_digest(repo_root / "schemas" / "acquisition" / "v0.2.0")
        == ACQUISITION_V020_TREE_SHA256
    )


def test_acquisition_schema_export_api_exists() -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")

    assert callable(getattr(module, "rendered_acquisition_schemas", None))
    assert callable(getattr(module, "export_acquisition_schemas", None))
    assert callable(getattr(module, "acquisition_schemas_are_current", None))


def test_acquisition_export_writes_strict_versioned_schemas(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")

    written = module.export_acquisition_schemas(tmp_path)

    assert {path.name for path in written if path.parent.name == "v0.1.0"} == (
        V010_SCHEMA_FILENAMES
    )
    assert {path.name for path in written if path.parent.name == "v0.2.0"} == (
        V020_SCHEMA_FILENAMES
    )
    assert {path.parent for path in written} == {
        tmp_path / "acquisition" / "v0.1.0",
        tmp_path / "acquisition" / "v0.2.0",
    }
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith(f"/schemas/acquisition/{path.parent.name}/{path.name}")
        if "oneOf" not in schema:
            assert schema["additionalProperties"] is False


def test_acquisition_plan_schema_pins_exact_reviewed_v2(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")
    written = module.export_acquisition_schemas(tmp_path)
    schema_path = next(
        path
        for path in written
        if path.parent.name == "v0.1.0" and path.name == "pilot_acquisition_plan.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["const"]["plan_id"] == "m1-03-reports-260-269-v2"
    assert schema["const"]["authorization_status"] == "not_authorized"
    assert schema["const"]["baseline_receipt_git_commit"] == (
        "9281ebb2fcfbb6626dfcbebff98347a7ff9291d2"
    )
    assert len(schema["const"]["targets"]) == 10


def test_attempt_and_ledger_schemas_publish_conditional_variant_constraints(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")
    written = module.export_acquisition_schemas(tmp_path)
    by_name = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in written
        if path.parent.name == "v0.1.0"
    }

    attempt_guards = by_name["acquisition_attempt_receipt.schema.json"]["allOf"]
    ledger_guards = by_name["operational_ledger_record.schema.json"]["allOf"]
    assert len(attempt_guards) == 5
    assert attempt_guards[0]["then"]["properties"]["error_message"] == {"const": None}
    assert attempt_guards[1]["then"]["properties"]["transferred_bytes"] == {"const": 0}
    assert len(ledger_guards) == 6
    assert ledger_guards[0]["then"]["required"] == ["attempt"]
    assert ledger_guards[1]["then"]["required"] == ["failure"]
    assert ledger_guards[2]["then"]["properties"]["disposition"] == {
        "const": "identical_no_duplicate_raw_file"
    }
    assert ledger_guards[4]["then"]["properties"]["disposition"] == {"const": "stop_for_review"}
    assert ledger_guards[5]["then"]["properties"]["normalized_url"] == {"const": None}
    nested_attempt = by_name["operational_ledger_record.schema.json"]["$defs"][
        "AcquisitionAttemptReceipt"
    ]
    assert len(nested_attempt["allOf"]) == 5
    assert nested_attempt["allOf"][0]["then"]["properties"]["error_message"] == {"const": None}
    local_path_schema = by_name["operational_ledger_record.schema.json"]["properties"][
        "local_relative_path"
    ]["anyOf"][0]
    assert re.fullmatch(local_path_schema["pattern"], "01_raw/reports/../escape.pdf") is None
    assert re.fullmatch(local_path_schema["pattern"], "01_raw/reports/.") is None
    assert re.fullmatch(local_path_schema["pattern"], "01_raw/reports//") is None
    assert re.fullmatch(local_path_schema["pattern"], "01_raw/reports/2026/./report.pdf") is None
    assert re.fullmatch(local_path_schema["pattern"], "01_raw/reports/2026/report-269.pdf")

    attempt_schema = by_name["acquisition_attempt_receipt.schema.json"]
    safe_rate_header = attempt_schema["$defs"]["SafeRateLimitHeader"]
    assert set(safe_rate_header["properties"]["name"]["enum"]) == {
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
        "x-rate-limit-reset",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
    }
    assert safe_rate_header["properties"]["value"]["maxLength"] == 200
    assert safe_rate_header["properties"]["value"]["pattern"] == r"^[^\r\n]*$"
    safe_response = attempt_schema["$defs"]["SafeResponseHeaders"]
    assert len(safe_response["allOf"]) == 2
    redirect_guard = attempt_schema["allOf"][1]["then"]
    assert "response_headers" in redirect_guard["required"]
    ledger_schema = by_name["operational_ledger_record.schema.json"]
    assert ledger_schema["$defs"]["SafeRateLimitHeader"] == safe_rate_header
    assert len(ledger_schema["$defs"]["SafeResponseHeaders"]["allOf"]) == 2
    nested_redirect_guard = ledger_schema["$defs"]["AcquisitionAttemptReceipt"]["allOf"][1]["then"]
    assert "response_headers" in nested_redirect_guard["required"]


def test_acquisition_schema_render_and_check_are_deterministic(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")
    first = module.export_acquisition_schemas(tmp_path)
    first_bytes = {(path.parent.name, path.name): path.read_bytes() for path in first}

    second = module.export_acquisition_schemas(tmp_path)

    assert {(path.parent.name, path.name): path.read_bytes() for path in second} == first_bytes
    assert module.acquisition_schemas_are_current(tmp_path) is True
    first[0].write_text("{}\n", encoding="utf-8")
    assert module.acquisition_schemas_are_current(tmp_path) is False


def test_v020_schema_contract_is_additive_strict_and_hash_chained(tmp_path: Path) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.schema_export")
    written = module.export_acquisition_schemas(tmp_path)
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in written
        if path.parent.name == "v0.2.0"
    }

    authorization = schemas["network_authorization_artifact.schema.json"]
    assert authorization["properties"]["schema_version"]["const"] == "0.2.0"
    assert authorization["properties"]["scope"]["const"].endswith("compare_only")
    assert authorization["additionalProperties"] is False
    assert schemas["authorization_registry.schema.json"]["additionalProperties"] is False
    ledger = schemas["durable_ledger_record.schema.json"]
    assert ledger["discriminator"]["propertyName"] == "record_type"
    assert len(ledger["oneOf"]) == 11
    assert "DurableTemporaryRecoveryV2" in ledger["$defs"]
    index = schemas["authorization_use_index_record.schema.json"]
    assert index["discriminator"]["propertyName"] == "record_type"
    assert len(index["oneOf"]) == 4


def test_top_level_schema_check_includes_acquisition(tmp_path: Path) -> None:
    scientific = importlib.import_module("peru_conflicts.schema_export")
    discovery = importlib.import_module("peru_conflicts.discovery.schema_export")
    acquisition = importlib.import_module("peru_conflicts.acquisition.schema_export")
    benchmark = importlib.import_module("peru_conflicts.benchmark.schema_export")
    manifest = importlib.import_module("peru_conflicts.manifest.schema_export")
    scientific.export_json_schemas(tmp_path)
    discovery.export_discovery_schemas(tmp_path)
    written = acquisition.export_acquisition_schemas(tmp_path)
    manifest.export_manifest_schemas(tmp_path)
    benchmark.export_benchmark_schemas(tmp_path / "benchmark")

    command = [
        sys.executable,
        "scripts/export_schemas.py",
        "--check",
        "--output",
        str(tmp_path),
    ]
    current = subprocess.run(command, check=False, capture_output=True, text=True)
    written[0].write_text("{}\n", encoding="utf-8")
    drifted = subprocess.run(command, check=False, capture_output=True, text=True)

    assert current.returncode == 0, current.stdout + current.stderr
    assert drifted.returncode == 1
    assert "acquisition" in drifted.stdout.lower()
