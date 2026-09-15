"""Shared source-form validation without coordinator routing or draft submissions."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import Field

from peru_conflicts.benchmark.models import (
    BENCHMARK_OBJECT_TYPES,
    AnnotationObjectInstance,
    AnnotationState,
    AnnotationUnitType,
    EvidenceAnchor,
    EvidenceGranularity,
    FieldAnnotation,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models import MODEL_REGISTRY
from peru_conflicts.models.common import Identifier, Sha256, StrictModel

from .compatibility import CASE_SUBORDINATES, require_compatible
from .discovery import DiscoveredObject, DiscoveryWindow, SourcePosition, position_from_reference
from .packages import FORM_HEADERS, PackageManifest, verify_package
from .references import select_position, sha256
from .source_dates import validate_date_pair

RequiredFieldRegistry = Mapping[str, tuple[str, ...]]
PackageVerifier = Callable[[Mapping[str, bytes]], PackageManifest]


def rows(files: Mapping[str, bytes], name: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    reader = csv.DictReader(
        io.StringIO(files[name].decode("utf-8", errors="strict"), newline=""), strict=True
    )
    try:
        if reader.fieldnames != FORM_HEADERS[name].split(","):
            raise ValueError(f"{name}: columns differ from the blank template")
        for index, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{name} row {index}: wrong column count")
            result.append(row)
    except csv.Error as error:
        raise ValueError(f"{name}: malformed CSV quoting") from error
    return result


def _unique(values: list[str], label: str) -> None:
    if any(not value.strip() for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{label}: IDs must be nonempty and unique")


class DiscoveryFormHeader(StrictModel):
    discovery_id: Identifier
    report_number: int = Field(ge=1)
    object_family: Identifier
    unit_type: AnnotationUnitType
    cardinality_index: int = Field(ge=0)
    section: Identifier


def declarations(
    files: Mapping[str, bytes],
    *,
    package_verifier: PackageVerifier | None = None,
) -> tuple[PackageManifest, dict[str, DiscoveredObject], list[dict[str, str]]]:
    manifest = (
        verify_package(files, allow_drafts=True)
        if package_verifier is None
        else package_verifier(files)
    )
    references = {m.report_number: m for m in manifest.references}
    source_rows = rows(files, "discoveries.csv")
    _unique([row["discovery_id"] for row in source_rows], "discovery")
    discovered: dict[str, DiscoveredObject] = {}
    unresolved: list[dict[str, str]] = []
    for row in source_rows:
        report = int(row["report_number"])
        DiscoveryFormHeader(
            discovery_id=row["discovery_id"],
            report_number=report,
            object_family=row["object_family"],
            unit_type=AnnotationUnitType(row["unit_type"]),
            cardinality_index=int(row["cardinality_index"]),
            section=row["section"],
        )
        require_compatible(row["object_family"], AnnotationUnitType(row["unit_type"]))
        if report not in references or row["object_family"] not in BENCHMARK_OBJECT_TYPES:
            raise ValueError("discovery report/object family outside assignment")
        if row["unresolved"] not in {"true", "false"}:
            raise ValueError("unresolved must explicitly be true or false")
        if row["unresolved"] == "true":
            if not row["note"].strip():
                raise ValueError("unresolved discovery needs a note")
            unresolved.append(row)
            continue
        positions: list[SourcePosition] = []
        for side in ("start", "end"):
            page = int(row[f"{side}_page"])
            name = f"references/{report}/{page:04d}.txt"
            if name not in files:
                raise ValueError("discovery reference page missing")
            offset = select_position(
                files[name], line=int(row[f"{side}_line"]), column=int(row[f"{side}_column"])
            )
            positions.append(
                position_from_reference(page=page, offset=offset, reference=files[name])
            )
        m = references[report]
        discovered[row["discovery_id"]] = DiscoveredObject(
            window=DiscoveryWindow(
                report_number=report, source_sha256=m.source_sha256, page_count=m.page_count
            ),
            annotator_id=manifest.role,
            domain_object_type=row["object_family"],
            unit_type=AnnotationUnitType(row["unit_type"]),
            local_index=int(row["cardinality_index"]),
            start=positions[0],
            end=positions[1],
            section=row["section"],
        )
    _unique(
        [
            f"{int(row['report_number'])}/{row['object_family']}/{int(row['cardinality_index'])}"
            for row in source_rows
        ],
        "discovery cardinality",
    )
    _unique(
        [d.detection_key for d in discovered.values()],
        "source start (retain ambiguity, do not repair)",
    )
    return manifest, discovered, unresolved


def required_fields(family: str) -> tuple[str, ...]:
    """Only field names from the approved critical config/scientific registry; no values."""
    config_path = (
        Path(__file__).resolve().parents[3] / "config/benchmark/m2_critical_fields_v1.yaml"
    )
    config = cast(dict[str, Any], yaml.safe_load(config_path.read_bytes()))
    critical = [
        str(field)
        for group in config["source_value_critical"].values()
        for field in group["fields"]
    ]
    if family == "case_observation":
        return tuple(
            sorted(
                field
                for field in critical
                if field.split(".")[0] in {"report", "case", "case_month"}
            )
        )
    # Source-level subobjects such as case-reported indicators are permitted by
    # the frozen scientific/annotation contracts. This does not register a new
    # detection/scoring family or infer that such an object exists.
    allowed = BENCHMARK_OBJECT_TYPES | CASE_SUBORDINATES
    if family not in allowed or family not in MODEL_REGISTRY:
        raise ValueError("unregistered source object family")
    model = MODEL_REGISTRY[family]
    names = {f"{family}.{name}" for name in model.model_fields if name.endswith("_original")}
    names.update(field for field in critical if field.startswith(family + "."))
    # Relational values are fields of THIS human instance, not a second index space.
    if family == "actor":
        names.add("case_actor.role_original")
    if family == "location":
        names.add("case_location.relationship_original")
    if not names:
        raise ValueError("object family has no approved source fields")
    return tuple(sorted(names))


def empty_slots(
    files: Mapping[str, bytes],
    *,
    required_field_registry: RequiredFieldRegistry | None = None,
    package_verifier: PackageVerifier | None = None,
) -> list[dict[str, str]]:
    _, discoveries, _ = declarations(files, package_verifier=package_verifier)
    return _slots(files, discoveries, required_field_registry)


def _slots(
    files: Mapping[str, bytes],
    discoveries: Mapping[str, DiscoveredObject],
    required_field_registry: RequiredFieldRegistry | None,
) -> list[dict[str, str]]:
    inventory = [
        (key, value.domain_object_type, value.local_index) for key, value in discoveries.items()
    ]
    for row in rows(files, "objects.csv"):
        if row["discovery_id"] not in discoveries:
            raise ValueError("object refers to an undeclared discovery")
        parent = discoveries[row["discovery_id"]]
        require_compatible(
            parent.domain_object_type, parent.unit_type, subordinate=row["object_family"]
        )
        inventory.append((row["discovery_id"], row["object_family"], int(row["cardinality_index"])))
    if len(set(inventory)) != len(inventory) or any(index < 0 for _, _, index in inventory):
        raise ValueError("duplicate/invalid object cardinality")
    return [
        dict.fromkeys(FORM_HEADERS["annotations.csv"].split(","), "")
        | {
            "discovery_id": discovery_id,
            "object_family": family,
            "cardinality_index": str(index),
            "field_name": field,
        }
        for discovery_id, family, index in inventory
        for field in _registered_fields(family, required_field_registry)
    ]


def _registered_fields(family: str, registry: RequiredFieldRegistry | None) -> tuple[str, ...]:
    if registry is None:
        return required_fields(family)
    if family not in registry or not registry[family]:
        raise ValueError("object family missing from pinned required-field registry")
    return registry[family]


class NeutralDiscoveryAnnotations(StrictModel):
    """Source fields and declared inventory for one neutral discovery."""

    discovery_id: Identifier
    object_inventory: tuple[AnnotationObjectInstance, ...]
    annotations: tuple[FieldAnnotation, ...]


class NeutralDraft(StrictModel):
    package: PackageManifest
    input_files: dict[str, bytes]
    input_hashes: dict[str, Sha256]
    discoveries: tuple[DiscoveredObject, ...]
    unresolved: tuple[dict[str, str], ...]
    inspections: tuple[dict[str, str], ...]
    records: tuple[NeutralDiscoveryAnnotations, ...]
    complete: bool


def _value(row: dict[str, str]) -> str | None:
    value, kind = row["original_value"], row["value_type"]
    if not kind:
        if value:
            raise ValueError("original value needs an explicit value_type")
        return None
    if kind == "string":
        return json.dumps(value, ensure_ascii=False)
    if kind not in {"number", "boolean", "json"}:
        raise ValueError("value_type must be string, number, boolean or json")
    parsed: object = json.loads(value)
    if kind == "number" and (isinstance(parsed, bool) or not isinstance(parsed, (int, float))):
        raise ValueError("number value_type requires a number")
    if kind == "boolean" and not isinstance(parsed, bool):
        raise ValueError("boolean value_type requires true/false")
    return canonical_json_bytes(parsed).decode()


def _evidence(files: Mapping[str, bytes], manifest: PackageManifest) -> dict[str, EvidenceAnchor]:
    source_rows = rows(files, "evidence.csv")
    _unique([r["evidence_id"] for r in source_rows], "evidence")
    reports = {m.report_number: m for m in manifest.references}
    result: dict[str, EvidenceAnchor] = {}
    for row in source_rows:
        report, page = int(row["report_number"]), int(row["page"])
        name = f"references/{report}/{page:04d}.txt"
        if report not in reports or name not in files:
            raise ValueError("evidence report/page outside frozen reference")
        granularity = EvidenceGranularity(row["granularity"])
        if granularity is EvidenceGranularity.SECTION:
            raise ValueError("critical evidence needs a typed locator, not section alone")
        payload: dict[str, Any] = {
            "report_id": f"report-{report}",
            "report_number": report,
            "source_sha256": reports[report].source_sha256,
            "page": page,
            "section": row["section"],
            "granularity": granularity.value,
        }
        if granularity is EvidenceGranularity.SPAN:
            payload["source_span"] = {
                side: select_position(
                    files[name], line=int(row[f"{side}_line"]), column=int(row[f"{side}_column"])
                )
                for side in ("start", "end")
            }
        elif granularity is EvidenceGranularity.BOUNDING_BOX:
            payload["source_bbox"] = {key: float(row[key]) for key in ("x0", "y0", "x1", "y1")}
        elif granularity is EvidenceGranularity.TABLE_CELL:
            payload.update(
                source_table=row["table"],
                table_row_original=row["row"],
                table_column_original=row["column"],
            )
        elif granularity is EvidenceGranularity.PAGE_ONLY:
            payload["page_only_rationale"] = row["rationale"]
        result[row["evidence_id"]] = EvidenceAnchor.model_validate_json(json.dumps(payload))
    return result


def validate_neutral_forms(
    files: Mapping[str, bytes],
    *,
    expected_package: PackageManifest,
    require_complete: bool = False,
    required_field_registry: RequiredFieldRegistry | None = None,
    package_verifier: PackageVerifier | None = None,
) -> NeutralDraft:
    """Validate with trusted package rules and an optional pinned field registry.

    A supplied verifier must enforce the canonical package-byte verification rules.
    The caller supplies its trusted expected identity separately from the files.
    """
    manifest, discoveries, unresolved = declarations(files, package_verifier=package_verifier)
    if manifest != expected_package:
        raise ValueError("package/source/reference differs from trusted coordinator assignment")
    slots = _slots(files, discoveries, required_field_registry)
    slot_keys = {
        (r["discovery_id"], r["object_family"], r["cardinality_index"], r["field_name"])
        for r in slots
    }
    actual = rows(files, "annotations.csv")
    actual_keys = [
        (r["discovery_id"], r["object_family"], r["cardinality_index"], r["field_name"])
        for r in actual
    ]
    if len(set(actual_keys)) != len(actual_keys) or not set(actual_keys).issubset(slot_keys):
        raise ValueError("extra or duplicate annotation slot")
    evidence = _evidence(files, manifest)
    annotations: dict[str, list[FieldAnnotation]] = {key: [] for key in discoveries}
    for row in actual:
        if not row["state"]:
            if row["original_value"] or row["value_type"] or row["comment"]:
                raise ValueError("entered annotation content requires an explicit state")
            continue
        key = row["discovery_id"]
        unit = discoveries[key].to_annotation_unit()
        if row["evidence_id"] not in evidence:
            raise ValueError("annotation needs an existing evidence_id")
        anchor = evidence[row["evidence_id"]]
        if (
            anchor.report_number != unit.report_number
            or anchor.page not in unit.pages
            or anchor.section not in unit.sections
        ):
            raise ValueError("evidence outside human-declared unit")
        annotations[key].append(
            FieldAnnotation(
                annotation_id="annotation-" + sha256(canonical_json_bytes(row)),
                unit_id=unit.unit_id,
                annotator_id=manifest.role,
                domain_object_type=row["object_family"],
                field_name=row["field_name"],
                state=AnnotationState(row["state"]),
                raw_value_json=_value(row),
                evidence_anchors=(anchor,),
                uncertainty_comment=row["comment"] or None,
                cardinality_index=int(row["cardinality_index"]),
            )
        )
        if (
            row["field_name"] in {"case_actor.role_original", "case_location.relationship_original"}
            and discoveries[key].domain_object_type != "case_observation"
            and row["state"] != "not_applicable"
        ):
            raise ValueError("relational component without case scope must be not_applicable")
    for values in annotations.values():
        groups: dict[tuple[str, int], dict[str, FieldAnnotation]] = {}
        for value in values:
            groups.setdefault((value.domain_object_type, value.cardinality_index), {})[
                value.field_name
            ] = value
        for (family, _), fields in groups.items():
            validate_date_pair(fields, family)
    inspections = rows(files, "inspection.csv")
    expected_inspections = {
        (m.report_number, family) for m in manifest.references for family in BENCHMARK_OBJECT_TYPES
    }
    inspection_keys = [(int(r["report_number"]), r["object_family"]) for r in inspections]
    if len(set(inspection_keys)) != len(inspection_keys) or not set(inspection_keys).issubset(
        expected_inspections
    ):
        raise ValueError("duplicate or unassigned inspection")
    inspection_complete = set(inspection_keys) == expected_inspections
    for row in inspections:
        found = (
            any(
                d.window.report_number == int(row["report_number"])
                and d.domain_object_type == row["object_family"]
                for d in discoveries.values()
            )
            or any(
                u["report_number"] == row["report_number"]
                and u["object_family"] == row["object_family"]
                for u in unresolved
            )
            or any(
                discoveries[s["discovery_id"]].window.report_number == int(row["report_number"])
                and s["object_family"] == row["object_family"]
                for s in slots
            )
        )
        expected_zero = "false" if found else "true"
        if (
            row["inspection_complete"] != "true"
            or row["zero_discoveries_confirmed"] != expected_zero
        ):
            inspection_complete = False
    slot_complete = sum(len(values) for values in annotations.values()) == len(slots)
    complete = inspection_complete and slot_complete
    if require_complete and not complete:
        raise ValueError(
            "inspection incomplete"
            if not inspection_complete
            else "required annotation slot incomplete"
        )
    names_complete = not any(
        discovery.domain_object_type == "case_observation"
        and not any(s["discovery_id"] == key and s["object_family"] == "case_name" for s in slots)
        for key, discovery in discoveries.items()
    )
    complete = complete and names_complete
    if require_complete and not names_complete:
        raise ValueError("complete case requires at least one declared case name instance")
    records: list[NeutralDiscoveryAnnotations] = []
    for key, discovery in discoveries.items():
        unit = discovery.to_annotation_unit()
        inventory: dict[tuple[str, int], list[str]] = {}
        for row in slots:
            if row["discovery_id"] == key:
                inventory.setdefault(
                    (row["object_family"], int(row["cardinality_index"])), []
                ).append(row["field_name"])
        records.append(
            NeutralDiscoveryAnnotations(
                discovery_id=key,
                object_inventory=tuple(
                    AnnotationObjectInstance(
                        unit_id=unit.unit_id,
                        domain_object_type=family,
                        cardinality_index=index,
                        required_field_names=tuple(fields),
                    )
                    for (family, index), fields in inventory.items()
                ),
                annotations=tuple(annotations[key]),
            )
        )
    return NeutralDraft(
        package=manifest,
        input_files=dict(files),
        input_hashes={name: sha256(data) for name, data in sorted(files.items())},
        discoveries=tuple(discoveries.values()),
        unresolved=tuple(unresolved),
        inspections=tuple(inspections),
        records=tuple(records),
        complete=complete,
    )
