# Bounded report-264 execution guards

`execution.ai_pi_batch` adds a separate execution schema and synthetic tests for
the owner's report-264 Batch 1 scope. Scientific schema 0.3.1, metric contract
0.1.1 and ordinary `EvidenceAnchor`/`validate_candidate` restrictions are unchanged.
This module opens no source PDF and dispatches no model.

The exact source is SHA-256
`5d7e9a506d402915d994456fb9a69e371788613e583d8a215975705c7cad0ddd`,
4,539,029 bytes and 104 physical pages. Allowed physical pages are 1–18, 35–41,
83–86 and 100: exactly 30 distinct pages including all context and continuation.
Any required page outside those ranges stops the batch. The ceilings are eight
packets, 20 tasks including retries, four hours of wall time, 180 PI review minutes
and zero external spend. Token usage may remain `UNOBSERVED`.

`BatchEnvelope` requires an explicit owner instruction ID, absolute source/data/
output paths, actual executable hashes, all three native PDF tool identities,
resource hash, implementation commit/tree, configuration identity and repository
root. `verify_envelope` compares these against independently supplied identities
and checks tool/resource bytes; it never lets stale PDF metadata amend the source
pin. `verify_source_identity` accepts fresh observations from the caller and
requires their exact agreement with the pinned hash, size and physical page count.
The retained source may live in the separately authorized technical evidence
directory; no acquisition or copying into `01_raw` is required. Its exact absolute
path must match the independently supplied authorization. Source paths inside Git
or this batch's output directory are rejected.
The caller must supply prospective cumulative usage to `require_budget` before
each new operation. Defaults are ceilings, not authority to dispatch.

The only output destination is the independently specified existing external data
root followed by
`06_validation/ai_pi_reconstruction/development/report-264/batch-001`.
`prepare_output_root` requires that the batch directory be absent. JSON and retained
raw-text writes use exclusive creation, flush and file fsync. They never replace
existing artifacts; traversal, alternate streams, unsafe Windows names, canonical
file types and outside-root destinations are rejected. A failed partial write
remains a failed retained artifact; no automatic overwrite, deletion or repair is
provided. These checks do not claim protection against a privileged process
concurrently changing filesystem paths.

`freeze_then_normalize` writes original response bytes before invoking a normalizer.
It preserves those bytes even if normalization fails. `freeze_initial_candidate`
binds the candidate to the retained raw hash and freezes its initial version once.
Corrections require separately named append-only versions; the original file is
never edited. `MachineCandidate` has a literal machine origin, internal-draft use,
existing `FieldAnnotation`s or unresolved partial fields, typed object candidates
and evidence-bound relationships. Optional normalized fields are separate from
literal originals. No confidence score, PI decision or accuracy claim is created.

`WorkerPacket` and `SourceFirstPacket` allow only exact source identity, source
units, batch/packet bindings and fixed neutral instructions. Extra audit IDs,
labels, expected answers, candidate answers and PI content fail validation.
`source_first_input` rejects every path except the pinned source PDF and validates
unit boundaries. This is a procedural input boundary; it cannot make an already
exposed reader independent or restrict its operating-system access.

`ReportContextAssociation` is a separately typed `SAME_REPORT` relation only for
`report.report_number` and `report.reference_period`. It binds the context source
unit, target unit/report, exact report/hash/physical page and an original quote with
a span or bounding box. The context validator checks source/target identity and
reference evidence. It does not widen ordinary annotation boundaries or validate
a date normalization scientifically. Partial candidates remain unresolved.

Coverage distinguishes `unprocessed`, `machine_empty_unverified` and
`machine_candidate_present`. An empty response establishes no absence and unknown
casualties or other unprocessed values remain null. Mechanical validation returns
incompleteness issues; it does not certify source completeness, PI review, a
reference denominator, population accuracy, regime qualification or release.

The additive generated schema is `schemas/execution/report264_batch1_v1.json`.
The ordinary `scripts/export_schemas.py --check` includes it without changing any
scientific, metric or historical execution schema.
