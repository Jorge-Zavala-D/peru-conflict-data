"""Human-form validation and synthetic-only immutable lifecycle."""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import AwareDatetime, Field

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.benchmark.models import (
    BENCHMARK_OBJECT_TYPES,
    AnnotationObjectInstance,
    AnnotationState,
    AnnotationUnitType,
    AnnotatorSubmission,
    EvidenceAnchor,
    EvidenceGranularity,
    FieldAnnotation,
    PartitionRole,
    SubmissionStatus,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models import MODEL_REGISTRY
from peru_conflicts.models.common import Identifier, Sha256, StrictModel

from .discovery import (
    DiscoveredObject,
    DiscoveryComparison,
    DiscoveryWindow,
    SourcePosition,
    compare_discoveries,
    position_from_reference,
)
from .packages import (
    FORM_HEADERS,
    PackageManifest,
    publish_new,
    require_readiness_root,
    verify_package,
)
from .references import select_position, sha256


def rows(files: Mapping[str, bytes], name: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(files[name].decode("utf-8", errors="strict"), newline=""))
    if reader.fieldnames != FORM_HEADERS[name].split(","):
        raise ValueError(f"{name}: columns differ from the blank template")
    result: list[dict[str, str]] = []
    for index, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{name} row {index}: wrong column count")
        result.append(row)
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
) -> tuple[PackageManifest, dict[str, DiscoveredObject], list[dict[str, str]]]:
    manifest = verify_package(files, allow_drafts=True)
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
                if field.split(".")[0] in {"report", "case", "case_name", "case_month"}
            )
        )
    # Source-level subobjects such as case-reported indicators are permitted by
    # the frozen scientific/annotation contracts. This does not register a new
    # detection/scoring family or infer that such an object exists.
    allowed = BENCHMARK_OBJECT_TYPES | {field.split(".")[0] for field in critical}
    if family not in allowed or family not in MODEL_REGISTRY:
        raise ValueError("unregistered source object family")
    model = MODEL_REGISTRY[family]
    names = {f"{family}.{name}" for name in model.model_fields if name.endswith("_original")}
    names.update(field for field in critical if field.startswith(family + "."))
    if not names:
        raise ValueError("object family has no approved source fields")
    return tuple(sorted(names))


def empty_slots(files: Mapping[str, bytes]) -> list[dict[str, str]]:
    _, discoveries, _ = declarations(files)
    inventory = [
        (key, value.domain_object_type, value.local_index) for key, value in discoveries.items()
    ]
    for row in rows(files, "objects.csv"):
        if row["discovery_id"] not in discoveries:
            raise ValueError("object refers to an undeclared discovery")
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
        for field in required_fields(family)
    ]


class ValidatedDraft(StrictModel):
    package: PackageManifest
    input_files: dict[str, bytes]
    coordinator_partitions: dict[int, PartitionRole]
    input_hashes: dict[str, Sha256]
    discoveries: tuple[DiscoveredObject, ...]
    unresolved: tuple[dict[str, str], ...]
    inspections: tuple[dict[str, str], ...]
    submissions: tuple[AnnotatorSubmission, ...]
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


def validate_forms(
    files: Mapping[str, bytes],
    partitions: Mapping[int, PartitionRole],
    *,
    expected_package: PackageManifest,
    require_complete: bool = False,
) -> ValidatedDraft:
    manifest, discoveries, unresolved = declarations(files)
    if manifest != expected_package:
        raise ValueError("package/source/reference differs from trusted coordinator assignment")
    if set(partitions) != {m.report_number for m in manifest.references}:
        raise ValueError("coordinator routing differs from assignment")
    slots = empty_slots(files)
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
        found = any(
            d.window.report_number == int(row["report_number"])
            and d.domain_object_type == row["object_family"]
            for d in discoveries.values()
        ) or any(
            u["report_number"] == row["report_number"]
            and u["object_family"] == row["object_family"]
            for u in unresolved
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
    submissions: list[AnnotatorSubmission] = []
    for key, discovery in discoveries.items():
        unit = discovery.to_annotation_unit()
        inventory: dict[tuple[str, int], list[str]] = {}
        for row in slots:
            if row["discovery_id"] == key:
                inventory.setdefault(
                    (row["object_family"], int(row["cardinality_index"])), []
                ).append(row["field_name"])
        submissions.append(
            AnnotatorSubmission(
                submission_id="draft-" + sha256(canonical_json_bytes([manifest.package_id, key])),
                annotator_id=manifest.role,
                unit_id=unit.unit_id,
                partition_role=partitions[unit.report_number],
                status=SubmissionStatus.DRAFT,
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
    return ValidatedDraft(
        package=manifest,
        input_files=dict(files),
        coordinator_partitions=dict(partitions),
        input_hashes={name: sha256(data) for name, data in sorted(files.items())},
        discoveries=tuple(discoveries.values()),
        unresolved=tuple(unresolved),
        inspections=tuple(inspections),
        submissions=tuple(submissions),
        complete=complete,
    )


class SyntheticLock(StrictModel):
    kind: Literal["SYNTHETIC_EXECUTION_PROOF_NOT_HUMAN_SUBMISSION"] = (
        "SYNTHETIC_EXECUTION_PROOF_NOT_HUMAN_SUBMISSION"
    )
    lock_id: str
    locked_at: AwareDatetime
    supersedes: Sha256 | None = None
    draft: ValidatedDraft
    locked_submissions: tuple[AnnotatorSubmission, ...]


def read_locked(root: Path, digest: str) -> SyntheticLock:
    require_readiness_root(root)
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("lock identity must be exact SHA-256")
    with DirectoryLease.acquire(root) as parent, parent.acquire_child(digest) as directory:
        with directory.open_child_read("payload.json") as stream:
            data = stream.read()
        with directory.open_child_read("receipt.sha256") as stream:
            seal = stream.read()
    if sha256(data) != digest or seal != (digest + "\n").encode():
        raise ValueError("locked payload changed or publication incomplete")
    return SyntheticLock.model_validate_json(data)


def _history(root: Path) -> dict[str, SyntheticLock]:
    require_readiness_root(root)
    return {
        path.name: read_locked(root, path.name)
        for path in sorted(root.iterdir())
        if path.name != ".publication.lock"
    }


@contextmanager
def _publication_guard(root: Path) -> Generator[None]:
    require_readiness_root(root)
    with DirectoryLease.acquire(root) as parent:
        stream = parent.open_child_exclusive(".publication.lock")
        try:
            stream.write(b"synthetic publication in progress\n")
            stream.flush()
            os.fsync(stream.fileno())
            yield
        finally:
            stream.close()
            parent.unlink_child(".publication.lock")


def lock_synthetic(
    root: Path,
    draft: ValidatedDraft,
    lock_id: str,
    locked_at: datetime,
    *,
    expected_package: PackageManifest,
    confirmed: bool,
    supersedes: str | None = None,
) -> str:
    if draft.package != expected_package:
        raise ValueError("lock differs from trusted coordinator assignment")
    with _publication_guard(root):
        return _lock_synthetic(
            root, draft, lock_id, locked_at, confirmed=confirmed, supersedes=supersedes
        )


def _lock_synthetic(
    root: Path,
    draft: ValidatedDraft,
    lock_id: str,
    locked_at: datetime,
    *,
    confirmed: bool,
    supersedes: str | None,
) -> str:
    if not confirmed or not draft.complete:
        raise ValueError("explicit completion confirmation and complete validation required")
    if draft.package.run_id != "synthetic-run":
        raise ValueError("real annotation launch is not approved; synthetic rehearsal only")
    verified = validate_forms(
        draft.input_files,
        draft.coordinator_partitions,
        expected_package=draft.package,
        require_complete=True,
    )
    if verified != draft:
        raise ValueError("validated draft differs from freshly verified input bytes")
    history = _history(root)
    if any(record.lock_id == lock_id for record in history.values()):
        raise ValueError("lock ID already published; overwrite prohibited")
    if supersedes is None and any(r.draft.package == draft.package for r in history.values()):
        raise ValueError("existing package lock requires explicit supersession")
    if supersedes is not None:
        if supersedes not in history or any(r.supersedes == supersedes for r in history.values()):
            raise ValueError("supersession needs preserved current parent")
        parent = history[supersedes]
        if parent.draft.package != draft.package:
            raise ValueError("supersession cannot change package/run/role")
    locked = tuple(
        AnnotatorSubmission.model_validate_json(
            json.dumps(
                s.model_dump(mode="json")
                | {
                    "status": "locked",
                    "locked_at": locked_at.isoformat(),
                    "submission_id": lock_id + "-" + str(index),
                    "supersedes_submission_id": None
                    if supersedes is None
                    else next(
                        (
                            p.submission_id
                            for p in history[supersedes].locked_submissions
                            if p.unit_id == s.unit_id
                        ),
                        None,
                    ),
                }
            )
        )
        for index, s in enumerate(draft.submissions)
    )
    record = SyntheticLock(
        lock_id=lock_id,
        locked_at=locked_at,
        supersedes=supersedes,
        draft=draft,
        locked_submissions=locked,
    )
    data = canonical_json_bytes(record.model_dump(mode="json")) + b"\n"
    digest = sha256(data)
    publish_new(root, f"{digest}/payload.json", data)
    publish_new(root, f"{digest}/receipt.sha256", (digest + "\n").encode())
    read_locked(root, digest)
    return digest


def compare_locked(
    root: Path, a: str, b: str, *, right_root: Path | None = None
) -> dict[int, DiscoveryComparison]:
    roots = sorted({root.resolve(), (right_root or root).resolve()})
    with ExitStack() as stack:
        for directory in roots:
            stack.enter_context(_publication_guard(directory))
        return _compare_locked(root, a, b, right_root=right_root)


def _compare_locked(
    root: Path, a: str, b: str, *, right_root: Path | None = None
) -> dict[int, DiscoveryComparison]:
    history = _history(root)
    right_history = history if right_root is None else _history(right_root)
    if a not in history or b not in right_history:
        raise ValueError("comparison requires two published locks")
    if any(record.supersedes in {a, b} for record in (*history.values(), *right_history.values())):
        raise ValueError("comparison input is superseded")
    left, right = history[a].draft, right_history[b].draft
    if (
        left.package.role != "annotator-a"
        or right.package.role != "annotator-b"
        or left.package.references != right.package.references
        or left.coordinator_partitions != right.coordinator_partitions
    ):
        raise ValueError("comparison requires distinct A/B roles with identical source references")
    return {
        m.report_number: compare_discoveries(
            DiscoveryWindow(
                report_number=m.report_number,
                source_sha256=m.source_sha256,
                page_count=m.page_count,
            ),
            left.package.role,
            right.package.role,
            tuple(d for d in left.discoveries if d.window.report_number == m.report_number),
            tuple(d for d in right.discoveries if d.window.report_number == m.report_number),
        )
        for m in left.package.references
    }
