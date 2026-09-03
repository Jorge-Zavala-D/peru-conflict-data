# M2-01 benchmark metric specification

Version 0.1.0 defines metrics only. No parser is evaluated in M2-01.

## Evaluation population and leakage

Evaluation uses locked, adjudicated human gold from the fixed held-out reports in
`config/benchmark/m2_partition_v1.yaml`. Protocol-pilot reports 264 and 269 are excluded from blind
scores. Parser-development reports may support diagnostics but never substitute for held-out gates.
Extra predicted objects count as false positives; missing predictions count as false negatives.
`evaluate_benchmark()` is the only normative M3 gate. The individual metric functions remain
diagnostics and cannot by themselves establish a final benchmark result.

## Case detection

Match a predicted case observation to gold by its source-bounded annotation-unit ID, or by an
approved deterministic report/page/block key when IDs are assigned after segmentation. The
project's longitudinal `case.case_id` is excluded from M2 source-value scoring and remains an M4
linkage artifact. Precision is
`TP/(TP+FP)` and recall is `TP/(TP+FN)`; an empty denominator scores 1 only when both relevant sets
are empty. The later M3 target is at least 99% for both.

## Exact source-page attribution

For each matched critical object/field, the predicted sorted page tuple must equal the gold tuple.
Partial overlap is incorrect, missing prediction is incorrect, and extra pages are incorrect. Report
SHA must already match the benchmark source. Later target: at least 99%.

## Conditional matched-field diagnostic

The comparison key is `(unit_id, domain_object_type, field_name, cardinality_index)`. State and
canonical raw JSON value must both match. Thus `not_reported`, `not_applicable`, `explicit_zero`,
`source_ambiguous`, and a missing prediction are distinct outcomes. Original strings compare
Unicode code points exactly after JSON decoding; no whitespace, accent, case, or punctuation repair
occurs inside the metric. Duplicate comparison keys in either gold or predictions are rejected
rather than collapsed or resolved by input order. This diagnostic evaluates gold keys only and is
not a final gate because unrelated extra prediction keys are outside its denominator.

## Mandatory strict critical-field gate

The normative evaluator compares every unique key in the complete gold and prediction populations.
It reports `correct`, `incorrect`, `missing`, `extra`, `gold_total`, `prediction_total`,
`strict_denominator`, and `strict_exact_accuracy`. The formula is:

`strict_denominator = gold_total + extra`

`strict_exact_accuracy = correct / strict_denominator`

Incorrect and missing expected values already occupy positions in `gold_total`; unsupported scalar
fields and unsupported cardinality indexes extend the denominator. Therefore a parser cannot obtain
a perfect result by predicting all gold values plus hallucinated keys. Duplicate keys are rejected.
Dates compare the source-original string and precision separately. Later target: at least 99% for
the owner-approved source-value critical set.

## Structured/multi-object matching

Objects are compared as multisets, so duplicate source rows are not collapsed. Matching signatures
are canonical JSON of these source-preserving keys:

| Object | Deterministic matching fields |
|---|---|
| actor/case actor | `name_original`, `actor_type_original`, `role_original` |
| demand/case demand | `text_original`, `theme_original`, `category_original`, `competent_entity_original` |
| location/case location | full original location plus visible administrative levels and relationship |
| protest event | date original/precision, measure type, actors, location, demand |
| violence event | date original/precision, type, description, casualty totals and ordered component multiset |
| dialogue event | date original/precision, description, status |
| mediation observation | annotation-unit ID, start date/original precision, status, requester, actors, type, mediator, case description, demands, progress |
| agreement | date original/precision, agreement text, responsibility, deadline, compliance progress |
| Defensoría action | date, type/category/subtype hierarchy, description |
| alert | date, type, risk, location, text |
| case observation | source-bounded annotation-unit ID |

For a multiset signature, true positives are the minimum gold/predicted multiplicity; remaining
predicted multiplicity is false positive and remaining gold multiplicity false negative. Match-field
changes require a versioned metric specification and owner approval. The normative evaluator
requires complete populations for every registered object type and exposes precision/recall and
TP/FP/FN separately by type. Omitting an object population is an error rather than an empty score.
Each object passed to the normative evaluator must contain exactly its versioned flattened
projection keys: missing keys and unreviewed extra keys are rejected before signatures are built.

## Instance-aware coverage and independent annotation

Each submission declares a report-local object inventory keyed by annotation unit, object type, and
cardinality index. Required field names on each declaration expand into exact annotation slots. A
locked submission is valid only when every declared slot has exactly one explicit annotation state;
silent omissions and undeclared extra slots are rejected. A gold coverage receipt uses the same
reviewed inventory, so five declared actors require coverage of all five actor instances.

Annotators may declare different inventories. `validate_independent_submissions()` requires distinct
submission and annotator IDs, the same annotation unit and partition role, and two locked current
submissions. It reports object-instance count mismatches without forcing either annotator to adopt
the other's inventory. The caller supplies the versioned submission history; a locked submission
with a locked successor is no longer current. Draft, explicitly superseded, and non-current locked
submissions cannot form an A/B pair.

## Missingness and ambiguity

- Explicit zero is correct only against explicit-zero gold with numeric JSON `0`.
- Domain null is not directly scored; the benchmark state explaining it is scored.
- `not_reported` and `not_applicable` never match each other.
- `source_ambiguous` is not scored as any single candidate value unless adjudication resolves it.
- `illegible_uninspectable` and `structurally_unavailable` remain coverage states and are excluded
  from value denominators only by an owner-approved coverage rule, never silently.

## Evidence scoring

The denominator is every critical source-value slot requiring evidence. `EvidenceRequirement`
records the exact report ID and number, source SHA, exact page tuple, allowed section, and allowed
evidence granularities.
`evaluate_evidence_requirements()` operates on actual `EvidenceAnchor` objects and separately counts
missing evidence, wrong report ID/number, missing/wrong SHA, missing/extra pages, missing/wrong
section, invalid granularity, and missing typed locators.

Every complete anchor has the exact source SHA, page, and section plus the locator selected by its
declared granularity: SPAN requires `source_span`; BOUNDING_BOX requires `source_bbox`; TABLE_CELL
requires nonblank table, row, and column labels; PAGE_ONLY requires an allowed context and nonblank
rationale. A valid
span does not require a bbox, and a valid bbox does not require a span. Later M3 acceptance requires
complete evidence for every critical prediction even when aggregate page accuracy passes.

## Critical-field categories

`config/benchmark/m2_critical_fields_v1.yaml` separates human source-value accuracy from source-byte
custody prerequisites, technical matching keys, and typed evidence requirements. Custody failures
fail the benchmark precondition but do not enter the human transcription denominator. Technical
keys enable observation matching but are not source values.

## Deterministic implementation

`peru_conflicts.benchmark.metrics` implements the mandatory evaluator, strict field scoring,
binary detection, exact page accuracy, conditional matched-field accuracy, duplicate-aware multiset
matching, and typed evidence scoring. Unit tests use synthetic sets only: perfect output, all extra
prediction pathways, false negatives, page mismatch, missing versus zero, not-applicable, duplicate
objects, incomplete provenance, and object-inventory disagreement. No source annotation or parser
output is embedded in these tests.
