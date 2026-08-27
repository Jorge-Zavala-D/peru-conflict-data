# ADR 007: Validated external data root and write zones

Status: accepted, 2026-08-27.

## Context

Hard-coded Dropbox paths are not portable, and writable filesystem permissions do not protect raw evidence.

## Decision

Resolve `CONFLICT_DATA_ROOT` or an explicit test argument, require the nine expected directories, refuse any overlap in either direction between the repository and data root, reject traversal, and allow routine writes only beneath `02_extracted` through `07_releases`. Classify both the logical path and its resolved target so a symlink/reparse alias under a protected zone cannot become writable.

## Consequences

Tests use synthetic temporary roots. Any exceptional source/archive mutation requires a separate explicitly authorized acquisition or archival workflow.
