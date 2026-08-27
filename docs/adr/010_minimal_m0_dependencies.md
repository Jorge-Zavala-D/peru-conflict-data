# ADR 010: Minimal Milestone 0 dependency set

Status: accepted, 2026-08-27.

## Context

The seed proposed a broad PDF/OCR/geospatial/linkage/semantic stack before any benchmark justified those tools.

## Decision

M0 runtime depends only on Pydantic and PyYAML. Development adds uv-locked pytest, Ruff, Pyright, coverage, pre-commit, and required type stubs. Defer Parquet/DuckDB, PDF, OCR, table, geospatial, linkage, and model libraries until the first task that needs them.

## Consequences

CI installs a small locked environment. Later dependency additions require purpose, system requirements, license/security review, and benchmark evidence where applicable.
