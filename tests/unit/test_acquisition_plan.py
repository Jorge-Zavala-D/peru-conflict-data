from __future__ import annotations

import hashlib
import importlib
import importlib.util
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

V1_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v1.yaml")
V2_PATH = Path("config/acquisition_pilots/m1_03_reports_260_269_v2.yaml")
V1_FILE_SHA256 = "59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7"
MERGED_M1_SHA = "9281ebb2fcfbb6626dfcbebff98347a7ff9291d2"
M1_02_2_RECEIPT_SHA256 = "963a9b317f8485c58e4b8b7f408a4c8739ea23f0260fd7c368656f99d17a4cc2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v2_plan_exists_without_mutating_reviewed_v1() -> None:
    assert _sha256(V1_PATH) == V1_FILE_SHA256
    assert V2_PATH.is_file()

    payload = yaml.safe_load(V2_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.1.0"
    assert payload["plan_id"] == "m1-03-reports-260-269-v2"
    assert payload["authorization_status"] == "not_authorized"
    assert payload["baseline_receipt_path"] == "docs/source_integrity_receipt_m1_02_2.md"
    assert payload["baseline_receipt_git_commit"] == MERGED_M1_SHA
    assert payload["baseline_receipt_sha256"] == M1_02_2_RECEIPT_SHA256
    assert [target["report_number"] for target in payload["targets"]] == list(range(260, 270))
    assert len(payload["targets"]) * 2 == payload["limits"]["max_urls"] == 20


def test_acquisition_plan_module_exists() -> None:
    try:
        specification = importlib.util.find_spec("peru_conflicts.acquisition.plan")
    except ModuleNotFoundError:
        specification = None
    assert specification is not None


def test_acquisition_plan_loader_api_exists() -> None:
    module = importlib.import_module("peru_conflicts.acquisition.plan")

    assert callable(getattr(module, "load_reviewed_pilot_plan", None))
    assert getattr(module, "REVIEWED_V2_PLAN_FILE_SHA256", None) == (
        "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"
    )


def test_reviewed_v2_loader_pins_raw_semantic_and_target_fingerprints() -> None:
    module = importlib.import_module("peru_conflicts.acquisition.plan")

    loaded = module.load_reviewed_pilot_plan(
        V2_PATH,
        required_sha256="d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4",
    )

    assert loaded.plan.plan_id == "m1-03-reports-260-269-v2"
    assert loaded.plan.authorization_status == "not_authorized"
    assert loaded.plan.baseline_receipt_git_commit == MERGED_M1_SHA
    assert loaded.file_sha256 == "d5cab626ba167fc45c8b5147d04bc40f85aec3a952d7fd4dbd5543b20631b4c4"
    assert (
        loaded.semantic_sha256 == "e4b8ca609af2290563dab312488da0017ec67f5c8e05dbdf269861262b979c5b"
    )
    assert loaded.target_set_sha256 == (
        "721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1"
    )
    assert all(target.expected_remote_sha256 is None for target in loaded.plan.targets)
    assert {
        target.report_number: set(target.uncertainty_codes)
        for target in loaded.plan.targets
        if target.association_status == "unresolved_association"
    } == {
        261: {"opaque_filename", "unresolved_association"},
        263: {"opaque_filename", "unresolved_association"},
    }


def test_wrong_caller_digest_fails_before_yaml_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("peru_conflicts.acquisition.plan")
    yaml_called = False

    def fail_if_called(_: object) -> object:
        nonlocal yaml_called
        yaml_called = True
        raise AssertionError("YAML must not be parsed after a digest mismatch")

    monkeypatch.setattr(module.yaml, "safe_load", fail_if_called)

    with pytest.raises(module.PlanDigestMismatch, match="caller-required"):
        module.load_reviewed_pilot_plan(V2_PATH, required_sha256="0" * 64)
    assert yaml_called is False


@pytest.mark.parametrize(
    "replacement",
    [
        "http://www.defensoria.gob.pe/report.pdf",
        "https://www.defensoria.gob.pe:444/report.pdf",
        "https://user@example.org/report.pdf",
        "https://downloads.defensoria.gob.pe/report.pdf",
    ],
)
def test_acquisition_plan_rejects_unapproved_transport_authority(replacement: str) -> None:
    models = importlib.import_module("peru_conflicts.acquisition.models")
    payload = yaml.safe_load(V2_PATH.read_text(encoding="utf-8"))
    payload["targets"][0]["direct_download_url"] = replacement

    with pytest.raises(ValidationError):
        models.AcquisitionPilotPlan.model_validate(payload)
