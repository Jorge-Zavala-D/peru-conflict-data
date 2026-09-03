# M2-01 source-grounded ontology decisions

These are proposed owner decisions for scientific schema v0.3.0. “Source fact” means visible in
the fixed reports 260–269; “modeling decision” states the proposed representation; “inference” is
explicitly identified. Approval remains with Jorge.

## Q1 — nullable `Demand.text_original`

- **Current behavior:** v0.2.0 requires a nonblank verbatim `text_original` for every `Demand`.
- **Source facts:** every report includes structured “Demandas sociales identificadas” tables.
  Reports 260 pp. 28–29, 264 pp. 25–26, and 269 pp. 40–41 show theme, category, count, and
  competent entity without a verbatim demand sentence in the same row. The same structure recurs
  in reports 261–263 and 265–268. The general taxonomy is not a case-specific demand sentence.
- **Counterexample:** narrative new-case and protest rows often contain a source-visible demand
  sentence; those records retain `text_original`.
- **Decision:** make `Demand.text_original` nullable, but require at least one source-visible
  original dimension among text, theme, category, and competent entity. Never synthesize text from
  a category.
- **Annotation impact:** annotate each dimension independently. `not_reported` for text is not an
  empty string and does not erase observed structured dimensions.
- **Migration/backward compatibility:** existing v0.2.0 rows migrate without value change; new
  structured-only rows become valid in v0.3.0. Owner approval required.

## Q2 — source-reported case indicators versus events

- **Current behavior:** v0.2.0 has report aggregates plus event records, but no dedicated
  source-reported case-month indicator.
- **Source facts:** case tables and violence sections report statuses/counts at case or reporting
  scope independently of dated event narratives. Report 269 pp. 110–111 demonstrates that a
  report statement and a named-case casualty count can coexist and conflict. Mediation blocks also
  report source-local status/mechanism values without describing a dated dialogue event.
- **Decision:** add `CaseReportedIndicator`, keyed to case-month/report with `metric_original`,
  non-null source value, unit/scope, and mandatory provenance. It is source-reported only and is
  never computed from `ViolenceEvent` or `DialogueEvent`.
- **Annotation impact:** record the visible value and scope; missing/zero/ambiguous state stays in
  benchmark metadata. Derived measures remain separate downstream records.
- **Remaining uncertainty:** historical label stability is unknown; metric names remain open
  source strings. Owner approval required.

## Q3 — structural case description versus monthly facts

- **Current behavior:** v0.2.0 exposes `CaseMonth.monthly_facts_original` but no case-description
  field on the observation.
- **Source facts:** report 260 p. 16 presents `Descripción del caso`, `Descripción de los acuerdos`,
  and `Hechos del mes` as distinct columns. Report 267 p. 12 presents `Descripción del caso`,
  `Descripción de los acuerdos`, and `Avances de cumplimiento`. Report 268 p. 17 begins the
  agreement-monitoring section with `Descripción del caso`, `Acuerdos`, and `Avances de
  cumplimiento`; report 269 p. 15 similarly separates `Problemática`, `Acuerdos`, and `Avances de
  cumplimiento`. Equivalent separation recurs in all ten reports.
- **Decision:** add `CaseMonth.case_description_original`. It records the structural description as
  published in that report; it is not treated as timeless canonical text and is not conflated with
  `monthly_facts_original`.
- **Annotation impact:** both fields receive separate annotations/anchors, even when prose overlaps.
- **Migration:** v0.2.0 case-month rows migrate with the new field null until source-annotated.
  Owner approval required.

## Q4 — mediation identity and observation

- **Current behavior:** v0.2.0 `MediationProcess` combines a process ID with `report_id` and all
  source-local report fields.
- **Source facts:** mediation blocks recur across reports, and report 264 p. 6 shows a complete
  report-local record. No stable source mediation-process identifier or explicit cross-report
  continuity statement was observed in any of the ten PDFs.
- **Decision:** separate optional `MediationProcess` identity from `MediationObservation`.
  `MediationObservation` owns `report_id` and all published fields. Its process/case links are
  optional and require provenance. `MediationProcess` is created only after evidence-backed
  cross-report linkage; visually similar labels do not establish continuity.
- **Source-column mapping:** in report 264 p. 6, `Estado` is the source status and maps to
  `MediationObservation.status_original`; the `Estado situacional` narrative maps to
  `MediationObservation.progress_original`. They are not interchangeable status codes.
- **Annotation impact:** annotators create source-local observations. They do not assign a process
  identity. Later linkage/adjudication may add identity records without rewriting observations.
- **Migration:** each v0.2.0 process row becomes a v0.3.0 observation; a process row is created only
  when identity evidence exists. Owner approval required.

## Q5 — additional fields and rejected additions

### Accepted source-evidenced additions

- `CaseMonth.case_description_original`, for the recurring structural/problem description.
- `CaseReportedIndicator`, for source-reported case-level dialogue, mechanism, violence, casualty,
  or other named indicators with explicit scope and provenance.
- `MediationObservation`, to represent source-local mediation blocks independently of identity.

Existing models already represent the remaining recurring structures: multi-level `Location`,
actors/roles, demand dimensions, protests, violence/casualty components, dialogue events,
agreements/compliance, Defensoría actions, alerts, transitions, report aggregates, provenance, and
source discrepancies. The report-269 casualty contradiction is handled by `DiscrepancyRecord`, not
by adding a repaired casualty field.

### Rejected as speculative in this version

- A closed dialogue, violence, demand, alert, or mediation taxonomy: the ten reports do not prove
  longitudinally stable enumerations.
- Automatic case links for protest-annex rows: the source does not always establish them.
- A mandatory persistent mediation identity: no stable source ID was found.
- Derived cumulative violence calculated from events: source-reported and derived values must stay
  separate.
- A timeless canonical case description: report-specific wording can change.

## Migration summary

Scientific schemas v0.1.0 and v0.2.0 remain immutable. Version v0.3.0 changes `Demand`,
`CaseMonth`, and mediation semantics and adds two registered objects. Consumers must explicitly
migrate the schema version; no v0.2.0 payload is silently relabeled. Source-original strings remain
primary, normalized values optional, unknown remains null, and benchmark annotation states carry
the richer reason for non-values.
