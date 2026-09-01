# M1-04A corpus-manifest reconciliation design

## Status and boundary

M1-04A consumes the frozen M1-02 discovery runs and the completed, spent
M1-03B.2 operational ledger. It makes no network request, performs no raw write,
does not parse PDF content, and does not claim final corpus completeness. Candidate
JSON/JSONL products remain under a caller-provided ignored cache directory until a
later human review authorizes canonical materialization.

The technical manifest contract is independently versioned as `manifest/v0.1.0`.
It does not change scientific schema `v0.2.0` or the discovery/acquisition snapshots.

## Evidence hierarchy

1. Qualifying document-visible or official-metadata identity evidence establishes an
   observed report number or reference month.
2. An observed report identity requires a qualifying number/month pair. Sequence
   expectations, filenames, URL slugs, and embedded PDF metadata cannot create or
   overwrite an identity.
3. Exact SHA-256 equality may establish byte identity. URL similarity or a shared
   report association cannot.
4. Source-original text, spelling, capitalization, dates, descriptions, hosts, and
   URLs remain unchanged in source-observation records.
5. Research coverage expectations and unnumbered historical leads remain gaps or
   observations, never manufactured report rows.

## Input contract

The materializer requires two explicit frozen discovery run directories. Each run is
validated against its reviewed run ID and the exact size and SHA-256 of
`records.jsonl`, `requests.jsonl`, and `summary.json`. Every discovery record is
strictly revalidated as discovery `v0.3.0`.

Repeated deterministic discovery record IDs in different runs are not collapsed.
The run ID qualifies each capture occurrence, preserving the definitive traversal and
targeted supplement as separate provenance. Conflicting mappings are evaluated across
all occurrences.

The Dropbox input is resolved through `CONFLICT_DATA_ROOT`. The namespace marker,
authorization-use index, deterministic ledger, lock, and ten protected PDFs are opened
read-only, hash-validated, and checked against the completed run graph. The only valid
terminal is `completed / all_ten_remote_bytes_identical` for run
`m103b-1dff6ef0b40dec88e4382932a8c5cf48`.

## Record families

### Corpus report manifest entry

One row represents one observed, qualifying numbered identity. It retains the
report/month mapping, all source-original titles with provenance, all contributing
discovery/evidence/source-observation references, acquisition state, byte-version
count, protected local reference when present, review state, gap references, input
fingerprints, and capture run IDs.

### Source observation record

One row represents one URL observation in one discovery-record occurrence in one run.
This preserves catalogue, search, thematic, landing, and direct-download multiplicity,
including repeated captures. Original and normalized transport URLs are separate;
normalization never merges apex and `www` hosts.

### Byte-version record

One row represents one actual SHA-256 byte object. M1-04A creates these rows only for
reports 260–269. Each row binds the protected relative path, bytes, SHA-256, live-run
evidence, association status, disposition, and spent authorization.

### Version/source relationship edge

Edges distinguish exact byte equality, multiple official URLs for one observed
identity, candidate same-report relations without byte evidence, different bytes
requiring review, and unresolved relations. Edge validators prevent URL relations from
asserting byte identity. The completed run contributes ten exact-byte edges; discovery
relations remain pre-hash candidate evidence.

### Gap-register entry

Gaps represent unresolved research expectations or evidence limitations. M1-04A
generates separate rows for the 21 expected months from 2004-04 through 2005-12, report
numbers 1–22, the 2004 and 2005 unnumbered leads, reports without byte acquisition,
261/263 opaque direct-file association, and distinct direct-file URL sets whose byte
equivalence is unknown. No gap row creates a report identity.

### Coverage report and receipt

The coverage report calculates observed ranges, counts, conflicts, gap classes, byte
closure, and candidate status from the candidate records. Its status is always
`candidate_requires_human_review` in M1-04A. The materialization receipt pins every
input/output artifact, implementation commit, schema version, record count, sort rule,
and safety assertion.

## Deterministic reconciliation

Pure reconciliation functions accept validated discovery occurrences and validated
acquisition evidence. Stable IDs use SHA-256 over explicit run-qualified components. Tuple fields are
sorted by explicit semantic keys, JSON objects use canonical key ordering, and JSONL
files contain one canonical object plus LF per record. Input-file order is normalized
by run ID and artifact fingerprint before reconciliation.

The preferred title remains null unless one source-original entry title is supported
without conflict by qualifying paired identity observations. All alternatives remain
available regardless of selection. Materially conflicting titles generate review
references rather than silent correction.

## Output and safety boundary

The CLI accepts explicit discovery run directories and one explicit output directory.
It rejects an existing output directory and permits output only beneath the
repository's ignored `.cache` directory, which necessarily excludes the external data
root and `01_raw`, `05_database`, `06_validation`, and `07_releases`. It never imports discovery
transport or acquisition execution code. The only canonical writer serializes all
seven candidate files and immediately rereads and validates them.

Candidate data remain ignored and local. Git contains only code, schemas, tests,
source-safe fixtures, and documentation. Dropbox remains read-only throughout M1-04A.

## Review boundary

M1-04A may establish that the observed numbered sequence 23–269 is internally
one-to-one from 2006-01 through 2026-07 and that reports 260–269 close against exact
bytes. It may not resolve reports 1–22, decompose the 2004/2005 historical bundles,
adjudicate ambiguous direct-file relations, or claim complete April-2004–July-2026
coverage. Those remain inputs to the separate M1-04 human review/materialization gate.
