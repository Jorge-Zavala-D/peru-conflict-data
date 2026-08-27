# ADR 005: Deterministic extraction precedes model assistance

Status: accepted, 2026-08-27.

## Context

End-to-end PDF-to-model-to-CSV processing obscures evidence, error mechanisms, and reproducibility.

## Decision

Use native text, layout, tables, and deterministic rules first. Model use requires authorized scope, minimal segments, strict schemas, source spans, null support, content-addressed caching, measured benchmarks, and complete model/prompt/settings/output metadata.

## Consequences

No model dependency or calls are included in M0. Later model value must be established against human gold evidence.
