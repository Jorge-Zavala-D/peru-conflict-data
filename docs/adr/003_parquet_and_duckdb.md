# ADR 003: Parquet and DuckDB canonical storage

Status: accepted, 2026-08-27.

## Context

The project needs typed columnar files, relational validation, portable local analysis, and downstream Stata/R/CSV/XLSX exports.

## Decision

Use Parquet for canonical tables and DuckDB for relational querying. Export formats are generated products.

## Consequences

M0 defines schemas but defers storage dependencies until a milestone writes canonical tables. Canonical files remain outside Git.
