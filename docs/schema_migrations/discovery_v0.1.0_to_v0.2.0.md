# Discovery schema migration: v0.1.0 to v0.2.0

Status: approved technical migration for the M1 read-only inventory, 2026-08-27.
`schemas/discovery/v0.1.0/` is immutable and remains available for historical receipts.
The current generator writes only `schemas/discovery/v0.2.0/`.

## Change

`ProvisionalDiscoveryRecord` adds two nullable source-original fields:

- `page_title_original`: visible page/landing title text when exposed;
- `publication_date_original`: publication-date text as displayed or exposed in HTML metadata.

The values are copied from the observed HTML and are not normalized, inferred, or used as
sole report identity evidence. Existing candidate number/month evidence rules, URL roles,
redirect-chain rules, issue classifications, and missingness semantics are unchanged.

## Migration rule

An existing v0.1.0 record may be read as v0.2.0 only through an explicit migration step that
sets the two new fields to `null` unless a separately retained page observation supports the
source-original value. Changing `schema_version` alone is not a migration. The M1-02 bounded
run was rerun after the code change, so its records contain the fields under v0.2.0. No old
record or v0.1.0 schema file was edited in place.
