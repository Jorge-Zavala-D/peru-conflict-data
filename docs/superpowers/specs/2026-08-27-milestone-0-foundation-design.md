# Milestone 0 Foundation Design

## Status and scope

This design records Jorge's approved 2026-08-27 initialization specification. It covers Milestone 0 only. Milestone 1 corpus discovery, extraction, OCR, historical harmonization, entity resolution, geocoding, and bulk model calls are outside this design.

## Evidence boundary

The Git repository contains reproducible software, tests, small fixtures, schemas, configuration, documentation, and canonical generated specifications. `CONFLICT_DATA_ROOT` points to external storage. Routine code treats `00_external` and `01_raw` as read-only and writes only beneath `02_extracted` through `07_releases`. Official Defensoría PDFs are the authoritative published primary source; `Base15-26.xlsx` is complementary administrative evidence.

## Foundation architecture

The Python package has six focused boundaries:

1. `config.py` loads versioned project configuration without embedding a user-specific path.
2. `paths.py` resolves and validates the external data root, refuses the Git repository as a data root, rejects traversal, and classifies read-only and writable zones.
3. `hashing.py` and `ids.py` provide streaming SHA-256 and deterministic content-derived identifiers.
4. `models/` defines strict, versioned, source-preserving Pydantic models for reports, cases, case-months, locations, actors, demands, protests, violence, dialogue, agreements, Defensoría actions, alerts, relationships, provenance, discrepancies, and manual review/adjudication.
5. `run_metadata.py` captures Git/config/schema/parser/lockfile/environment/input/model-prompt identity.
6. `json_logging.py` emits machine-readable JSON Lines without placing logs in raw storage.

JSON Schemas under `schemas/` are generated from the Pydantic models. Parquet and DuckDB remain the canonical future storage formats, but M0 does not create corpus tables or install the full data/PDF/OCR/geospatial/semantic stack.

## Domain rules

- Missing and unreported values remain `null`; no validator computes zero from absence.
- Source Spanish strings and normalized derivatives use distinct fields.
- Stock status and transition evidence use distinct fields, including became-latent.
- Conflict cases and protests are distinct records connected by an explicit link model.
- Violence is event-level; casualty totals/components are nullable independently.
- Identity methods follow official code, deterministic linkage, probabilistic candidate, and manual adjudication without hard-coding historical taxonomies.
- Material values can carry one or more provenance records with report hash, page/section/span/bbox, extractor/parser/schema versions, and probabilistic model/prompt metadata when applicable.
- Source contradictions and parser errors are separate discrepancy classes.
- Manual decisions are append-only versioned adjudication records, not edits to derived data.

## Quality and delivery

Tests exercise path safety, hashing, strict schema validation, stable identifiers, nullable missingness, configuration loading, run metadata, JSON logging, and Git data-policy checks. CI installs only the locked M0 development group and never accesses Dropbox. Ruff, Pyright, pytest, pre-commit, and a repository data-policy guard are required gates. The live MIT `LICENSE` is preserved byte-for-byte. No commit, push, PR, merge, or M1 work is part of this execution.
