# Scientific schema v0.3.0 migration

Version 0.3.0 is the owner-approved M2-01 source-evidence contract. Historical `schemas/v0.1.0/` and
`schemas/v0.2.0/` remain immutable snapshots; consumers must opt into v0.3.0.

## Mechanical migration

- Change `schema_version` from `0.2.0` to `0.3.0` only while applying the semantic
  transformations below. Relabeling alone is invalid.
- Existing `Demand` rows retain all values. Structured source rows may set
  `text_original` null only when at least one original theme/category/competent-entity
  dimension is present.
- Existing `CaseMonth` rows add `case_description_original = null` until that field is
  independently annotated. Do not copy `monthly_facts_original` into it.
- A source-reported case-level metric becomes `CaseReportedIndicator` with a non-null
  source value and provenance. Do not materialize it by aggregating event records.
- Each v0.2.0 `MediationProcess` source row becomes a v0.3.0
  `MediationObservation`. Its old process ID is not automatically retained as a
  persistent identity. Create `MediationProcess` and link it only when cross-report
  evidence supports continuity; every process identity requires a named identity method and
  provenance, and both case and process links remain evidence-bearing.

Normalized fields remain optional derivatives. Benchmark states explain why a source
value is absent; scientific-domain null continues to mean unknown/unreported at the
domain layer and never implies zero.
