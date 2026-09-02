# M2-01 benchmark metric specification

Version 0.1.0 defines metrics only. No parser is evaluated in M2-01.

## Evaluation population and leakage

Evaluation uses locked, adjudicated human gold from the fixed held-out reports in
`config/benchmark/m2_partition_v1.yaml`. Protocol-pilot reports 264 and 269 are excluded from blind
scores. Parser-development reports may support diagnostics but never substitute for held-out gates.
Extra predicted objects count as false positives; missing predictions count as false negatives.

## Case detection

Match a predicted case observation to gold by the benchmark's reviewed observation ID, or by an
approved deterministic report/page/block key when IDs are assigned after segmentation. Precision is
`TP/(TP+FP)` and recall is `TP/(TP+FN)`; an empty denominator scores 1 only when both relevant sets
are empty. The later M3 target is at least 99% for both.

## Exact source-page attribution

For each matched critical object/field, the predicted sorted page tuple must equal the gold tuple.
Partial overlap is incorrect, missing prediction is incorrect, and extra pages are incorrect. Report
SHA must already match the benchmark source. Later target: at least 99%.

## Exact critical-field value accuracy

The comparison key is `(unit_id, domain_object_type, field_name, cardinality_index)`. State and
canonical raw JSON value must both match. Thus `not_reported`, `not_applicable`, `explicit_zero`,
`source_ambiguous`, and a missing prediction are distinct outcomes. Original strings compare
Unicode code points exactly after JSON decoding; no whitespace, accent, case, or punctuation repair
occurs inside the metric. Duplicate comparison keys in either gold or predictions are rejected
rather than collapsed or resolved by input order. Dates compare the source-original string and
precision separately. Later target: at least 99% for the owner-approved critical set.

## Structured/multi-object matching

Objects are compared as multisets, so duplicate source rows are not collapsed. Matching signatures
are canonical JSON of these source-preserving keys:

| Object | Deterministic matching fields |
|---|---|
| actor/case actor | `name_original`, `role_original` |
| demand/case demand | `text_original`, `theme_original`, `category_original`, `competent_entity_original` |
| location/case location | full original location plus visible administrative levels and relationship |
| protest event | date original/precision, measure type, actors, location, demand |
| violence event | date original/precision, type, description, casualty totals and ordered component multiset |
| dialogue event | date original/precision, description, status |
| mediation observation | source page/block locator, start date, status, type, mediator, description, progress |
| agreement | date original/precision, agreement text, responsibility, deadline, compliance progress |
| Defensoría action | date, type/category/subtype hierarchy, description |
| alert | date, type, risk, location, text |

For a multiset signature, true positives are the minimum gold/predicted multiplicity; remaining
predicted multiplicity is false positive and remaining gold multiplicity false negative. Match-field
changes require a versioned metric specification and owner approval.

## Missingness and ambiguity

- Explicit zero is correct only against explicit-zero gold with numeric JSON `0`.
- Domain null is not directly scored; the benchmark state explaining it is scored.
- `not_reported` and `not_applicable` never match each other.
- `source_ambiguous` is not scored as any single candidate value unless adjudication resolves it.
- `illegible_uninspectable` and `structurally_unavailable` remain coverage states and are excluded
  from value denominators only by an owner-approved coverage rule, never silently.

## Provenance completeness

The denominator is every critical gold field requiring evidence. A field is complete only when the
prediction names the exact report SHA and page and supplies the required section plus span/bbox/table
cell according to the handbook. Report the proportion complete and counts by missing component.
Later M3 acceptance requires provenance completeness for every critical prediction even when the
aggregate page-accuracy threshold is met.

## Deterministic implementation

`peru_conflicts.benchmark.metrics` implements binary detection, exact page accuracy, exact state/value
accuracy, duplicate-aware multiset matching, and provenance completeness. Unit tests use synthetic
sets only: perfect output, false positives, false negatives, page mismatch, missing versus zero,
not-applicable, duplicate objects, and incomplete provenance. No source annotation or parser output
is embedded in these tests.
