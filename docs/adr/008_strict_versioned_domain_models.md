# ADR 008: Strict versioned domain models are the schema source

Status: accepted, 2026-08-27.

## Context

Permissive hand-written schema stubs could silently accept drift and omitted several canonical relationships.

## Decision

Use frozen Pydantic models with strict/non-coercing values, finite numbers, `extra=forbid`, and schema version `0.1.0`. Generate deterministic JSON Schemas for all 23 M0 entities under `schemas/v0.1.0/` and preserve earlier version directories. Keep historical classifications, source-original transitions, and relationship vocabulary open until evidenced. Close only pipeline-controlled extraction-method and discrepancy vocabularies. Python validation is authoritative for semantic cross-field rules; generated schema explicitly carries the probabilistic-model metadata condition.

## Consequences

Model changes require tests, regenerated schemas, documentation, and migration review. Strictness applies to record shape, not premature taxonomy closure.
