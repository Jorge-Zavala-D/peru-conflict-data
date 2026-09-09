"""Annotator-neutral readiness package surface."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from peru_conflicts.acquisition.fs_safety import DirectoryLease
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .references import ReferenceSnapshotManifest, sha256, verify_pages

FORM_HEADERS = {
    "discoveries.csv": (
        "discovery_id,report_number,object_family,unit_type,cardinality_index,"
        "start_page,start_line,start_column,end_page,end_line,end_column,section,unresolved,note"
    ),
    "objects.csv": "discovery_id,object_family,cardinality_index",
    "annotations.csv": (
        "discovery_id,object_family,cardinality_index,field_name,state,value_type,"
        "original_value,comment,evidence_id"
    ),
    "evidence.csv": (
        "evidence_id,report_number,page,section,granularity,start_line,start_column,"
        "end_line,end_column,x0,y0,x1,y1,table,row,column,rationale"
    ),
    "inspection.csv": (
        "report_number,object_family,inspection_complete,zero_discoveries_confirmed,comment"
    ),
}

INSTRUCTIONS = b"""# Readiness preview: NOT ISSUED TO HUMANS

This package contains original native reference text and EMPTY forms, not answers.
Do not use machine suggestions or another person's work. No annotation is authorized yet.

Future workflow (after separate launch approval):
1. Read every assigned report page. References use report/page filenames.
2. Use the position helper to display numbered lines. Select a one-based line and
   Unicode character column yourself. Confirm the displayed context. The helper
   verifies location, not whether you chose the correct scientific object start.
3. Add each independently found object to discoveries.csv; local IDs and indexes
   are bookkeeping, never correspondence guesses. Preserve uncertainty in notes.
4. Declare additional object instances in objects.csv. Generate EMPTY field slots
   only after discovery. Never accept prefilled original source values.
5. Enter annotation state, original value and typed evidence using the handbook.
   Use string/number/boolean/json as value_type; blank means no source value.
   Do not replace missing information with zero. Explain ambiguity/uncertainty.
6. Certify every report/object-family inspection explicitly in inspection.csv.
   Empty forms do NOT mean zero objects. Confirm zero discoveries explicitly.
7. Validate without locking. Correct actionable errors and validate again.
8. Only an explicit separately confirmed lock publishes a new immutable payload.
   Lock cannot be edited. Corrections create new IDs and preserve previous bytes.

CSV files are UTF-8, with quoted cells for commas/newlines. Use a spreadsheet editor
that preserves text (including leading zeros and dates) or a plain text CSV editor.
Never execute spreadsheet formulas from source strings. Review saved values before lock.
Evidence choices: span, bounding_box, table_cell, page_only (with rationale).
States: observed, explicit_zero, not_reported, not_applicable, source_ambiguous,
structurally_unavailable, illegible_uninspectable, annotation_uncertain.
No values in this preview are human annotations or gold.
"""

FORM_GUIDE = b"""# Local form guide - readiness demonstration, not launch authority

Start with an empty package. No human annotation is authorized now. After a later
separate launch gate, the coordinator supplies the verified package and original PDF.
Read the original PDF together with the numbered native references. This guide gives
the form syntax; it does not supply answers or tell you where objects begin.

## Commands

Replace PACKAGE with the local package path (quote paths with spaces).
The commands below are COORDINATOR-ONLY readiness demonstrations, not instructions
to give an annotator access to this repository. The repository contains private
benchmark routing/configuration and must NOT be exposed to either human.
Before human issuance a separately reviewed isolated neutral runtime must exclude
repository/configuration/machine-aid access. That launch requirement is not fulfilled here.
The coordinator can rehearse using the repository's existing uv environment:

    uv run python scripts/prepare_m2_annotation.py page PACKAGE --report 260 --page 1
    uv run python scripts/prepare_m2_annotation.py position PACKAGE
        --report 260 --page 1 --line 1 --column 1
    uv run python scripts/prepare_m2_annotation.py slots PACKAGE
    uv run python scripts/prepare_m2_annotation.py inspection-template PACKAGE
    uv run python scripts/prepare_m2_annotation.py validate PACKAGE

Enter the wrapped position example on ONE command line. Commands print output and
do not overwrite forms. The coordinator will provide the
reviewed command environment before any launch. Copy generated CSV text only into a
new blank form, never over saved human work. Validation never locks your work.
The position command displays context for YOUR chosen position, not a recommendation.
Lines are split only on LF. Columns count Unicode characters; offsets/hashes are
calculated for you. End positions are exclusive. Cross-page boundaries are allowed.

## discoveries.csv

Enter your own local discovery_id (letters/digits/hyphens), report_number,
object_family, unit_type, cardinality_index (0,1,2... local bookkeeping), start/end
page/line/column, section, unresolved (true/false), note. Use a stable section label
from the source. No index, name, or code establishes identity with another person's work.
Discovery families: actor, alert, agreement, case_observation, dp_action, demand,
dialogue_event, location, mediation_observation, protest_event, violence_event.
Allowed unit_type values: report (whole report), report_month_aggregate (published
report/month aggregate), case_observation (published case block), case_subobject
(source object inside a case), report_annex_event (standalone annex event),
source_only_object (source object without a justified case link).
Choose the source-appropriate scope. Ask the coordinator about an unrepresentable
unit rather than guessing or changing a contract.
With unresolved=true retain a note and the known metadata; no invented coordinates.
Unresolved rows remain review evidence and cannot silently become zero discoveries.

## objects.csv and empty slots

After discovery, declare additional source instances with discovery_id,
object_family and a nonnegative local cardinality_index. Do not duplicate the
base instance already declared in discoveries.csv. Local indexes need not match
any other person's indexes. Independently inventory repeated rows/events; never
infer a case link, mediation continuity or longitudinal identity from proximity.
Scientific subobjects such as case_reported_indicator can be declared where the
source supports them. No software infers their existence. Declare one or more
case_name instances per complete case; do not select an artificial primary name.
The base case observation owns its single CaseMonth field set, never a repeated row.
Each actor instance owns its case_actor.role_original slot. Each location instance
owns its case_location.relationship_original slot; no separate relational indexes.
Outside a case scope these relation slots are explicitly not_applicable. Within a
case preserve the source-supported relationship or explicitly not_reported.
The slots command outputs field names only for YOUR declared instances, no values.
Repeated objects must have separate slots. Preserve source contradictions.

## annotations.csv

Retain generated discovery_id, object_family, cardinality_index and field_name.
Enter state, value_type, original_value, comment and evidence_id.
States:
- observed: source explicitly provides a value; raw value required.
- explicit_zero: source explicitly states numeric zero; number value 0 required.
- not_reported: inspected source does not report it; no raw value.
- not_applicable: field is inapplicable to this source object; no raw value.
- source_ambiguous: published evidence has competing readings; comment required.
- structurally_unavailable: source structure does not expose the field; no raw value.
- illegible_uninspectable: source cannot be inspected reliably; no raw value.
- annotation_uncertain: human is uncertain about their interpretation; comment required.
Do not collapse these states. Preserve Spanish strings. Never create generated prose
to repair a source. Never replace dashes or missing values with zero.
value_type: string, number, boolean or json. Blank means no source value. Use json
only for a source-supported structured value, not generated content; request assistance
with encoding if needed, without accepting a machine-proposed source reading.

## evidence.csv

Give each evidence row a unique evidence_id. report_number/page/section must match
the declared source unit. The tool obtains exact source/reference hashes itself.
granularity=span: start_line/start_column/end_line/end_column on that page.
granularity=bounding_box: x0/y0/x1/y1 in the PDF's coordinate system.
granularity=table_cell: table, row and column source labels.
granularity=page_only: explicit rationale explaining why whole-page evidence is apt.
Use the appropriate locator, not a guessed one. Every required annotation needs evidence.

## inspection.csv and completion

The inspection-template command lists required report/family coverage, not object
counts. After inspecting, explicitly enter inspection_complete=true and
zero_discoveries_confirmed=true ONLY if you found none; otherwise false.
Do not treat missing files or empty forms as completed inspection. Preserve notes.
Validate repeatedly. An error is not a lock. A future separately confirmed lock is
irreversible: correction requires a new ID preserving the previous payload. No real
lock is available in this readiness demonstration. No values become gold here.
"""


class PackageManifest(StrictModel):
    kind: Literal["NON_CANONICAL_READINESS_PREVIEW"] = "NON_CANONICAL_READINESS_PREVIEW"
    run_id: Literal["m2-02-v1", "synthetic-run"]
    role: Literal["annotator-a", "annotator-b"]
    package_id: Sha256
    references: tuple[ReferenceSnapshotManifest, ...] = Field(min_length=1)
    file_hashes: dict[str, Sha256]


def build_package(
    run_id: Literal["m2-02-v1", "synthetic-run"],
    role: Literal["annotator-a", "annotator-b"],
    snapshots: Sequence[tuple[ReferenceSnapshotManifest, Mapping[int, bytes]]],
) -> dict[str, bytes]:
    files = {name: (header + "\n").encode() for name, header in FORM_HEADERS.items()}
    files["INSTRUCTIONS.md"] = INSTRUCTIONS
    files["FORM_GUIDE.md"] = FORM_GUIDE
    files["DATE_SEMANTICS_ADDENDUM.md"] = (
        Path(__file__).resolve().parents[3] / "docs/m2_01_date_semantics_correction_v1.md"
    ).read_bytes()
    manifests: list[ReferenceSnapshotManifest] = []
    for manifest, pages in sorted(snapshots, key=lambda item: item[0].report_number):
        verify_pages(manifest, pages)
        if any(m.report_number == manifest.report_number for m in manifests):
            raise ValueError("duplicate assigned report")
        manifests.append(manifest)
        for page, data in pages.items():
            files[f"references/{manifest.report_number}/{page:04d}.txt"] = data
    identity = sha256(canonical_json_bytes([run_id, role, [m.snapshot_sha256 for m in manifests]]))
    metadata = PackageManifest(
        run_id=run_id,
        role=role,
        package_id=identity,
        references=tuple(manifests),
        file_hashes={name: sha256(data) for name, data in sorted(files.items())},
    )
    files["PACKAGE_MANIFEST.json"] = canonical_json_bytes(metadata.model_dump(mode="json")) + b"\n"
    return files


def verify_package(files: Mapping[str, bytes], *, allow_drafts: bool = False) -> PackageManifest:
    if "PACKAGE_MANIFEST.json" not in files:
        raise ValueError("package manifest is missing")
    manifest = PackageManifest.model_validate_json(files["PACKAGE_MANIFEST.json"])
    if any(
        f"references/{m.report_number}/{p.page:04d}.txt" not in files
        for m in manifest.references
        for p in m.pages
    ):
        raise ValueError("package reference page is missing")
    snapshots = [
        (m, {p.page: files[f"references/{m.report_number}/{p.page:04d}.txt"] for p in m.pages})
        for m in manifest.references
    ]
    expected = build_package(manifest.run_id, manifest.role, snapshots)
    if set(expected) != set(files):
        raise ValueError("package has missing or unapproved files")
    for name, data in expected.items():
        if allow_drafts and name in FORM_HEADERS:
            continue
        if data != files[name]:
            raise ValueError(f"package bytes changed: {name}")
    return manifest


def assert_equivalent(a: Mapping[str, bytes], b: Mapping[str, bytes]) -> None:
    left, right = verify_package(a), verify_package(b)
    if (
        left.role == right.role
        or left.run_id != right.run_id
        or left.references != right.references
    ):
        raise ValueError("A/B assignments differ or roles are not distinct")
    if {k: v for k, v in a.items() if k != "PACKAGE_MANIFEST.json"} != {
        k: v for k, v in b.items() if k != "PACKAGE_MANIFEST.json"
    }:
        raise ValueError("A/B source, instructions or blank forms differ")


def require_readiness_root(root: Path) -> None:
    logical = root.absolute()
    resolved = root.resolve(strict=True)
    cache = Path(__file__).resolve().parents[3] / ".cache" / "m2-02a1"
    temporary = Path(tempfile.gettempdir()).resolve()
    if logical != resolved or any(parent.is_symlink() for parent in [root, *root.parents]):
        raise ValueError("readiness destination cannot be aliased")
    if not resolved.is_relative_to(cache) and not (
        resolved.is_relative_to(temporary)
        and any(p.startswith("m2-readiness-") for p in resolved.parts)
    ):
        raise ValueError("writes restricted to readiness cache or owned synthetic temporary roots")


def publish_new(root: Path, relative: str, data: bytes) -> None:
    """Exclusive publication in non-production readiness storage; failed evidence is retained."""
    require_readiness_root(root)
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("publication path escapes readiness root")
    with ExitStack() as stack:
        directory = stack.enter_context(DirectoryLease.acquire(root))
        for part in path.parts[:-1]:
            directory = stack.enter_context(directory.acquire_child(part, create=True))
        with directory.open_child_exclusive(path.name) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        directory.sync_directory()
        with directory.open_child_read(path.name) as stream:
            if stream.read() != data:
                raise ValueError("published bytes differ; partial evidence retained")
