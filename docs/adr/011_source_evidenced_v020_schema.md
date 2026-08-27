# ADR 011: Source-evidenced v0.2.0 schema hardening

Status: accepted for the M0.1 hardening branch, 2026-08-27; owner review remains
required before M1.

## Context

Report 269 exposes source dimensions that the initial M0 model could not preserve:
separate demand theme/category/competent entity columns, process-level mediation records,
agreement follow-up text, intervention hierarchy, alert risk/type/location, structured
geography, date precision, and violence-event type. Monthly report indicators can also be
published independently of event-level calculations. The M0 schema directory is already a
committed snapshot and must remain reproducible.

## Decision

Retain `schemas/v0.1.0/` unchanged and generate `schemas/v0.2.0/` from strict Pydantic
models. Add nullable source-original fields, optional normalized derivatives, a
`MediationProcess` relation, and conditional indicator-basis/derivation metadata. Keep
dated dialogue events separate from processes, agreement text separate from compliance
progress, and source-reported indicator rows separate from derived rows. Require report
number/reference-period evidence that is document-visible or official metadata; an
embedded PDF title alone is insufficient. Do not close historical Spanish taxonomies.

## Consequences

Future records must be explicitly migrated and revalidated; changing only a version string
is invalid. Existing raw bytes and v0.1 schemas remain auditable. The richer contract
prevents source information loss while leaving historical harmonization and identity parts
for evidence-based later milestones.
