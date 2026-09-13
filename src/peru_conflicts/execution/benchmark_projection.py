"""Versioned source-slot projection; synthetic representability, not gold authority.

No joins, identity repair, date parsing, I/O, adjudication, or start-key scoring.
Each relational component belongs to the same declared benchmark object instance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from peru_conflicts.benchmark.metrics import (
    OBJECT_MATCH_FIELDS,
    ComparableAnnotation,
)
from peru_conflicts.benchmark.models import (
    BENCHMARK_SCHEMA_VERSION,
    AnnotationSlot,
    AnnotationState,
    EvidenceAnchor,
    EvidenceRequirement,
    FieldAnnotation,
)
from peru_conflicts.models import MODEL_REGISTRY
from peru_conflicts.models.common import SCHEMA_VERSION

from .annotation import ValidatedDraft, validate_forms
from .source_dates import validate_date_pair

SCIENTIFIC_CONTRACT_VERSION = SCHEMA_VERSION
BENCHMARK_CONTRACT_VERSION = BENCHMARK_SCHEMA_VERSION

# Independent closed execution contract. A metric-field addition must not silently
# gain a supplier: it requires a reviewed crosswalk update too.
SOURCE_FIELDS = {
    "actor": ("name_original", "actor_type_original"),
    "location": (
        "location_text_original",
        "department_original",
        "province_original",
        "district_original",
        "population_center_original",
    ),
    "demand": ("text_original", "theme_original", "category_original", "competent_entity_original"),
    "case_observation": (),
    "protest_event": (
        "event_date_original",
        "event_date_precision_original",
        "measure_type_original",
        "actors_text_original",
        "location_text_original",
        "demand_text_original",
    ),
    "violence_event": (
        "event_date_original",
        "event_date_precision_original",
        "violence_type_original",
        "description_original",
        "fatalities_total",
        "injured_total",
        "casualty_components",
    ),
    "dialogue_event": (
        "event_date_original",
        "event_date_precision_original",
        "description_original",
        "status_original",
    ),
    "mediation_observation": (
        "start_date_original",
        "start_date_precision_original",
        "status_original",
        "requester_original",
        "actors_original",
        "mediation_type_original",
        "mediator_original",
        "case_description_original",
        "demands_original",
        "progress_original",
    ),
    "agreement": (
        "agreement_date_original",
        "agreement_date_precision_original",
        "case_description_original",
        "text_original",
        "responsibility_original",
        "deadline_original",
        "compliance_progress_original",
    ),
    "dp_action": (
        "action_date_original",
        "action_date_precision_original",
        "action_type_original",
        "intervention_category_original",
        "intervention_subtype_original",
        "intervention_hierarchy_original",
        "description_original",
    ),
    "alert": (
        "alert_date_original",
        "alert_date_precision_original",
        "alert_type_original",
        "risk_original",
        "location_text_original",
        "text_original",
    ),
}
RELATIONAL_FIELDS = {
    "actor": {"role_original": "case_actor.role_original"},
    "location": {"relationship_original": "case_location.relationship_original"},
}
TECHNICAL_FAMILIES = {"case_observation", "mediation_observation"}


def field_crosswalk() -> dict[str, dict[str, tuple[str, str]]]:
    result: dict[str, dict[str, tuple[str, str]]] = {}
    for family, fields in SOURCE_FIELDS.items():
        suppliers = {f: ("HUMAN_SOURCE_SLOT", f"{family}.{f}") for f in fields}
        suppliers.update(
            {
                f: ("RELATIONAL_COMPONENT_SLOT", slot)
                for f, slot in RELATIONAL_FIELDS.get(family, {}).items()
            }
        )
        if family in TECHNICAL_FAMILIES:
            suppliers["unit_id"] = ("DETERMINISTIC_TECHNICAL_FIELD", "annotation_unit.unit_id")
        result[family] = suppliers
    if set(result) != set(OBJECT_MATCH_FIELDS) or any(
        set(result[family]) != set(fields) for family, fields in OBJECT_MATCH_FIELDS.items()
    ):
        raise ValueError("execution crosswalk differs from benchmark v0.1.1")
    return result


def source_value(annotation: FieldAnnotation) -> Any:
    """Preserve state alongside decoded value; unresolved evidence cannot be finalized."""
    if annotation.state in {
        AnnotationState.SOURCE_AMBIGUOUS,
        AnnotationState.ANNOTATION_UNCERTAIN,
        AnnotationState.ILLEGIBLE_UNINSPECTABLE,
    }:
        raise ValueError("unresolved annotation requires later reviewed adjudication/forensics")
    return json.loads(annotation.raw_value_json) if annotation.raw_value_json is not None else None


@dataclass(frozen=True)
class SyntheticBenchmarkProjection:
    objects: dict[str, list[dict[str, Any]]]
    critical_annotations: tuple[ComparableAnnotation, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]
    evidence: dict[tuple[str, str, str, int], tuple[EvidenceAnchor, ...]]


def project_synthetic_benchmark(draft: ValidatedDraft) -> SyntheticBenchmarkProjection:
    """Invented-data proof only. Does not create a gold record or authorize execution."""
    if draft.package.run_id != "synthetic-run":
        raise ValueError("real human-gold projection is not authorized")
    verified = validate_forms(
        draft.input_files,
        draft.coordinator_partitions,
        expected_package=draft.package,
        require_complete=True,
    )
    if verified != draft or draft.unresolved:
        raise ValueError("draft differs or contains unresolved discoveries")
    crosswalk = field_crosswalk()
    objects: dict[str, list[dict[str, Any]]] = {family: [] for family in crosswalk}
    critical: list[ComparableAnnotation] = []
    requirements: list[EvidenceRequirement] = []
    evidence: dict[tuple[str, str, str, int], tuple[EvidenceAnchor, ...]] = {}
    # Critical membership comes from the unchanged owner-approved 40-field file.
    config = yaml.safe_load(
        (
            Path(__file__).resolve().parents[3] / "config/benchmark/m2_critical_fields_v1.yaml"
        ).read_bytes()
    )
    critical_names = {
        field for group in config["source_value_critical"].values() for field in group["fields"]
    }
    for submission in draft.submissions:
        by_key = {
            (a.domain_object_type, a.cardinality_index, a.field_name): a
            for a in submission.annotations
        }
        for annotation in submission.annotations:
            source_value(annotation)  # No unresolved noncritical value is silently discarded.
            if annotation.field_name in critical_names:
                key = (
                    annotation.unit_id,
                    annotation.domain_object_type,
                    annotation.field_name,
                    annotation.cardinality_index,
                )
                critical.append(
                    ComparableAnnotation(*key, annotation.state, annotation.raw_value_json)
                )
                anchors = annotation.evidence_anchors
                requirements.append(
                    EvidenceRequirement(
                        slot=AnnotationSlot(
                            unit_id=key[0],
                            domain_object_type=key[1],
                            field_name=key[2],
                            cardinality_index=key[3],
                        ),
                        report_id=anchors[0].report_id,
                        report_number=anchors[0].report_number,
                        source_sha256=anchors[0].source_sha256,
                        pages=tuple(sorted({a.page for a in anchors})),
                        sections=tuple(sorted({a.section for a in anchors})),
                        allowed_granularities=tuple(dict.fromkeys(a.granularity for a in anchors)),
                    )
                )
                evidence[key] = anchors
        for instance in submission.object_inventory:
            family = instance.domain_object_type
            if family not in crosswalk:
                continue  # e.g. CaseName is critical-field evidence, not a new object metric.
            supplied = {
                name: by_key[(family, instance.cardinality_index, name)]
                for name in instance.required_field_names
            }
            validate_date_pair(supplied, family)
            item: dict[str, Any] = {}
            for field, (kind, supplier) in crosswalk[family].items():
                if kind == "DETERMINISTIC_TECHNICAL_FIELD":
                    item[field] = submission.unit_id
                    continue
                if supplier not in supplied:
                    raise ValueError(f"missing required source supplier: {family}.{field}")
                value = source_value(supplied[supplier])
                if value is not None:
                    model_name, model_field = supplier.split(".")
                    TypeAdapter(
                        MODEL_REGISTRY[model_name].model_fields[model_field].annotation
                    ).validate_json(json.dumps(value), strict=True)
                item[field] = value
            objects[family].append(item)
    return SyntheticBenchmarkProjection(objects, tuple(critical), tuple(requirements), evidence)
