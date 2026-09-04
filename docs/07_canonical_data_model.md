# Canonical relational data model

Core tables are `report`, `report_month`, `case`, `case_name`, `case_month`,
`case_reported_indicator`, `location`, `case_location`, `actor`, `case_actor`, `demand`,
`case_demand`, `protest_event`, `case_protest_link`, `violence_event`, `dialogue_event`,
`mediation_observation`, `mediation_process`, `agreement`, `dp_action`, `alert`,
`case_relationship`, `provenance`, `discrepancy`, `manual_review`, and `adjudication`.
The current source contract is schema `v0.3.0`; generated `v0.1.0` and `v0.2.0`
directories remain immutable historical snapshots.

Official case code precedes deterministic multi-field linkage, probabilistic candidacy, and manual adjudication. Stock status and transition evidence are separate. Merge, split, rename, reactivation, and other relationships remain explicit and their historical vocabulary remains open until evidenced. Null is never coerced to zero.

M0 runtime validation is strict: unknown fields, value-type coercion, non-finite numbers, impossible calendar months, negative casualty counts, and whitespace-only identifiers fail. Conflict type, stock status, phase, transition, relationship, and other historical classifications retain open source-original strings beside optional normalized strings. Each transition is a source-original record with provenance rather than a closed set of booleans. Case/protest and case/case links require evidence IDs.

The Python model validators are the authoritative semantic validator. Generated JSON
Schema captures field types, bounds, identity-evidence guards, indicator-basis
conditions, demand-source presence, mediation-link provenance, closed pipeline
extraction methods, and the probabilistic-model metadata condition, but cross-field
coordinate ordering and certain type-specific discrepancy rules still require the
Python validator. Downstream non-Python consumers must run or reproduce those checks.
Source-reported report aggregates and derived calculations remain separate
`report_month` rows. Source-reported case values use `case_reported_indicator` and are
never derived from events. Report-local mediation observations remain separate from
optional evidence-linked longitudinal process identities.
