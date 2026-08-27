# ADR 006: Benchmark before scale

Status: accepted, 2026-08-27.

## Context

Apparent extraction speed can hide systematic case, page, arithmetic, and linkage errors.

## Decision

Reports 260-269 are the first consecutive modern benchmark. Do not process a regime at scale until human gold evaluation meets accepted targets or Jorge approves an evidence-backed revision.

## Consequences

M0 performs only file/page/native-text/workbook inventory. It creates no fake gold tests or parser accuracy claims.
