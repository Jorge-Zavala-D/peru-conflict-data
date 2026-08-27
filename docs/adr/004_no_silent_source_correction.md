# ADR 004: No silent source correction

Status: accepted, 2026-08-27.

## Context

Published reports may contradict themselves or administrative evidence; parsers may also be wrong.

## Decision

Preserve every sourced value and exact evidence. Classify parser error, source inconsistency, ambiguity, missing evidence, cross-source conflict, and potential editorial error separately. Preferred analytical values, if later needed, are explicit derivatives.

## Consequences

Arithmetic or cross-source QA produces discrepancy and review records, never in-place repair.
