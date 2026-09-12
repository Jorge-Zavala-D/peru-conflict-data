# Canonical field-level data dictionary (schema v0.3.0)

This dictionary is synchronized with the 26 models in
`peru_conflicts.models.MODEL_REGISTRY` and the generated files in `schemas/v0.3.0/`.
The Python models and their validators are authoritative; this document explains the
research meaning and storage contract. `schemas/v0.1.0/` is retained as the immutable
M0 snapshot and is documented by the migration note in
`docs/schema_migrations/v0.1.0_to_v0.2.0.md`. The M2-01 migration is documented in
`docs/scientific_schema_v0_3_0_migration.md`; v0.2.0 also remains immutable.

## Conventions

- **Representation:** `id` is a nonblank stable identifier; `str` is a source string
  unless marked normalized; `date` is an ISO date parsed from source evidence;
  `YYYY-MM` is a validated reference month; `int/float` is a numeric measure; `bool`
  is an explicitly reported boolean; `hash` is lowercase SHA-256.
- **Original/normalized:** `orig` preserves the published Spanish value or source
  spelling exactly (including an observed empty string); `norm` is a separately versioned
  derivative and may be null. A parsed date or code is not a license to discard the
  original text.
- **Null:** `null` means unreported, unavailable, or not supported by the source. It is
  not zero. A reported numeric `0` remains `0`; a source-provided empty string remains
  distinct from both `null` and `0`.
- **Multiplicity:** `1` is required once, `0..1` is optional scalar, and `0..*` is an
  optional repeated tuple. Empty repeated tuples mean no retained members, not a source
  claim that the set is empty.
- **Provenance:** `P` means a material field must be traceable to one or more
  `provenance` rows with report/hash/page/section and evidence text where feasible;
  `P*` means the association row carries that evidence; `—` is a technical field whose
  identity is captured by run metadata or a parent record. Provenance IDs are links, not
  embedded copies of the source.
- **Origin:** `S` source-reported; `D` derived by the pipeline; `S/D` depends on the
  explicit field/basis value; `T` technical metadata. Historical labels remain open
  strings. The only closed values below are pipeline controls, not historical taxonomies.

Every registry model also has `schema_version` (`1`, `str`, `T`, `0..1` with a default
equal to `0.3.0`, `—`, record version) and must validate against the generated schema.

## `report` (`ReportRecord`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `report_id` | Stable report identity used by all report-scoped records | id | — | 1 | Key referenced by every report-scoped entity | T |
| `source_version_id` | Identity of this official byte/version observation | id | — | 1 | Key for alternate-byte records | T |
| `report_number` | Published report number, integer | orig numeric | N | 0..1 | P; supported by its evidence-type and provenance-ID fields | S |
| `reference_period` | Reported reference month, validated `YYYY-MM` | parsed/orig value | N | 0..1 | P; supported by its evidence-type and provenance-ID fields | S/D |
| `report_number_evidence_types` | Evidence classes (`document_visible`, `official_metadata`, or `embedded_pdf_title`) | source-evidence classification | empty | 0..* | Describes `report_number_provenance_ids` | T/S |
| `report_number_provenance_ids` | Evidence rows supporting report number | ids | empty unless number present | 0..* | FK to `provenance`; visible/metadata evidence required | T |
| `reference_period_evidence_types` | Evidence classes supporting reference month | source-evidence classification | empty | 0..* | Describes `reference_period_provenance_ids` | T/S |
| `reference_period_provenance_ids` | Evidence rows supporting reference month | ids | empty unless period present | 0..* | FK to `provenance`; visible/metadata evidence required | T |
| `publication_date` | Publication date parsed from official evidence | date | N | 0..1 | P where available | S/D |
| `title_original` | Title as printed or carried by source | orig str | N | 0..1 | P; PDF metadata alone is not identity evidence | S |
| `source_url_original` | Official landing/download URL as observed | orig str | N | 0..1 | P or acquisition receipt reference | S |
| `source_filename` | Original stored filename | orig str | — | 1 | Links to immutable raw/external path | S/T |
| `canonical_filename` | Deterministic repository filename derivative | norm str | N | 0..1 | Run/config identity | D |
| `sha256` | Hash of exact source bytes | hash | — | 1 | Closes to raw byte version | T |
| `byte_size` | Exact source byte count | int / bytes | — | 1 | Hash receipt | T/S |
| `page_count` | PDF page count | int / pages | N | 0..1 | P/forensic receipt | S/D |
| `source_status` | Published/observed source status label | orig str | N | 0..1 | P where source states it | S |
| `native_text_status` | Native-text diagnostic status | str | N | 0..1 | Forensic/run receipt | D |
| `format_regime` | Empirically assigned parser-regime label | str | N | 0..1 | Method/run evidence | D |
| `supersedes_source_version_id` | Prior byte version replaced or revised by this one | id | N | 0..1 | FK to `source_version_id` | D/S |
| `provenance_ids` | General report metadata evidence rows | ids | empty | 0..* | FK to `provenance` | T |

The stale embedded PDF `/Title` value `RCS N° 126` is never sufficient for either
identity field. A disagreement is retained as a discrepancy, not repaired here.

## `report_month` (`ReportMonthAggregate`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `report_month_id` | Stable row identity for one metric observation | id | — | 1 | Key | T |
| `report_id` | Report containing the observation | id | — | 1 | FK to `report` | T |
| `metric_original` | Source metric/indicator label, open vocabulary | orig str | — | 1 | P for source-reported rows | S |
| `indicator_basis` | `source_reported` or `derived` | pipeline control | — | 1 | Determines conditional fields | T |
| `value` | Indicator value (numeric or source status/text); missing stays null | scalar | N | 0..1 | P when source-reported; derivation trace when derived | S/D |
| `unit_original` | Published unit label | orig str | N | 0..1 | P when present | S |
| `scope_original` | Published population, denominator, or coverage scope for the indicator | orig str | N | 0..1 | P when source-reported and present; never inferred | S |
| `provenance_ids` | Evidence IDs attached to the observation; required for `source_reported`, optional for `derived` when source context is directly relevant | ids | N when not supplied | 0..* | FK to `provenance`; derived rows still require derivation metadata and upstream IDs | T |
| `derivation_name` | Named calculation for a derived indicator | str | required for derived | 0..1 | Paired with version and upstream IDs | D |
| `derivation_version` | Version of calculation code/rule | str | required for derived | 0..1 | Run metadata | D |
| `upstream_record_ids` | Records consumed by a derived calculation | ids | required for derived | 0..* | FK-like links to event/record IDs | D |

A source-reported narrative/table value and an event-table calculation are separate
rows even if their labels and values match. No derived row silently replaces a published
indicator.

## `case` (`ConflictCase`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_id` | Canonical case key; historical identity parts are deferred | id | — | 1 | Referenced by case-month and link tables | T |
| `official_code` | Official case code when present | orig str | N | 0..1 | P through case observations | S |
| `canonical_name` | Current canonical display name, if adjudicated | norm str | N | 0..1 | P/identity adjudication | D |
| `identity_method` | Identity resolution method label | str | N | 0..1 | Run/adjudication evidence | D |
| `identity_confidence` | Confidence in canonical identity, `[0,1]` | float | N | 0..1 | Candidate/adjudication evidence | D |
| `provenance_ids` | Evidence supporting case-level identity | ids | empty | 0..* | FK to `provenance` | T |

## `case_name` (`CaseName`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_name_id` | Observation key | id | — | 1 | Key | T |
| `case_id` | Linked canonical case | id | — | 1 | FK to `case` | T/D |
| `report_id` | Report where name appears | id | — | 1 | FK to `report` | T |
| `name_original` | Exact observed case name | orig str | — | 1 | P | S |
| `name_normalized` | Comparison/search normalization | norm str | N | 0..1 | Derived from original; never replaces it | D |
| `provenance_ids` | Name evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_month` (`CaseMonth`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_month_id` | One case observation in one report month | id | — | 1 | Key | T |
| `case_id` | Canonical case key | id | — | 1 | FK to `case` | T/D |
| `report_id` | Report containing observation | id | — | 1 | FK to `report` | T |
| `reference_period` | Observation month, `YYYY-MM` | parsed/source period | — | 1 | FK-like to report period | S/D |
| `official_code_original` | Source case code | orig str | N | 0..1 | P | S |
| `name_original` | Source case name in this month | orig str | N | 0..1 | P | S |
| `stock_status_original` | Published active/latent or source equivalent | orig str | N | 0..1 | P | S |
| `stock_status_normalized` | Versioned comparison status | norm str | N | 0..1 | Method/crosswalk evidence | D |
| `phase_original` | Published phase label | orig str | N | 0..1 | P | S |
| `phase_normalized` | Versioned phase derivative | norm str | N | 0..1 | Method/crosswalk evidence | D |
| `conflict_type_original` | Published conflict type | orig str | N | 0..1 | P | S |
| `conflict_type_normalized` | Versioned harmonized type | norm str | N | 0..1 | Taxonomy version required | D |
| `case_description_original` | Structural/problem description as published in this report; not timeless canonical text | orig str | N | 0..1 | P; distinct from monthly facts | S |
| `transitions` | Transition evidence records, not stock flags | tuple of records | empty | 0..* | Each nested record requires provenance | S/D |
| `monthly_facts_original` | Published monthly facts text | orig str | N | 0..1 | P | S |
| `provenance_ids` | Observation evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_reported_indicator` (`CaseReportedIndicator`)

This table stores a source-reported value scoped to one case-month. It is not an
event and cannot contain a derived value.

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_reported_indicator_id` | Stable indicator observation key | id | — | 1 | Key | T |
| `case_month_id` | Case-month observation | id | — | 1 | FK to `case_month` | T |
| `case_id` | Case identity | id | — | 1 | FK to `case` | T |
| `report_id` | Report containing the value | id | — | 1 | FK to `report` | T |
| `metric_original` | Exact source label/open metric name | orig str | — | 1 | P | S |
| `value` | Explicit source value; null is invalid for an existing row | scalar | — | 1 | P | S |
| `unit_original` | Published unit | orig str | N | 0..1 | P when visible | S |
| `scope_original` | Published case/time/population scope | orig str | N | 0..1 | P; never inferred | S |
| `provenance_ids` | Exact source evidence | ids | — | 1..* | FK to `provenance` | T |

## `location` (`Location`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `location_id` | Location key | id | — | 1 | Referenced by `case_location` | T |
| `location_text_original` | Complete source location string | orig str | — | 1 | P | S |
| `department_original` | Source department component | orig str | N | 0..1 | P when explicitly stated | S |
| `province_original` | Source province component | orig str | N | 0..1 | P when explicitly stated | S |
| `district_original` | Source district component | orig str | N | 0..1 | P when explicitly stated | S |
| `population_center_original` | Source town/community/population-center component | orig str | N | 0..1 | P when explicitly stated | S |
| `department_normalized` | Harmonized department | norm str | N | 0..1 | Crosswalk/version evidence | D |
| `province_normalized` | Harmonized province | norm str | N | 0..1 | Crosswalk/version evidence | D |
| `district_normalized` | Harmonized district | norm str | N | 0..1 | Crosswalk/version evidence | D |
| `population_center_normalized` | Harmonized population center | norm str | N | 0..1 | Crosswalk/version evidence | D |
| `ubigeo` | Administrative code | norm str | N | 0..1 | Crosswalk evidence | D |
| `match_method` | Geographic matching method | str | N | 0..1 | Run/crosswalk evidence | D |
| `crosswalk_version` | Version of geographic crosswalk | str | N | 0..1 | Run metadata | D |
| `match_confidence` | Match confidence, `[0,1]` | float | N | 0..1 | Candidate/review evidence | D |
| `provenance_ids` | Location evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_location` (`CaseLocation`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_location_id` | Case-location observation key | id | — | 1 | Key | T |
| `case_id` | Case key | id | — | 1 | FK to `case` | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `location_id` | Location key | id | — | 1 | FK to `location` | T |
| `relationship_original` | Source description of location relationship | orig str | N | 0..1 | P | S |
| `provenance_ids` | Association evidence | ids | empty | 0..* | FK to `provenance` | T |

## `actor` (`Actor`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `actor_id` | Actor key; historical linkage deferred | id | — | 1 | Referenced by `case_actor` | T |
| `name_original` | Exact actor name | orig str | — | 1 | P | S |
| `name_normalized` | Comparison normalization | norm str | N | 0..1 | Never replaces original | D |
| `actor_type_original` | Source actor type | orig str | N | 0..1 | P | S |
| `actor_type_normalized` | Optional harmonized type | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `provenance_ids` | Actor evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_actor` (`CaseActor`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_actor_id` | Case-actor observation key | id | — | 1 | Key | T |
| `case_id` | Case key | id | — | 1 | FK to `case` | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `actor_id` | Actor key | id | — | 1 | FK to `actor` | T/D |
| `role_original` | Source role/relationship | orig str | N | 0..1 | P | S |
| `role_normalized` | Harmonized role | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `provenance_ids` | Association evidence | ids | empty | 0..* | FK to `provenance` | T |

## `demand` (`Demand`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `demand_id` | Demand key | id | — | 1 | Referenced by `case_demand` | T |
| `text_original` | Full demand text when source-visible | orig str | N | 0..1 | P | S |
| `text_normalized` | Search/analysis normalization | norm str | N | 0..1 | Never replaces original | D |
| `theme_original` | `Tema de demanda social` | orig str | N | 0..1 | P | S |
| `theme_normalized` | Optional theme derivative | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `category_original` | Distinct `Categoría` column | orig str | N | 0..1 | P; never inferred from theme | S |
| `category_normalized` | Optional category derivative | norm str | N | 0..1 | Only after an approved taxonomy | D |
| `competent_entity_original` | `Entidad pública competente` | orig str | N | 0..1 | P; distinct from theme/category | S |
| `provenance_ids` | Demand evidence | ids | empty | 0..* | FK to `provenance` | T |

At least one original source dimension among text, theme, category, and competent
entity is required. Structured-only rows never receive synthesized demand prose.

## `case_demand` (`CaseDemand`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_demand_id` | Case-demand observation key | id | — | 1 | Key | T |
| `case_id` | Case key | id | — | 1 | FK to `case` | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `demand_id` | Demand key | id | — | 1 | FK to `demand` | T |
| `provenance_ids` | Association evidence | ids | empty | 0..* | FK to `provenance` | T |

## `protest_event` (`ProtestEvent`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `protest_event_id` | Event key distinct from cases | id | — | 1 | Referenced by `case_protest_link` and violence links | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `event_date` | Parsed event date when justified | date | N | 0..1 | P/source-date evidence | S/D |
| `event_date_original` | Exact source date/date phrase | orig str | N | 0..1 | P | S |
| `event_date_precision_original` | Open source precision label (day/month/period/etc.) | orig str | N | 0..1 | P | S |
| `measure_type_original` | Source protest/action measure | orig str | N | 0..1 | P | S |
| `measure_type_normalized` | Optional harmonized measure | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `actors_text_original` | Source actor text | orig str | N | 0..1 | P | S |
| `location_text_original` | Source event location text | orig str | N | 0..1 | P | S |
| `demand_text_original` | Source event demand text | orig str | N | 0..1 | P | S |
| `violence_explicit` | Whether source explicitly links violence | bool | N | 0..1 | P | S |
| `provenance_ids` | Event evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_protest_link` (`CaseProtestLink`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `case_protest_link_id` | Link key | id | — | 1 | Key | T |
| `case_id` | Case key | id | — | 1 | FK to `case` | T |
| `protest_event_id` | Protest event key | id | — | 1 | FK to `protest_event` | T |
| `link_method` | Evidence method (open method label) | str | — | 1 | P required | D/S |
| `confidence` | Link confidence, `[0,1]` | float | N | 0..1 | Candidate/review evidence | D |
| `provenance_ids` | Link evidence | ids | — | 1..* | FK to `provenance`; nonempty required | T |

## `violence_event` (`ViolenceEvent`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `violence_event_id` | Event key | id | — | 1 | Key | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `protest_event_id` | Linked protest when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `event_date` | Parsed event date | date | N | 0..1 | P/source-date evidence | S/D |
| `event_date_original` | Exact source date phrase | orig str | N | 0..1 | P | S |
| `event_date_precision_original` | Open source date precision | orig str | N | 0..1 | P | S |
| `violence_type_original` | Source event type/label | orig str | N | 0..1 | P | S |
| `description_original` | Exact event description | orig str | N | 0..1 | P | S |
| `fatalities_total` | Reported total fatalities | int / persons | N | 0..1 | P; unknown remains null | S |
| `injured_total` | Reported total injured | int / persons | N | 0..1 | P; unknown remains null | S |
| `casualty_components` | Component records by source group | tuple of records | empty | 0..* | Parent/event P; nested labels original | S |
| `provenance_ids` | Event evidence | ids | empty | 0..* | FK to `provenance` | T |

## `dialogue_event` (`DialogueEvent`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `dialogue_event_id` | Dated dialogue occurrence key | id | — | 1 | Key | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `mediation_process_id` | Parent continuing mediation process | id | N | 0..1 | FK to `mediation_process`; if populated, `provenance_ids` is required | D/S |
| `event_date` | Parsed event date | date | N | 0..1 | P | S/D |
| `event_date_original` | Source date phrase | orig str | N | 0..1 | P | S |
| `event_date_precision_original` | Open source date precision | orig str | N | 0..1 | P | S |
| `description_original` | Event description | orig str | N | 0..1 | P | S |
| `status_original` | Event status as stated | orig str | N | 0..1 | P | S |
| `provenance_ids` | Event evidence | ids | empty | 0..* | FK to `provenance` | T |

## `mediation_process` (`MediationProcess`)

This is an optional evidence-linked longitudinal identity. Similar source labels do
not establish continuity.

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `mediation_process_id` | Continuing mediation identity | id | — | 1 | Referenced only after linkage review | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence required | S/D |
| `canonical_label` | Reviewed display label | norm str | N | 0..1 | Identity adjudication | D |
| `identity_method` | Open linkage method | str | — | 1 | Review/run evidence | D |
| `identity_confidence` | Linkage confidence `[0,1]` | float | N | 0..1 | Candidate/review evidence | D |
| `provenance_ids` | Identity/link evidence | ids | — | 1..* | Required for every process identity | T |

## `mediation_observation` (`MediationObservation`)

One report-local source block. It preserves `Fecha de inicio`, `Estado`, `Solicitante`,
`Actores`, `Tipo de mediación`, `Mediador`, `Descripción de caso`, `Demandas`, and
progress without inventing cross-report continuity.

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `mediation_observation_id` | Source-observation key | id | — | 1 | Key | T |
| `report_id` | Report containing the block | id | — | 1 | FK to `report` | T |
| `mediation_process_id` | Optional reviewed process link | id | N | 0..1 | Evidence required if populated | D/S |
| `case_id` | Optional case link | id | N | 0..1 | Evidence required if populated | D/S |
| `start_date` | Parsed start date | date | N | 0..1 | P/source-date evidence | S/D |
| `start_date_original` | Exact `Fecha de inicio` | orig str | N | 0..1 | P | S |
| `start_date_precision_original` | Open source precision | orig str | N | 0..1 | P | S |
| `status_original` | Published mediation `Estado` | orig str | N | 0..1 | P | S |
| `requester_original` | `Solicitante` | orig str | N | 0..1 | P | S |
| `actors_original` | `Actores` | orig str | N | 0..1 | P | S |
| `mediation_type_original` | `Tipo de mediación` | orig str | N | 0..1 | P | S |
| `mediator_original` | `Mediador` | orig str | N | 0..1 | P | S |
| `case_description_original` | `Descripción de caso` | orig str | N | 0..1 | P | S |
| `demands_original` | Source demand text in block | orig str | N | 0..1 | P | S |
| `progress_original` | Source `Estado situacional` progress narrative | orig str | N | 0..1 | P | S |
| `provenance_ids` | Observation/link evidence | ids | empty | 0..* | Links require nonempty evidence | T |

## `agreement` (`Agreement`)

`text_original` is the source `Acuerdos`/agreement text. It is deliberately separate from
`compliance_progress_original` (`Avances de cumplimiento`). Responsibility and deadline
remain source strings and are not actor links or interpreted dates.

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `agreement_id` | Agreement/follow-up record key | id | — | 1 | Key | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `agreement_date` | Parsed agreement date | date | N | 0..1 | P | S/D |
| `agreement_date_original` | Exact source date phrase | orig str | N | 0..1 | P | S |
| `agreement_date_precision_original` | Open source date precision | orig str | N | 0..1 | P | S |
| `case_description_original` | Published agreement-module `Descripción del caso` | orig str | N | 0..1 | P | S |
| `text_original` | Published agreement text (`Acuerdos`) | orig str | N | 0..1 | P | S |
| `compliance_progress_original` | Published implementation progress (`Avances de cumplimiento`) | orig str | N | 0..1 | P | S |
| `responsibility_original` | Explicit responsible organization/person text | orig str | N | 0..1 | P; no actor FK implied | S |
| `deadline_original` | Explicit deadline text | orig str | N | 0..1 | P; no date interpretation implied | S |
| `provenance_ids` | Agreement evidence | ids | empty | 0..* | FK to `provenance` | T |

## `dp_action` (`DefensoriaAction`)

Broad action labels remain in `action_type_original`. The optional intervention fields
retain a source hierarchy such as broad category -> subtype without a closed historical
taxonomy.

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `dp_action_id` | Defensoría action key | id | — | 1 | Key | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `action_date` | Parsed action date | date | N | 0..1 | P | S/D |
| `action_type_original` | Broad source action type | orig str | N | 0..1 | P | S |
| `intervention_category_original` | Broad intervention category | orig str | N | 0..1 | P | S |
| `intervention_category_normalized` | Optional category derivative | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `intervention_subtype_original` | Source subtype | orig str | N | 0..1 | P | S |
| `intervention_subtype_normalized` | Optional subtype derivative | norm str | N | 0..1 | Taxonomy/version evidence | D |
| `intervention_hierarchy_original` | Ordered source labels from broad to specific | tuple of orig str | empty | 0..* | P for each retained path | S |
| `description_original` | Action description | orig str | N | 0..1 | P | S |
| `provenance_ids` | Action evidence | ids | empty | 0..* | FK to `provenance` | T |

## `alert` (`Alert`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `alert_id` | Alert key | id | — | 1 | Key | T |
| `report_id` | Report key | id | — | 1 | FK to `report` | T |
| `case_id` | Linked case when evidenced | id | N | 0..1 | Explicit link evidence | S/D |
| `alert_date` | Parsed alert date | date | N | 0..1 | P | S/D |
| `text_original` | Full alert text | orig str | N | 0..1 | P | S |
| `alert_type_original` | Source alert type | orig str | N | 0..1 | P | S |
| `risk_original` | Source risk label/description | orig str | N | 0..1 | P | S |
| `location_text_original` | Alert location text | orig str | N | 0..1 | P | S |
| `provenance_ids` | Alert evidence | ids | empty | 0..* | FK to `provenance` | T |

## `case_relationship` (`CaseRelationship`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `relationship_id` | Directed relationship key | id | — | 1 | Key | T |
| `case_id_from` | Source/earlier case key | id | — | 1 | FK to `case` | T |
| `case_id_to` | Target/later/related case key | id | — | 1 | FK to `case` | T |
| `relationship_type_original` | Exact relationship label, open vocabulary | orig str | — | 1 | P required | S |
| `relationship_type_normalized` | Optional interpretation (continuation/merge/split/etc.) | norm str | N | 0..1 | Adjudication/taxonomy evidence | D |
| `effective_period` | Period relationship applies | `YYYY-MM` | N | 0..1 | P | S/D |
| `confidence` | Candidate confidence, `[0,1]` | float | N | 0..1 | Candidate/review evidence | D |
| `provenance_ids` | Relationship evidence | ids | — | 1..* | FK to `provenance`; nonempty required | T |

## `provenance` (`ProvenanceRecord`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `provenance_id` | Evidence row key | id | — | 1 | Referenced by material fields | T |
| `object_type` | Registry entity containing field | id/str | — | 1 | FK-like model name | T |
| `object_id` | Record containing field | id | — | 1 | FK-like record key | T |
| `field_name` | Material field supported | id/str | — | 1 | Must match model field | T |
| `source_report_id` | Report where evidence occurs | id | — | 1 | FK to `report` | T |
| `source_sha256` | Hash of cited source bytes | hash | — | 1 | Must match source version | T |
| `source_page` | 1-based page | int / page | N | 0..1 | Page locator | S/T |
| `source_section` | Section heading | orig str | N | 0..1 | Locator | S |
| `source_table` | Table label | orig str | N | 0..1 | Locator | S |
| `source_bbox` | PDF coordinate rectangle | nested numeric | N | 0..1 | Locator | T |
| `source_span` | Character span in extracted text | nested int | N | 0..1 | Locator | T |
| `source_text` | Exact cited evidence text | orig str | N | 0..1 | Evidence payload | S |
| `extraction_method` | Controlled pipeline method | enum | — | 1 | Run metadata; model calls require invocation | T |
| `extractor_name` | Tool/extractor name | str | N | 0..1 | Run metadata | T |
| `extractor_version` | Tool version | str | N | 0..1 | Run metadata | T |
| `parser_version` | Parser/rule version | str | N | 0..1 | Run metadata | T |
| `model_invocation` | Provider/model/prompt/schema/span/output identity | nested record | N | 0..1 | Required only for probabilistic method | T |
| `confidence` | Extraction confidence, `[0,1]` | float | N | 0..1 | Review/candidate evidence | D |
| `review_status` | Review workflow status | str | N | 0..1 | Manual-review key where applicable | T/D |

## `discrepancy` (`DiscrepancyRecord`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `discrepancy_id` | Discrepancy key | id | — | 1 | Key | T |
| `report_id` | Report containing conflict | id | — | 1 | FK to `report` | T |
| `discrepancy_type` | `PARSER_ERROR`, `SOURCE_INCONSISTENCY`, etc. | controlled enum | — | 1 | Evidence requirements depend on type | T |
| `severity` | Review severity | str | N | 0..1 | QA/review workflow | T/D |
| `value_a` | First retained value | scalar | N | 0..1 | `provenance_a_ids` | S/D |
| `provenance_a_ids` | Evidence for first value | ids | required except missing-evidence type | 0..* | FK to `provenance` | T |
| `value_b` | Second retained value | scalar | N | 0..1 | `provenance_b_ids` for conflicts | S/D |
| `provenance_b_ids` | Evidence for second value | ids | required for source/cross-source conflicts | 0..* | FK to `provenance` | T |
| `status` | Open/reviewed/resolved workflow state | str | N | 0..1 | Review/adjudication | T/D |
| `classification_rationale` | Why discrepancy class applies | orig str | — | 1 | Auditable decision text | T/S |
| `parser_version` | Parser under which found | id/str | — | 1 | Run metadata | T |
| `review_id` | Linked manual review | id | N | 0..1 | FK to `manual_review` | T |

Report-269 candidate notes for M2 are retained in
`docs/source_discrepancy_reconnaissance.md`; they are not parser corrections.

## `manual_review` (`ManualReviewItem`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `review_id` | Review queue key | id | — | 1 | Referenced by discrepancies/adjudications | T |
| `object_type` | Entity under review | id/str | — | 1 | Model registry name | T |
| `object_id` | Record under review | id | N | 0..1 | FK-like object key | T |
| `issue_type` | Review issue class, open | id/str | — | 1 | Workflow | T |
| `candidate_payloads_json` | Immutable candidate documents | JSON strings | empty | 0..* | Evidence IDs also required | T/D |
| `machine_suggestion_json` | Optional machine suggestion | JSON | N | 0..1 | Must pair with invocation | D |
| `machine_model_invocation` | Model identity for suggestion | nested record | N | 0..1 | Required iff suggestion exists | T |
| `evidence_provenance_ids` | Evidence for review | ids | — | 1..* | FK to `provenance` | T |
| `neighboring_periods` | Context months | `YYYY-MM` tuple | empty | 0..* | Context only | T/S |
| `review_status` | Queue status | id/str | — | 1 | Workflow | T |
| `second_review_required` | Whether independent review is required | bool | default false | 1 | QA policy | T |
| `created_at` | Time created with timezone | datetime | — | 1 | Run/audit log | T |
| `parser_version` | Parser context | id/str | — | 1 | Run metadata | T |

## `adjudication` (`AdjudicationRecord`)

| Field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `adjudication_id` | Append-only decision key | id | — | 1 | Key | T |
| `review_id` | Review item decided | id | — | 1 | FK to `manual_review` | T |
| `decision_original` | Reviewer’s source-language decision | orig str | — | 1 | Evidence IDs | S/T |
| `decision_action` | Structured action label | id/str | — | 1 | Workflow, not historical taxonomy | T |
| `decision_payload_json` | Optional structured decision payload | JSON | N | 0..1 | Evidence IDs | T/D |
| `rationale` | Decision rationale | orig str | — | 1 | Evidence IDs | T/S |
| `reviewer_id` | First reviewer | id | — | 1 | Audit identity | T |
| `decided_at` | Decision time with timezone | datetime | — | 1 | Audit log | T |
| `parser_version` | Parser context | id/str | — | 1 | Run metadata | T |
| `evidence_provenance_ids` | Evidence supporting decision | ids | — | 1..* | FK to `provenance` | T |
| `supersedes_adjudication_id` | Prior decision superseded | id | N | 0..1 | Append-only chain | T |
| `second_reviewer_id` | Independent second reviewer | id | N | 0..1 | Must differ from first | T |
| `second_reviewed_at` | Second review time with timezone | datetime | N | 0..1 | Paired with reviewer | T |

## Supporting nested records

| Record / field | Meaning / representation | Orig/norm | Null | Mult | Provenance / relationship | Origin |
|---|---|---|---|---|---|---|
| `TransitionEvidence.transition_original` | Exact transition phrase | orig str | — | 1 | P required by transition | S |
| `TransitionEvidence.transition_normalized` | Optional interpretation | norm str | N | 0..1 | Review/taxonomy evidence | D |
| `TransitionEvidence.provenance_ids` | Transition evidence | ids | — | 1..* | FK to `provenance` | T |
| `CasualtyComponent.component_original` | Source casualty group | orig str | — | 1 | Parent violence evidence | S |
| `CasualtyComponent.fatalities` | Group fatalities | int/persons | N | 0..1 | Parent violence P | S |
| `CasualtyComponent.injured` | Group injured | int/persons | N | 0..1 | Parent violence P | S |
| `SourceBBox.x0`, `y0`, `x1`, `y1` | Page-coordinate rectangle | float/points | — | 1 each | Nested locator | T |
| `SourceSpan.start`, `end` | Half-open text span offsets | int/characters | — | 1 each | Nested locator | T |
| `ModelSetting.name` | Inference setting name | id/str | — | 1 | Nested invocation | T |
| `ModelSetting.value` | Inference setting value | scalar | N allowed | 1 | Nested invocation | T |
| `ModelInvocation.provider` | Model provider | id/str | — | 1 | Required for probabilistic provenance | T |
| `ModelInvocation.model` | Model identifier | id/str | — | 1 | Required for probabilistic provenance | T |
| `ModelInvocation.prompt_version` | Prompt version | id/str | — | 1 | Required for probabilistic provenance | T |
| `ModelInvocation.output_schema_version` | Output schema identity | id/str | — | 1 | Required for probabilistic provenance | T |
| `ModelInvocation.source_span_hash` | Hash of sent source span | hash | — | 1 | Cache/reproducibility key | T |
| `ModelInvocation.output_hash` | Hash of model output | hash | — | 1 | Cache/reproducibility key | T |
| `ModelInvocation.inference_settings` | Settings tuple | nested tuple | empty | 0..* | Run metadata | T |

## Controlled pipeline values

`IndicatorBasis` has `source_reported` and `derived`. `ReportIdentityEvidenceType` has
`document_visible`, `official_metadata`, and `embedded_pdf_title`; the model validator
rejects the last value when it is the only support for a report number or reference
period. `ExtractionMethod` and `DiscrepancyType` are documented in
`docs/09_provenance_standard.md` and `docs/10_source_discrepancy_protocol.md`.
These controls do not close any historical Spanish classification.
