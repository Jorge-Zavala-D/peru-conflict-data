# Aggregate observation-month extension

`ReportMonthAggregateObservationV1` is a prospective additive subclass, not a
replacement for `ReportMonthAggregate`. Its explicit
`aggregate_contract=report_month_observation_v1` and separate extension schema
identify the new contract; inherited `schema_version=0.3.1`, the global registry
and `schemas/v0.3.1/` bytes remain unchanged.

`observation_period` is an optional real calendar month (`0001-01` through
`9999-12`, ASCII `YYYY-MM`). It is distinct from the containing report's reference
period and actual publication date. Null means unspecified, never an imputed
report month. No daily/annual/interval representation or universal date-order
rule is introduced.

Explicit legacy conversion is
`ReportMonthAggregateObservationV1.model_validate(legacy.model_dump())`;
it records the new contract with `observation_period=None`. The caller must retain
the conversion provenance. To qualify a month, a caller must separately bind the
original period label and its resolution rule to the specific observation's
source report/version, hash, occurrence and field evidence. Nonempty provenance
IDs and a valid month do not prove this support. The r3 coordinator enforces those
retained-data bindings and requires an explicit supported month for each targeted
R010 record.

The inherited source-reported/derived guards, strict scalar and unknown-field
refusal remain active. Source-reported counts are not recalculated indicators.
The new schema carries the legacy conditional guards and an explicit year-zero
refusal in addition to ASCII month syntax and exact length. Export/currentness
uses `export_observation_schemas`/`observation_schemas_are_current` and the existing
`scripts/export_schemas.py` route. Complete-tree exporter test fixtures now include
this extension; previously omitted batch-schema fixture exports are restored
without relaxing their refusal checks.

Affected consumers are the new explicit model import, additive schema exporter,
top-level schema-currentness script and bounded external r3 projector. Legacy
imports, loaders, registry-based consumers and frozen schema identities do not
switch automatically. Validation is technical staging, not human-reference
eligibility, scientific acceptance, discovery completeness or release approval.

The additive consumer `execution.aggregate_processing.parse_report_month_aggregate`
and read-only `scripts/validate_report_month.py` now explicitly select the supported
contract with a required base version. They do not change legacy loaders or infer
the extension from `schema_version` alone. See [the source-safe local recipe and
synthetic commands](ai_pi_local_recipe.md); this validation seam does not reproduce
the historical source-specific adjudication/reporting helper.

The standalone Draft 2020-12 tests validate the exported extension offline.
Its defaulted `schema_version` and `aggregate_contract` are not required schema
properties: schema validation neither inserts them nor selects a runtime route.
The consumer intentionally requires the explicit version and, for the extension,
the discriminator; omitting either is not fallback authority. Schema acceptance
does not establish source support or scientific approval.
