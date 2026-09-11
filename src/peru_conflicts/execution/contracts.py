"""Read-only active annotation custody; never execution or annotation authority."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml

from peru_conflicts.benchmark.metrics import CURRENT_BENCHMARK_METRIC_CONTRACT_VERSION
from peru_conflicts.benchmark.models import BENCHMARK_SCHEMA_VERSION
from peru_conflicts.models.common import SCHEMA_VERSION, Sha256, StrictModel

ROOT = Path(__file__).resolve().parents[3]


class AnnotationContractIdentity(StrictModel):
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_digest(path: Path) -> str:
    return hashlib.sha256(
        "\n".join(f"{p.name}:{_sha(p)}" for p in sorted(path.glob("*.schema.json"))).encode()
    ).hexdigest()


def active_annotation_contract(root: Path = ROOT) -> AnnotationContractIdentity:
    """Re-read authoritative bytes on every boundary; never cache a mutable trust anchor."""
    config = root / "config/benchmark"
    ready = yaml.safe_load((config / "m2_02a_readiness_v2.yaml").read_bytes())
    run = yaml.safe_load((config / "m2_02_annotation_run_v1.yaml").read_bytes())
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
    )
    expected_ready = {
        "scientific_schema": f"v{identity.scientific_schema_version}",
        "scientific_digest": identity.scientific_schema_digest,
        "benchmark_schema": f"v{identity.benchmark_schema_version}",
        "benchmark_digest": identity.benchmark_schema_digest,
        "normative_evaluator_sha256": identity.evaluator_sha256,
        "date_correction_approval_sha256": identity.date_correction_approval_sha256,
        "m2_02_approval_sha256": identity.discovery_policy_approval_sha256,
    }
    expected_run = {
        "run_id": "m2-02-v1",
        "scientific_schema_version": identity.scientific_schema_version,
        "benchmark_schema_version": identity.benchmark_schema_version,
        "metric_contract_version": identity.metric_contract_version,
        "date_correction_approval_sha256": identity.date_correction_approval_sha256,
        "discovery_approval_sha256": identity.discovery_policy_approval_sha256,
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
