"""Read-only active annotation custody; never execution or annotation authority."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import field_validator

from peru_conflicts.benchmark.metrics import CURRENT_BENCHMARK_METRIC_CONTRACT_VERSION
from peru_conflicts.benchmark.models import BENCHMARK_SCHEMA_VERSION
from peru_conflicts.execution.readiness_approval import OwnerReadinessApproval
from peru_conflicts.models.common import SCHEMA_VERSION, Sha256, StrictModel

ROOT = Path(__file__).resolve().parents[3]


class DatePairInterpretationApproval(StrictModel):
    approval_record_version: Literal["1.0.0"]
    approval_id: Literal["M2-DATE-PAIR-INTERPRETATION-RATIFICATION-V1"]
    owner: Literal["Jorge Zavala"]
    recorded_at: str
    authority: Literal["explicit_owner_ratification_in_m2_02a_1e_prompt_2026_09_11"]
    reviewed_pr_number: Literal[13]
    reviewed_parent_head: Literal["e53284ae55d9221b80a1af8dc6ec8d8742e527a1"]
    reviewed_parent_tree: Literal["e1692fc4dd8d4cfb54d9b0bc40e2008f9937fd8d"]
    source_date_correction_approval_sha256: Sha256
    interpretation_document_sha256: Sha256
    scientific_schema_version: Literal["0.3.1"]
    benchmark_schema_version: Literal["0.1.1"]
    metric_contract_version: Literal["0.1.1"]
    critical_field_set_expanded: Literal[False]
    evaluator_arithmetic_changed: Literal[False]
    owner_readiness_approved: Literal[False]
    annotation_launch_approved: Literal[False]
    human_gold_created: Literal[False]
    m3_approved: Literal[False]

    @field_validator("recorded_at")
    @classmethod
    def aware_recording_time(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("recording timestamp must include an offset")
        return value


class HistoricalAnnotationContractIdentityV3(StrictModel):
    """Immutable pre-ratification evidence shape, never an active authority."""

    scientific_schema_version: Literal["0.3.1"]
    scientific_schema_digest: Sha256
    benchmark_schema_version: Literal["0.1.1"]
    benchmark_schema_digest: Sha256
    metric_contract_version: Literal["0.1.1"]
    evaluator_sha256: Sha256
    critical_field_set_sha256: Sha256
    date_correction_approval_sha256: Sha256
    discovery_policy_approval_sha256: Sha256
    date_pair_interpretation_sha256: Sha256


class HistoricalAnnotationContractIdentityV4(HistoricalAnnotationContractIdentityV3):
    date_pair_interpretation_approval_sha256: Sha256


class AnnotationContractIdentity(HistoricalAnnotationContractIdentityV4):
    owner_readiness_approval_sha256: Sha256


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_digest(path: Path) -> str:
    return hashlib.sha256(
        "\n".join(f"{p.name}:{_sha(p)}" for p in sorted(path.glob("*.schema.json"))).encode()
    ).hexdigest()


def active_annotation_contract(root: Path = ROOT) -> AnnotationContractIdentity:
    """Re-read authoritative bytes on every boundary; never cache a mutable trust anchor."""
    config = root / "config/benchmark"
    ready = yaml.safe_load((config / "m2_02a_readiness_v3.yaml").read_bytes())
    run = yaml.safe_load((config / "m2_02_annotation_run_v1.yaml").read_bytes())
    approval_path = config / "m2_02_date_pair_interpretation_approval_v1.yaml"
    approval = DatePairInterpretationApproval.model_validate(
        yaml.safe_load(approval_path.read_bytes())
    )
    owner_path = config / "m2_02a_owner_readiness_approval_v1.yaml"
    owner = OwnerReadinessApproval.model_validate(yaml.safe_load(owner_path.read_bytes()))
    identity = AnnotationContractIdentity(
        scientific_schema_version=SCHEMA_VERSION,
        scientific_schema_digest=_schema_digest(root / "schemas" / f"v{SCHEMA_VERSION}"),
        benchmark_schema_version=BENCHMARK_SCHEMA_VERSION,
        benchmark_schema_digest=_schema_digest(
            root / "schemas/benchmark" / f"v{BENCHMARK_SCHEMA_VERSION}"
        ),
        metric_contract_version=CURRENT_BENCHMARK_METRIC_CONTRACT_VERSION,
        evaluator_sha256=_sha(root / "src/peru_conflicts/benchmark/metrics.py"),
        critical_field_set_sha256=_sha(config / "m2_critical_fields_v1.yaml"),
        date_correction_approval_sha256=_sha(
            config / "m2_01_date_semantics_correction_approval_v1.yaml"
        ),
        discovery_policy_approval_sha256=_sha(config / "m2_02_owner_approval_v1.yaml"),
        date_pair_interpretation_sha256=_sha(root / "docs/m2_02_date_pair_interpretation_v1.md"),
        date_pair_interpretation_approval_sha256=_sha(approval_path),
        owner_readiness_approval_sha256=_sha(owner_path),
    )
    for field in (
        "scientific_schema_digest",
        "benchmark_schema_digest",
        "evaluator_sha256",
        "critical_field_set_sha256",
        "date_pair_interpretation_approval_sha256",
    ):
        if getattr(owner, field) != getattr(identity, field):
            raise ValueError("owner readiness approval differs from active run/readiness authority")
    if owner.readiness_evidence_index_v4_sha256 != _sha(
        root / "docs/m2_02a_readiness_evidence_index_v4.yaml"
    ):
        raise ValueError("owner readiness prereview evidence differs")
    if (
        approval.interpretation_document_sha256 != identity.date_pair_interpretation_sha256
        or approval.source_date_correction_approval_sha256
        != identity.date_correction_approval_sha256
    ):
        raise ValueError("date-pair interpretation differs from owner ratification")
    expected_ready = {
        "scientific_schema": f"v{identity.scientific_schema_version}",
        "scientific_digest": identity.scientific_schema_digest,
        "benchmark_schema": f"v{identity.benchmark_schema_version}",
        "benchmark_digest": identity.benchmark_schema_digest,
        "normative_evaluator_sha256": identity.evaluator_sha256,
        "date_correction_approval_sha256": identity.date_correction_approval_sha256,
        "m2_02_approval_sha256": identity.discovery_policy_approval_sha256,
        "readiness_id": "m2-02a-readiness-v3",
        "metric_contract_version": identity.metric_contract_version,
        "critical_field_set_sha256": identity.critical_field_set_sha256,
        "date_pair_interpretation_approval_sha256": (
            identity.date_pair_interpretation_approval_sha256
        ),
        "owner_readiness_approval_sha256": identity.owner_readiness_approval_sha256,
        "owner_readiness_approved": True,
        "annotation_launch_approved": False,
        "annotation_started": False,
        "human_gold_created": False,
        "dropbox_writes_approved": False,
        "parser_work_approved": False,
        "normative_metric_amendment_approved": False,
        "m3_approved": False,
    }
    expected_run = {
        "run_id": "m2-02-v1",
        "status": "readiness_approved_not_launched",
        "owner_readiness_approved": True,
        "owner_readiness_approval_sha256": identity.owner_readiness_approval_sha256,
        "launch_approved": False,
        "annotation_started": False,
        "human_gold_created": False,
        "scientific_schema_version": identity.scientific_schema_version,
        "benchmark_schema_version": identity.benchmark_schema_version,
        "metric_contract_version": identity.metric_contract_version,
        "date_correction_approval_sha256": identity.date_correction_approval_sha256,
        "discovery_approval_sha256": identity.discovery_policy_approval_sha256,
        "critical_field_set_sha256": identity.critical_field_set_sha256,
        "date_pair_interpretation_approval_sha256": (
            identity.date_pair_interpretation_approval_sha256
        ),
    }
    if any(ready.get(k) != v for k, v in expected_ready.items()) or any(
        run.get(k) != v for k, v in expected_run.items()
    ):
        raise ValueError("active annotation run/readiness contract mismatch")
    return identity


def validate_annotation_contract_alignment(identity: AnnotationContractIdentity) -> None:
    identity = AnnotationContractIdentity.model_validate(identity.model_dump())
    if identity != active_annotation_contract():
        raise ValueError("annotation contract differs from active run/readiness authority")
