"""Draft discovery compatibility helpers; no I/O, annotation launcher, or scoring.

These records demonstrate representability, not human authorship or approval.
Only synthetic callers are authorized until the execution policy is approved.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field, model_validator

from peru_conflicts.benchmark.models import (
    BENCHMARK_OBJECT_TYPES,
    AnnotationUnit,
    AnnotationUnitType,
    PartitionRole,
    derive_annotation_unit_id,
)
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Identifier, Sha256, StrictModel


def _digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class DiscoveryWindow(StrictModel):
    """Whole PDF only: no writable names, sections, case boundaries, or counts."""

    execution_policy_version: Literal["m2-02-execution-policy-v1"] = "m2-02-execution-policy-v1"
    report_number: int = Field(ge=1)
    source_sha256: Sha256
    partition_role: PartitionRole
    page_count: int = Field(ge=1)

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(range(1, self.page_count + 1))

    @property
    def window_id(self) -> str:
        return "discovery-window-" + _digest(self.model_dump(mode="json"))


class SourcePosition(StrictModel):
    """Zero-based Unicode code-point boundary in a frozen, full-page UTF-8 reference."""

    coordinate_policy: Literal["page-native-utf8-lf-codepoint-v1"] = (
        "page-native-utf8-lf-codepoint-v1"
    )
    page: int = Field(ge=1)
    reference_sha256: Sha256
    codepoint_offset: int = Field(ge=0)


def position_from_reference(*, page: int, offset: int, reference: bytes) -> SourcePosition:
    """Validate supplied reference bytes; never extract, normalize, or choose an anchor."""

    text = reference.decode("utf-8", errors="strict")
    if not text or "\r" in text or "\f" in text or text.startswith("\ufeff"):
        raise ValueError("reference must be one nonempty UTF-8 LF page without BOM or form feed")
    if offset > len(text):
        raise ValueError("position is outside the reference page")
    return SourcePosition(
        page=page, reference_sha256=hashlib.sha256(reference).hexdigest(), codepoint_offset=offset
    )


class DiscoveredObject(StrictModel):
    """Execution sidecar declared after discovery, not an annotation or a gold record.

    Start/end reference custody and actual human authorship need later execution
    controls. Model validation cannot establish either from a declaration alone.
    """

    window: DiscoveryWindow
    annotator_id: Identifier
    domain_object_type: Identifier
    unit_type: AnnotationUnitType
    local_index: int = Field(ge=0)
    start: SourcePosition
    end: SourcePosition
    section: Identifier

    @model_validator(mode="after")
    def validate_boundary(self) -> Self:
        if self.domain_object_type not in BENCHMARK_OBJECT_TYPES:
            raise ValueError("unregistered object family")
        if self.domain_object_type == "case_observation":
            if self.unit_type is not AnnotationUnitType.CASE_OBSERVATION:
                raise ValueError("a discovered case must retain case-observation semantics")
        elif self.unit_type not in {
            AnnotationUnitType.REPORT_ANNEX_EVENT,
            AnnotationUnitType.SOURCE_ONLY_OBJECT,
        }:
            raise ValueError("this proof supports only independent annex or source-only objects")
        if (
            self.unit_type is AnnotationUnitType.REPORT_ANNEX_EVENT
            and self.domain_object_type
            not in {
                "protest_event",
                "violence_event",
                "dp_action",
                "alert",
                "agreement",
                "dialogue_event",
            }
        ):
            raise ValueError("non-event objects cannot be represented as annex events")
        if not 1 <= self.start.page <= self.end.page <= self.window.page_count:
            raise ValueError("discovered extent is outside the whole-report assignment")
        if self.start.page == self.end.page:
            if self.start.reference_sha256 != self.end.reference_sha256:
                raise ValueError("one page cannot have conflicting reference snapshots")
            if self.end.codepoint_offset <= self.start.codepoint_offset:
                raise ValueError("discovered extent must be nonempty and forward")
        return self

    @property
    def detection_key(self) -> str:
        """Proposed source-start identity: deliberately excludes end, ordinal, and values."""
        return "discovery-anchor-" + _digest(
            {
                "key_policy": "case_detection_anchor_key_v1",
                "report_number": self.window.report_number,
                "source_sha256": self.window.source_sha256,
                "domain_object_type": self.domain_object_type,
                "start": self.start.model_dump(mode="json"),
            }
        )

    def to_annotation_unit(self) -> AnnotationUnit:
        """Prove existing unit representability; not permission to create real submissions."""
        pages = tuple(range(self.start.page, self.end.page + 1))
        locator = "human-extent-" + _digest(
            {
                "start_key": self.detection_key,
                "end": self.end.model_dump(mode="json"),
                "section": self.section,
            }
        )
        return AnnotationUnit(
            unit_id=derive_annotation_unit_id(
                report_number=self.window.report_number,
                source_sha256=self.window.source_sha256,
                unit_type=self.unit_type,
                pages=pages,
                source_locator=locator,
            ),
            report_id=f"report-{self.window.report_number}",
            report_number=self.window.report_number,
            source_sha256=self.window.source_sha256,
            unit_type=self.unit_type,
            pages=pages,
            source_locator=locator,
            sections=(self.section,),
        )


@dataclass(frozen=True)
class DiscoveryComparison:
    """Unscored correspondence evidence retaining both declarations, including unmatched ones."""

    matched: tuple[tuple[DiscoveredObject, DiscoveredObject], ...]
    boundary_disagreements: tuple[tuple[DiscoveredObject, DiscoveredObject], ...]
    a_only: tuple[DiscoveredObject, ...]
    b_only: tuple[DiscoveredObject, ...]


def compare_discoveries(
    window: DiscoveryWindow,
    annotator_a: str,
    annotator_b: str,
    a: tuple[DiscoveredObject, ...],
    b: tuple[DiscoveredObject, ...],
) -> DiscoveryComparison:
    """Exact correspondence only; no fuzzy resolution, shared-ID rewriting, or metric output."""
    if not annotator_a.strip() or not annotator_b.strip() or annotator_a == annotator_b:
        raise ValueError("distinct nonempty annotator identities are required")
    page_references: dict[int, str] = {}
    for records, annotator in ((a, annotator_a), (b, annotator_b)):
        if any(record.window != window or record.annotator_id != annotator for record in records):
            raise ValueError("discovery assignment or annotator identity differs")
        if len({record.detection_key for record in records}) != len(records):
            raise ValueError("duplicate discovery anchors require explicit review, not collapse")
        for record in records:
            for position in (record.start, record.end):
                previous = page_references.setdefault(position.page, position.reference_sha256)
                if previous != position.reference_sha256:
                    raise ValueError("reference custody differs for the same PDF page")
    left = {record.detection_key: record for record in a}
    right = {record.detection_key: record for record in b}
    matched: list[tuple[DiscoveredObject, DiscoveredObject]] = []
    boundaries: list[tuple[DiscoveredObject, DiscoveredObject]] = []
    for key in sorted(left.keys() & right.keys()):
        pair = left[key], right[key]
        if pair[0].to_annotation_unit() == pair[1].to_annotation_unit():
            matched.append(pair)
        else:
            boundaries.append(pair)
    return DiscoveryComparison(
        matched=tuple(matched),
        boundary_disagreements=tuple(boundaries),
        a_only=tuple(left[key] for key in sorted(left.keys() - right.keys())),
        b_only=tuple(right[key] for key in sorted(right.keys() - left.keys())),
    )
