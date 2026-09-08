# M2-02 annotation execution protocol — readiness candidate

Implementation is authorized; production readiness and human launch are **not approved**.
No human is assigned, no package is issued, and no human submission or gold exists.
The owner-approved discovery policy remains unchanged. This execution candidate does
not implement parser scoring or approve M3. Fifteen separate readiness decisions
remain for Jorge; readiness approval would still not authorize annotation launch.

## Custody and central references

The coordinator run config pins reports 260–269, their exact PDF SHA-256 values and
1,128 pages. Reports 261/263 retain `unresolved_opaque_filename`. References are not
semantic extraction, object inventories, or annotations. The PDF remains authoritative.

The native extractor reads an owned system-temporary PDF snapshot copied from a
retained read-only source handle. The source hash is checked before extraction and
again before releasing custody. The snapshot is removed on context exit, including
failure. Neither protected source nor Dropbox receives a write. Extractor binaries,
versions, single-page options, encoding and Unicode policy are pinned. Real extraction
is a workstation-only readiness audit; CI uses a fake process and invented text.

Compare `-raw` and `-layout` structurally on all ten reports. The selected mode remains
an owner-review proposal. UTF-8 is strict, LF is required, no form feed/BOM or Unicode
normalization is introduced. Empty native pages remain explicit empty references;
they cannot supply fabricated character positions. A human may preserve an unresolved
declaration and explain why no legitimate start can be anchored.

Each report manifest binds source SHA, extraction-policy fingerprint, coordinate
policy, page count, and every page's SHA/bytes/codepoints. Generate twice centrally
and require byte equality. A/B receive identical frozen bytes; independent regeneration
on their computers is prohibited. Cross-platform extractor reproduction is not claimed.
The complete package manifest must be verified against the coordinator-held expected manifest,
not treated as a self-authenticating file supplied by an annotator.

## Human eligibility and separation

Future launch requires a private coordinator attestation of two distinct humans,
unexposed to machine review aids, predictions/prefill, one another's answers, and
benchmark partition labels. `EligibilityAttestation` is an assertion contract, not
automatic proof of history, authorship or permission. No real attestation is filled
here. Names, personnel details and exposure histories must never enter Git.

Only four neutral fields define a `DiscoveryWindow`: policy version, report number,
source SHA and page count. Partition is coordinator-only. A and B get separate
package roots and separate submission roots. The coordinator wrapper must never be
distributed with either package. Identical source text may contain ordinary words
also used in benchmark terminology; source content is not a machine answer or role label.

The software does not configure ACLs or make a same-user filesystem hostile-proof.
Before launch the coordinator must verify private shares/accounts: A cannot list/read
B's root or coordinator storage; B cannot list/read A's root or coordinator storage.
The CLI has no comparison command on the human surface. Comparison is coordinator-only
and requires both current sealed payloads. Instructional promises alone are insufficient.

## Human-operable package

Each package contains `PACKAGE_MANIFEST.json`, `INSTRUCTIONS.md`, `FORM_GUIDE.md`, `references/`, and
five CSV forms: discoveries, objects, annotations, evidence and inspection.
All CSVs initially contain headers only. There are no source answers or precreated
case units. The role and opaque package ID are the only A/B-specific differences.

The following repository commands are **coordinator-only readiness demonstrations**,
not launch authorization. The repository contains private partition metadata and must
not be exposed to blind annotators. Future launch requires an isolated neutral runtime
without coordinator config, machine aids or other annotators' data. `PACKAGE` below
denotes an unissued local readiness preview.

```text
uv run python scripts/prepare_m2_annotation.py page PACKAGE --report 260 --page 1
uv run python scripts/prepare_m2_annotation.py position PACKAGE --report 260 --page 1 --line 3 --column 7
uv run python scripts/prepare_m2_annotation.py slots PACKAGE
uv run python scripts/prepare_m2_annotation.py inspection-template PACKAGE
uv run python scripts/prepare_m2_annotation.py validate PACKAGE
```

The helper prints numbered native text and context for the human-selected line/column.
Columns count Unicode characters, not UTF-8 bytes or UTF-16 units. It computes the
hash/offset; the human does not type hashes. Verify the displayed context before
recording the selection. A valid coordinate is **not** proof of the correct scientific
start. The helper never suggests starts, searches for cases, or repairs correspondence.

Use a text-preserving CSV editor. Do not execute formulas, auto-convert identifiers,
dates or leading zeros, or silently alter Spanish strings. Quote commas/newlines.
Save UTF-8. The validator checks the exact header and rejects unknown columns/files.
The local CLI prints output; it does not overwrite any form or lock a submission.
Copy a blank generated slot/inspection template only after checking its destination;
never overwrite previously entered work to regenerate slots.

## Phase 1: independent discovery

Read all assigned source pages. In `discoveries.csv` enter a local ID, report,
registered discovery family, unit type, local index, start/end page and line/column,
section, and explicit `unresolved` true/false plus a note where needed.
Local indexes are bookkeeping, not cross-human identity. Duplicate starts fail;
retain ambiguity explicitly instead of adding fabricated suffixes or coordinate offsets.

For an unanchorable object, set `unresolved=true` and give a substantive note. The
original row is retained. It creates no fabricated AnnotationUnit or detection key.
It counts as a discovery for inspection certification, never as zero. M2-03 reviews
these unresolved declarations alongside matched/boundary/unmatched evidence.

## Phase 2: object inventory and annotation

Only human declarations produce empty slots. A case observation receives its
approved report/case/name/month fields, not an invented violence, location or mediation
instance. Declare repeated source objects explicitly in `objects.csv`, linked to
the local discovery ID. Scientific subobjects such as case-reported indicators may
have their own local cardinalities; this does not add a normative detection family.
Names come from frozen scientific fields and the critical-field config, never PDF inference.

Fill every generated slot with one approved state: observed, explicit_zero,
not_reported, not_applicable, source_ambiguous, structurally_unavailable,
illegible_uninspectable or annotation_uncertain. Original values are entered only
by humans after future launch. `value_type` is string/number/boolean/json; blank
means no source value. Empty is never zero. Ambiguous/uncertain states require a
comment. State/value semantics use the existing frozen `FieldAnnotation` validator.

`evidence.csv` binds report/source SHA (computed from the assigned package), page,
section and a typed locator: span uses line/column bounds converted to codepoints;
bounding_box uses x0/y0/x1/y1; table_cell uses exact table/row/column labels; page_only
requires rationale. Evidence must reference an existing assigned page within the
declared unit and section. No parser/evaluator change is involved.

For each assigned report and registered discovery family, certify
`inspection_complete=true`. If no discovery exists, explicitly confirm
`zero_discoveries_confirmed=true`; otherwise use false. Missing rows, blank tables
and interrupted sessions cannot constitute a completed zero.

## Validation, locks and correction

Draft validation is non-publishing and never locks automatically. Coordinator import
uses privately held package/routing metadata; humans do not see partition fields.
Errors identify missing inspection, required slot, invalid state/evidence, unknown
reference or duplicate identifier. Fix the draft and revalidate.

Current executable locking is **synthetic-only** and rejects the real `m2-02-v1` run.
Real launch remains disabled. The synthetic API requires explicit confirmation,
revalidates every original input byte and completeness, and acquires an exclusive
publication lock. It writes a new canonical payload and then its SHA receipt using
no-replace primitives, fsyncs and rereads them. Failed/partial evidence is retained;
do not treat a directory without a valid receipt as a lock or auto-delete it.

The lifecycle is draft → validated → separately confirmed → locked. There is no
edit/overwrite API for locks. Changed bytes are detected on every read; filesystem
access alone is not immutability. A correction must use a new lock ID and explicit
current-parent SHA. Old bytes remain. A second independent current branch of the
same package history is rejected. Changed unit boundaries remain in package-level
supersession evidence, not falsely paired by a local ordinal.

## Coordinator comparison and held-out sealing

Supply separate A/B locked roots to `compare_locked`. It rejects absent, corrupted,
same-role, superseded or source/routing-mismatched inputs. It reuses the owner-approved
exact correspondence algorithm and returns exact matches, boundary disagreements,
A-only and B-only. Unresolved original declarations remain in the sealed inputs and
must accompany M2-03 review. No adjudication, fuzzy matching, parser score or gold is emitted.

Proposed external structure (not created):

```text
06_validation/m2_benchmark/annotation_runs/m2-02-v1/
  coordinator/                 private assignments, attestations, comparisons, receipts
  reference_snapshot/          centrally frozen immutable bytes
  packages/annotator-a/         A-only
  packages/annotator-b/         B-only
  submissions/annotator-a/      A/coordinator only
  submissions/annotator-b/      B/coordinator only
  coordinator/sealed/           held-out labels; never parser-development accessible
```

No annotator-visible pathname contains a partition label. Routing for 261/263/265/267
is coordinator-only sealed after lock. All current routes prohibit development visibility;
future approved development work may separately expose only the permitted partition.
M3 and discovery-start scoring still require their separate owner approvals.

## Readiness evidence and remaining owner boundary

Real native references and blank packages stay in ignored `.cache/m2-02a1/`; no real
forms are completed. Synthetic references and responses are explicitly invented.
The owner packet binds exact configs, frozen authority, preview hashes, rehearsal,
Git/CI and principal review. All fifteen readiness decisions remain null. Nothing in
this document grants production readiness, human launch or Dropbox write authority.
