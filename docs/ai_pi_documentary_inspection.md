# Source-bound documentary inspection store

`DOCUMENTARY_INSPECTION_STORE_V001` is a bounded importer/reader, not an extractor,
canonical entity model, scientific validator or production dispatch integration.
Its relational contract remains `DOCUMENTARY_SQLITE_PROJECTION_V001`. Product
identity comes from the explicit manifest's `snapshot_version`; it does not
select a report. No private dataset or evidence manifest is distributed in Git.

## Supported boundary and public commands

The only supported view formats are `SOURCE_BOUND_CONTEXT_ATTACHMENT_V001`
(regional category/count/percentage) and `SOURCE_BOUND_CONTEXT_ATTACHMENT_V002`
(priority place/case-description/published-situation), each with three declared
columns. Supply already authorized, frozen, hash-addressed records and attributed
context evidence. Raw PDFs, arbitrary candidates/columns/ontologies, caption
discovery, scientific meaning and source acquisition are outside this component.

From a checkout, use the thin entry point:

```text
python scripts/inspect_documentary.py build manifest.json new.sqlite
python scripts/inspect_documentary.py validate new.sqlite manifest.json --receipt validation.json
python scripts/inspect_documentary.py query new.sqlite units
python scripts/inspect_documentary.py query new.sqlite regional
python scripts/inspect_documentary.py query new.sqlite priority
python scripts/inspect_documentary.py query new.sqlite dependencies
python scripts/inspect_documentary.py query new.sqlite limits
python scripts/inspect_documentary.py query new.sqlite trace --cell <original-hash#pointer>
python scripts/inspect_documentary.py export new.sqlite absent-export-directory
```

An installed package exposes the same commands with
`python -m peru_conflicts.inspection`. The SQL resource is packaged with the
library; no sibling scripts, private runtime imports, working-directory search,
`DATA_ROOT` scan, server, ORM, migration or plugin system is required. Library
entry points are `builder.build_snapshot`, `validation.validate`, `queries.query`
and `exports.export`; path arguments are `pathlib.Path` instances.

The explicit manifest contains:

- `projection_version`: the contract identifier above;
- `snapshot_version`: this new product's nonempty identifier;
- `documents`: entries with `sha256`, explicit JSON `path`, and `purposes`;
- `views`: selected frozen view `sha256`, original `request_sha256`, `label`, and
  optional original document aliases/metadata retained in the manifest;
- `authorship`: import attribution, separate from source annotation/applicability;
- optional `expected_accounting`: declared engineering accounting, not a score.

Document paths may be absolute or relative to the manifest file, never silently
relative to the process working directory. Original manifest content is retained;
resolving a location does not rewrite source addresses. All inputs must be supplied
explicitly. Hashes bind exact JSON bytes; source records use original hash-plus-
JSON-pointer identities, including root/escaped properties and canonical
nonnegative array indices. Required integrity failures fail the build. Optional
unavailable references remain queryable with raw references/reasons; a conflicting
historical record digest is never downgraded to unresolved interpretation.

## Additive construction means a new snapshot

Extension uses a new product and explicit union manifest, writes an absent output,
and never updates the previous SQLite file. Disjoint selected units are preserved
independently even when their page numbers, local row labels, text or TOTAL labels
match. Identical whole-document bytes are stored once; their ordered distinct
purposes and original view references remain traceable. Duplicate selected views
are rejected, not counted twice. Reuse of the same original cell in alternative
views is unsupported and rejected. Incompatible repeated native-word evidence
bindings also fail instead of silently ignoring an INSERT conflict. This is not
general support for overlapping alternative/versioned membership semantics.

Invented A+B tests establish an additive receiving/storage boundary, not unseen-
report performance or permission to access any real source. A future real extension
requires a separately authorized, non-reserved developmental unit, compatible
native representation, losslessly addressed cell/group proposal, attributed
source-bound assertions and scope/exposure metadata. A downloaded PDF alone is
insufficient; missing evidence preparation is not an inherited import.

## Preservation and validation

Original JSON bytes are retained once per full-document digest. Only selected
records and necessary evidence become projected observations; other records in a
shared BLOB are not silently admitted. Full record payloads/unknown properties,
types and presence accompany useful relational joins. Historical record hashes
retain their named algorithm; storage payload digests have a separate name.

Body rows/cells, regional headers, priority heading/ordinal metadata, native words,
ordered membership, geometry/own-text frames, contexts/segments, attributed
assertions, exact qualifier scopes, dependencies and unresolved references remain
separate. Context/qualifier literals are distinct from reconstructed display text.
A qualifier may cite a valid original header outside the caption; it may not move
to an unrelated column. Table, exact-column and reported-organization scopes are
not interchangeable. No PDF/image coordinate transform or source renumbering is
inferred. Native word/frame/source-column binding conflicts are rejected.

Qualifier kinds also obey the established profile-specific targets, independently
of caller-supplied labels. Explicit null targets retain the original unresolved
resolution and have no active cell edge (technical target kind `unresolved`);
malformed non-null scopes fail, rather than being relabelled as uncertainty.
Independent validation resolves scopes from pinned originals, not projected target
columns, and compares all required snapshot metadata with the supplied manifest
and fixed inspection-only restrictions. Validation never sanitizes inspected data.

JSON null, absent property, empty string, numeric zero, Boolean false, unknown,
confirmed_none, reported_empty, absent_field and unreviewed_interpretation remain
distinct. Documentary TOTAL/category roles are not canonical case/event identities.
Inspection stays true; normalization, automatic dispatch, scientific acceptance
and benchmark scoring remain false. Execution authority is not human source review;
matching asserted support is inherited machine-readable evidence, not semantic truth.

The builder enables/verifies foreign keys before a DDL/data transaction, closes a
local DELETE-journal stage, independently validates it and exclusively publishes to
an absent path. No required WAL sidecar or folder-wide transaction is promised.
Rollback/incomplete-stage and partial-copy/output failures are reported honestly;
existing outputs are never overwritten. The validator does not import/call the
builder and checks both SQLite integrity and foreign keys plus byte/semantic
round trips. Optimized Python is explicitly rejected by build/validation before
successful-validation claims; their assertion checks cannot silently disappear.

Read-only query/export opens mode=ro, enables query-only mode, closes connections
and enforces before/after file hashes with explicit exceptions even under `-O`.
Unit order comes from the manifest; source rows/cells/segments use stored ordinal
order, including ordered multi-segment concatenation. Evidence traces deliberately
fan out; ordinary body views do not. HTML escaping/newline rendering is display
syntax; UTF-8 CSV is a convenience export, not the sole provenance record. Contexts
and original addresses remain visible when several units share a layout profile.
The legacy query field names `introduction_literal` and `caption_literal` retain
ordered segment literals joined with a display newline; that joining is not a
claim of one contiguous source quote. Individual exact spans/literals remain in
`segments` and its original addressed payloads.

Scientific schema, metric policy, canonical Parquet/DuckDB, B1FIX, ownership and
no-dispatch decisions are unchanged. Repository tests qualify engineering
preservation and portability, not source coverage, independent scientific
validation, human review, milestone completion or release readiness.
