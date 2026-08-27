# ADR 008: Strict versioned domain models are the schema source

Status: accepted, 2026-08-27.

## Context

Permissive hand-written schema stubs could silently accept drift and omitted several canonical relationships.

## Decision

Use frozen Pydantic models with strict/non-coercing values, finite numbers, `extra=forbid`, and versioned schemas. Preserve the 23-entity M0 snapshot under `schemas/v0.1.0/`; the source-evidenced v0.2.0 contract adds `mediation_process`, source-level dimensions, identity-evidence guards, and explicit source-reported/derived indicators under `schemas/v0.2.0/`. Keep historical classifications, source-original transitions, and relationship vocabulary open until evidenced. Close only pipeline-controlled extraction-method, discrepancy, indicator-basis, and identity-evidence controls. Python validation is authoritative for semantic cross-field rules; generated schemas carry the key conditional guards.

## Consequences

Model changes require tests, regenerated schemas, documentation, and migration review. Strictness applies to record shape, not premature taxonomy closure.
