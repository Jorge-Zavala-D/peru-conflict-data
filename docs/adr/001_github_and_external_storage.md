# ADR 001: GitHub and external-storage separation

Status: accepted, 2026-08-27.

## Context

Official reports, administrative workbooks, extracted evidence, and canonical data are large or governed separately from the software.

## Decision

Git stores code, tests, schemas, configuration, small source-safe fixtures, documentation, and release recipes. `CONFLICT_DATA_ROOT` stores external/raw/derived data. Routine code refuses source/archive writes and Git policy rejects data formats.

## Consequences

CI is corpus-free. Reproduction requires an independently provisioned external root. Source immutability is enforced by workflow/code because Dropbox ACLs remain writable.
