# Milestone 0.1 Hardening Design

## Status and boundary

This design records the owner-approved hardening pass for 2026-08-27. It remains on
`codex/milestone-0-foundation` and does not authorize Milestone 1 discovery, acquisition,
benchmark annotation, extraction, OCR, entity resolution, or writes to `01_raw`.

The existing `schemas/v0.1.0/` directory is an immutable M0 snapshot. The working
source contract becomes `v0.2.0`; generated schemas are written only to
`schemas/v0.2.0/`. A migration note and tests document version retention and make an
explicit migration boundary necessary rather than silently treating old records as new
records.

## Evidence-driven source additions

The additions below are nullable/source-preserving because they are directly evidenced in
the ten-report benchmark, especially report 269. No historical taxonomy is closed by this
change.

### Demand dimensions

`Demand` keeps `theme_original`, adds `category_original`, and keeps
`competent_entity_original` as separate source columns. `category_normalized` is an
optional derivative and is not populated by the schema. A category is never inferred from
theme or competent entity.

### Dialogue and mediation

`MediationProcess` represents a continuing process and preserves start date (with source
precision), status, requester, actors, mediation type, mediator, case description,
demands, and process progress as separate original fields. It may link to a case and to
dated `DialogueEvent` records. `DialogueEvent` remains the event-level table for dated
dialogue occurrences and gains a nullable process link and date-precision field. Neither
model assumes that a process is one event.

### Agreements and follow-up

`Agreement` separates case description, agreement text, and compliance-progress text.
Optional responsibility and deadline strings preserve explicitly stated source values
without resolving organizations into the actor table or interpreting a deadline that the
source does not state. Agreement date precision is nullable and source-preserving.

### Defensoría interventions

`DefensoriaAction` retains the broad source action type and adds nullable original
category, subtype, and hierarchy-path fields plus optional normalized derivatives. The
hierarchy path is an ordered tuple of source labels; it does not become a closed enum or
an actor link.

### Alerts, geography, protests, and violence

`Alert` gains nullable source-original alert type, risk, and location fields. `Location`
keeps the complete original location text and adds nullable structured original
department, province, district, and population-center components beside normalized
derivatives. `ProtestEvent` records nullable original event-date text and open date
precision. `ViolenceEvent` records nullable source-original violence-event type and event
date precision. Existing dates remain parsed derivatives and may be null when the source
is imprecise.

## Source-reported versus derived monthly indicators

`ReportMonthAggregate` gains a required open `indicator_basis` value with the two pipeline
meanings `source_reported` and `derived` (the values describe provenance, not a historical
taxonomy). A source-reported row retains its original metric label, value, unit, scope,
and provenance. A derived row additionally requires a derivation name/version and at
least one upstream record identifier; it never overwrites or substitutes for a
source-reported row with the same metric. Event-table calculations are therefore
published as separate derived rows, while a PDF narrative/table indicator remains a
separate source-reported row even when the numbers happen to agree.

## Provenance, nulls, and identity

All additions preserve the existing provenance architecture. `None` means unreported or
not available; an empty source string is retained as an empty value only when the source
actually contains one; zero remains a reported zero. Original and normalized fields are
never merged. Report identity must use visible document evidence and/or official landing
or download metadata; an embedded PDF `/Title` value such as `RCS N° 126` is never sole
evidence. Disagreements become discrepancy records.

## Manifest boundary

Dropbox `01_raw/manifests/` is the operational acquisition ledger: discovery output,
retrieval receipts, HTTP metadata, retries, local paths, acquisition status, collision
evidence, and alternate byte-version records. Git contains manifest schemas, discovery and
acquisition code, official-domain configuration, tests, methodological rules, and only
small reviewed metadata indexes when explicitly useful. A canonical normalized report
manifest will later be materialized in Parquet/DuckDB; release-specific inventories and
checksums belong under `07_releases`. Git does not hold a mutable operational manifest.

## M1 safety and deferred benchmark discrepancies

M1 identity checks must require report number and reference month from document-visible
evidence and/or official metadata and preserve conflicts. The following report-269
observations are reconnaissance notes for M2, not corrections:

1. Alert narrative text reports 58 alerts with a 51/2/5 breakdown, while Cuadro N.° 1
   reports 34 with a 28/2/4 breakdown.
2. In a July 2026 report, case `1514-0726` says `Ingresó como caso nuevo: Agosto 2026`.

Both are candidate `SOURCE_INCONSISTENCY` records once independently benchmarked.

## Non-goals and acceptance

This pass does not add PDF/OCR/geospatial/model dependencies, run the corpus, create
derived Dropbox files, resolve historical identities, or weaken any benchmark gate.
Acceptance requires generated-schema synchronization, migration/version tests, complete
local quality checks, unchanged source hashes and source counts, a clean repository data
policy check, and an independent pull-request Actions run. The branch is not merged.
