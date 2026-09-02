# M2-01 human annotation handbook

Version: 0.1.0. Scope: fixed PDFs for reports 260–269. Status: owner-review draft;
not human gold. Scientific target: v0.3.0. Benchmark technical contract: v0.1.0.

## 1. Governing rules

Annotate only source-visible information from the assigned PDF pages. Preserve Spanish strings,
capitalization, punctuation, and reported precision. Never infer a case link, actor role, normalized
taxonomy, date precision, zero, or longitudinal identity merely because it seems plausible. A blank
cell is not zero. A report-level annex row is not a case object unless the source explicitly links it.
Contradictory published values are recorded separately and queued as `SOURCE_INCONSISTENCY`.

Annotators A and B receive the same PDF bytes, handbook, unit boundaries, and blank forms. They may
not see each other's work, machine suggestions, parser output, or adjudications before both
submissions lock. A locked submission is immutable. Corrections create a superseding submission;
disagreements and adjudications never overwrite A or B. Annotator IDs are pseudonymous role IDs,
not personal information.

## 2. Annotation states

| State | Meaning | Domain materialization |
|---|---|---|
| `observed` | A source-visible nonzero value is present. | Exact source value; normalization remains separate. |
| `explicit_zero` | The source explicitly reports numeric zero or an unambiguous none-count. | Numeric zero only; never inferred from absence. |
| `not_reported` | The applicable field has no reported value in the bounded unit. | Domain `None`; reason retained in annotation metadata. |
| `not_applicable` | The field does not apply to this source object. | Domain `None`; not interchangeable with not reported. |
| `source_ambiguous` | Two or more plausible source readings exist. | No canonical value until adjudicated. |
| `structurally_unavailable` | This report/section design does not expose the field. | Domain `None`; report-format fact retained. |
| `illegible_uninspectable` | The assigned evidence cannot be read reliably. | No value; requires later source-forensics decision. |
| `annotation_uncertain` | Annotator can state a candidate but cannot reach protocol certainty. | No gold value until adjudicated; comment required. |

JSON null is not itself an annotation state. `raw_value_json` is present for `observed` and is the
numeric literal `0` for `explicit_zero`; required non-value states omit it. Source ambiguity may
retain candidate text only as an annotation value and must include a comment.

## 3. Unit types and deterministic boundaries

- `report`: cover/title/reference period and report-wide metadata.
- `report_month_aggregate`: one named source aggregate/table cell for the report month.
- `case_observation`: one case block as published in one report.
- `case_subobject`: a bounded actor, demand, dialogue, violence, mediation, agreement, action,
  alert, relationship, or provenance object attached by explicit evidence.
- `report_annex_event`: one or more bounded rows in protest/violence/action annexes.
- `source_only_object`: published material that cannot safely be linked to a case.

Unit IDs are SHA-256-derived from report number, source SHA, unit type, exact sorted page tuple, and
a reviewed source locator. Changing any boundary creates a new unit ID. Pilot units are fixed in
`config/benchmark/m2_partition_v1.yaml`.

## 4. Page-evidence contract

Every critical annotation carries report ID/number, exact PDF SHA, one-based page, and section.
Use an exact text span for prose or a bounding box when layout is material. A table cell anchor also
records table title, row label, and column label. Page-only evidence is allowed only for a fact whose
entire page is the meaningful unit (for example, a page-wide absence/format observation) and requires
a rationale. Cross-page evidence uses multiple anchors in reading order. Repeated statements may
share one anchor across multiple field annotations; do not duplicate or paraphrase source text.
When two pages conflict, retain both anchors and open a discrepancy.

## 5. Scientific field dictionary

All records inherit exact `schema_version`. IDs are stable technical identifiers, never inferred
source values. Unless stated otherwise, `*_original` is copied from the PDF, `*_normalized` is left
null by human annotators, and `provenance_ids` contains the evidence records supporting the object.

### Report and report-month objects

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `ReportRecord` | `report_id`, `source_version_id`, `report_number`, `reference_period`, identity-evidence types/IDs, `publication_date`, `title_original`, `source_url_original`, `source_filename`, `canonical_filename`, `sha256`, `byte_size`, `page_count`, `source_status`, `native_text_status`, `format_regime`, `supersedes_source_version_id`, `provenance_ids`. Annotators confirm document-visible number/month/title/page count; custody fields are packet-fixed, not inferred from prose. | One per PDF byte version; number/month need qualifying evidence. | number, month, SHA. |
| `ReportMonthAggregate` | `report_month_id`, `report_id`, `metric_original`, `indicator_basis`, `value`, `unit_original`, `scope_original`, `provenance_ids`, derivation name/version/upstream IDs. Human source rows use `source_reported`; annotators never create derived rows. | One per named aggregate/table cell; exact row/column anchor. | Approved aggregate metrics and provenance. |

### Case identity, observation, and location

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `ConflictCase` | `case_id`, `official_code`, `canonical_name`, `identity_method`, `identity_confidence`, `provenance_ids`. Human annotation records source observations; canonical identity/linkage is not decided here unless an official code is visible. | Zero/one linked identity per observation; official-code anchor required. | ID/code. |
| `CaseName` | `case_name_id`, `case_id`, `report_id`, `name_original`, `name_normalized`, `provenance_ids`. Copy the exact displayed case/denomination label. | One or more names per case observation. | original name. |
| `CaseMonth` | `case_month_id`, `case_id`, `report_id`, `reference_period`, `official_code_original`, `name_original`, stock status original/normalized, phase original/normalized, conflict type original/normalized, `case_description_original`, `transitions`, `monthly_facts_original`, `provenance_ids`. Structural description and current/month facts are separate even if repeated. | One per case/report observation; field-level anchors. | status, phase, type, description, monthly facts, transitions. |
| `CaseReportedIndicator` | `case_reported_indicator_id`, `case_month_id`, `case_id`, `report_id`, `metric_original`, non-null `value`, `unit_original`, `scope_original`, `provenance_ids`. Use only for a value explicitly reported at case/reporting scope; never calculate from events. | Zero or more per case-month; exact label/cell anchor. | violence/casualty/dialogue indicators. |
| `Location` | `location_id`, `location_text_original`, department/province/district/population-center original and normalized fields, `ubigeo`, match method/version/confidence, provenance. Copy the full source location and separately transcribe visible levels; do not infer omitted levels. | One per distinct source location string. | original and visible levels. |
| `CaseLocation` | `case_location_id`, `case_id`, `report_id`, `location_id`, `relationship_original`, provenance. Create only when the source attaches the location to the case. | Zero or more per case observation. | relationship and link evidence. |

### Actors and demands

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `Actor` | `actor_id`, `name_original`, name/type normalized/original, provenance. Copy each source-visible actor; do not split ambiguous collective strings without a protocol basis. | One per distinct actor mention chosen under unit rules. | original name. |
| `CaseActor` | `case_actor_id`, `case_id`, `report_id`, `actor_id`, role original/normalized, provenance. Role must be explicit or `not_reported`; list position alone is not a role. | Zero or more per case observation. | explicit role/link. |
| `Demand` | `demand_id`, nullable `text_original`, text normalized, theme original/normalized, category original/normalized, competent entity original, provenance. Annotate each source dimension independently; structured-only rows are valid. | One per demand/category row; at least one original dimension. | text when present, theme, category, competent entity. |
| `CaseDemand` | `case_demand_id`, `case_id`, `report_id`, `demand_id`, provenance. Create only when the source row/narrative establishes the case link. | Zero or more; explicit link anchor. | link evidence. |

### Protest and violence

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `ProtestEvent` | `protest_event_id`, `report_id`, date/original/precision, measure type original/normalized, actor/location/demand text, `violence_explicit`, provenance. Copy one annex row as one event unless the source visibly groups multiple actions. | Zero or more report-level events. | date, measure, actor, location, demand. |
| `CaseProtestLink` | link ID, case ID, protest ID, `link_method`, confidence, provenance. Never infer from a shared place/name alone. | Optional; evidence mandatory. | link evidence. |
| `ViolenceEvent` | event ID, report/case/protest IDs, date/original/precision, violence type, description, fatalities/injured totals, casualty components, provenance. A dash/blank is not automatically zero; retain source contradiction. | Zero or more dated/source-bounded events. | dates, type, totals/components. |
| `CasualtyComponent` | component label, fatalities, injured. Copy civilian/police/armed-forces components exactly; unknown stays null. | Nested zero or more per violence event. | both counts and component. |

### Dialogue and mediation

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `DialogueEvent` | event ID, report/case/mediation IDs, date/original/precision, description, status, provenance. Requires a dated or distinctly bounded dialogue occurrence; source-reported case status alone belongs in `CaseReportedIndicator`. | Zero or more events; mediation link evidence mandatory. | date, description, status. |
| `MediationObservation` | observation ID, report ID, optional process/case IDs, start date/original/precision, status, requester, actors, mediation type, mediator, case description, demands, progress, provenance. Transcribe one report-local block. Do not assign process identity. | One per published mediation block. | start date, status/type/mediator, description/progress. |
| `MediationProcess` | process ID, optional case ID, canonical label, required identity method, optional confidence, and mandatory provenance. This is a later evidence-backed identity object, not a direct annotation answer. | Created only after linkage review; usually zero in raw annotations. | identity evidence if created. |

### Agreements, actions, alerts, and relationships

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `Agreement` | agreement ID, report/case IDs, date/original/precision, case description, agreement text, compliance progress, responsibility, deadline, provenance. Keep agreement text and monthly compliance separate. | Zero or more agreement rows/items. | date, text, compliance. |
| `DefensoriaAction` | action ID, report/case IDs, action date, action type, intervention category/subtype originals/normalized, hierarchy, description, provenance. Preserve table hierarchy and narrative action separately. | Zero or more; report-level counts need not be case-linked. | date/type/provenance. |
| `Alert` | alert ID, report/case IDs, date, text, type, risk, location, provenance. Do not infer a case relationship from geographic overlap. | Zero or more report alerts. | type/risk/location/provenance. |
| `CaseRelationship` | relationship ID, from/to case IDs, relationship type original/normalized, effective period, confidence, provenance. Only explicit or adjudicated continuation/rename/merge/split/reactivation/related evidence qualifies. | Zero or more; evidence required. | all identity-bearing fields. |

### Evidence, discrepancy, and review records

| Object | Fields and annotation rule | Cardinality / evidence | Critical |
|---|---|---|---|
| `ProvenanceRecord` | provenance/object/field IDs; report ID/SHA/page/section/table/bbox/span/text; extraction method; extractor/parser/model metadata; confidence/status. Human annotations use `manual`; no model invocation. | At least one per critical fact; reusable across fields. | report/SHA/page/section/span/bbox. |
| `DiscrepancyRecord` | discrepancy/report IDs, type, severity, values and both provenance sides, status, rationale, parser version, review ID. Source contradictions use `SOURCE_INCONSISTENCY`; parser differences use `PARSER_ERROR`. | One per identified discrepancy. | type and both evidence sides. |
| `ManualReviewItem` | review/object IDs, issue type, candidate JSON, optional machine suggestion plus invocation, evidence IDs, neighboring periods, status, second-review flag, creation time/parser version. Machine suggestions are prohibited in A/B forms. | Append-only review queue item. | evidence and status. |
| `AdjudicationRecord` | adjudication/review IDs, decision/action/payload, rationale, reviewer/time/version, evidence IDs, supersession and second-review fields. Never rewrite the underlying submissions. | Append-only decisions; second reviewer differs. | decision, rationale, evidence. |

## 6. Benchmark technical records

`AnnotationUnit` freezes source bounds. `EvidenceAnchor` implements Section 4. `FieldAnnotation`
stores one field/cardinality position and one explicit state. `AnnotatorSubmission` preserves an
immutable A or B submission after lock. `AnnotationDisagreement` references both submissions and
their annotations. `GoldAdjudication` records a separate reviewed decision. `BenchmarkCoverageReceipt`
proves every required field is either observed or assigned an allowed non-value state.
`BenchmarkPartition` freezes report-level roles.

## 7. Common ambiguities and prohibited inference

- A dash may mean zero, unavailable, or typographic suppression; use surrounding labels and the
  handbook, otherwise `source_ambiguous`.
- A case description repeated month to month is still a report-specific observation.
- “En diálogo” or a mediation type is not a dated dialogue event.
- Cumulative casualty counts are not reconstructed from individual event rows.
- A competent entity is not automatically an actor role or an agreement responsibility.
- Similar mediation titles do not create a longitudinal process.
- A protest row is source-only until a case link is explicit.
- Normalized values, UBIGEO, and taxonomy mappings are not human gold in M2-02 unless separately
  added to an approved normalized benchmark layer.

## 8. Pilot and handoff

Reports 264 and 269 are protocol-pilot reports and cannot later be blind holdout. The two blank
packets under `.cache/m2-01/pilots/` contain no substantive answers. Pilot review must confirm that
two independent annotators can apply these rules without definition-level ambiguity before M2-01
closes or M2-02 begins.
