# Discovery schema v0.2.0 to v0.3.0

Status: explicit forward version for M1-02.1. No prior schema directory is
regenerated or rewritten.

## Why the version changed

Discovery `v0.2.0` allowed one `page_title_original` and one
`publication_date_original` on every provisional record. That shape is ambiguous
on official thematic/search pages containing multiple independent entries: the
first page-wide date could be copied to unrelated report candidates.

Version `v0.3.0` replaces those ambiguous fields with:

- `source_page_title_original`: visible title of the containing HTML page;
- `entry_title_original`: title of the bounded source entry/card/item;
- `entry_publication_date_original`: date visible inside that same entry;
- `entry_description_original`: entry-local descriptive text used as evidence.

The version also adds strict schemas for one actual HTTP request attempt, a
reconnaissance-run summary, and the reviewed non-executable reports 260-269 pilot
acquisition recipe. Attempt receipts preserve timestamps, selected safe HTTP
headers, complete/partial body state, permitted-body byte count and SHA-256, and
normalized redirect-target evidence. The summary never represents corpus
completeness; M1 fixes `corpus_completeness_status` to `not_assessed`.

The pilot schema pins the reviewed authoritative hosts and all ten target rows,
including local benchmark hashes and structured uncertainty for opaque URLs.
`authorization_status` is fixed to `not_authorized`, and remote expected hashes
are fixed to null until an authorized retrieval exists.

## Migration rule

Changing `schema_version` is not a migration. A `v0.2.0` provisional record can be
upgraded only by re-parsing its exact observed HTML under the `v0.3.0` scoped-entry
rules. A reviewer must not copy `page_title_original` or
`publication_date_original` mechanically into entry fields because the old values
may have been page-global.

Legacy aggregate request receipts cannot be losslessly reconstructed as
per-attempt receipts. They retain their historical evidentiary value in the
ignored M1 run and its durable checksum receipt, but missing attempt timestamps,
headers, transient responses, and body hashes remain unknown.

## Retention

The generated directories `schemas/discovery/v0.1.0/` and
`schemas/discovery/v0.2.0/` are immutable. Tests pin complete tree digests for both
versions. The current exporter writes only `schemas/discovery/v0.3.0/` and the
scientific exporter continues to write only scientific `v0.2.0`.
