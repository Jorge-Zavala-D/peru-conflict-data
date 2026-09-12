# Peru social conflict data

Research-data infrastructure for a defensible historical reconstruction of Peru's Defensoría del Pueblo Social Conflicts Monitoring System, April 2004-present.

Status: **Milestone 1 and M2-01 are complete; M2-02 human annotation has not started.**

Jorge has approved the
[source-neutral discovery execution policy](docs/m2_02_discovery_execution_policy.md).
The [approval record](config/benchmark/m2_02_owner_approval_v1.yaml) approves the policy contract
only. M2-02A owner readiness is approved: all 15 decisions are closed in
[the readiness approval](config/benchmark/m2_02a_owner_readiness_approval_v1.yaml).
Readiness v3 and evidence index v5 bind that approval. This permits preparation of
a separate launch gate only; no real issuance, annotation, production locking,
human gold, Dropbox execution writes or parser work is authorized.
See the [execution candidate](docs/m2_02_annotation_execution_protocol.md) and
[coordinator checklist](docs/m2_02_coordinator_checklist.md). No normative discovery-start scoring is approved,
and the final M3 gate remains unapproved.
The write-once canonical M1 identity/coverage package exists at
`06_validation/m1_corpus_manifest/v0.2.0/`. It establishes 247 numbered reports and
247 months without mapping conflicts while preserving 287 factual gaps and 50 owner
adjudications. This is corpus identity/coverage closure, not full PDF acquisition:
authoritative byte completeness remains false and 237 report bytes remain deferred.
Scientific v0.3.0 and benchmark v0.1.0 remain immutable historical approvals.
The [owner-authorized date correction](docs/scientific_schema_v0_3_0_to_v0_3_1_date_correction.md)
advances the active readiness contracts to scientific v0.3.1 and benchmark v0.1.1;
only action/alert source dates and precision replace parsed dates in object matching.
The unlaunched run and neutral package/issuance identities explicitly bind those active
contracts; the current source-neutral evidence index is v5. Historical indexes remain intact.
The active run pins the exact critical-field set and the separately recorded M2-02A.1E
date-pair ratification, which authenticates the interpretation document.
The date-pair ratification alone did not approve readiness; the separate 15-decision
record now approves readiness only, never annotation launch. The two machine pilot aids were verified only for
protocol coherence and remain non-gold. M2 human gold does not exist and M2-02 human annotation has
not started. Object-family thresholds remain deferred until the post-M2-03 gate
revision; the current M3 gate v1 remains an unapproved owner-review draft.

## Storage boundary

Git contains code, tests, schemas, configuration, small synthetic fixtures, and documentation. Official reports, the administrative workbook, extracted artifacts, canonical Parquet/DuckDB, validation evidence, operational acquisition manifests, and releases live outside Git beneath `CONFLICT_DATA_ROOT` (operational manifests under `01_raw/manifests/`).

```powershell
$env:CONFLICT_DATA_ROOT = 'X:\path\to\Defensoria Social Conflicts Database'
uv sync --frozen --group dev
uv run pytest
```

Do not point `CONFLICT_DATA_ROOT` at this repository. Routine code refuses writes beneath `00_external`, `01_raw`, and `99_archive`.

Start with [AGENTS.md](AGENTS.md), [project charter](docs/01_project_charter.md),
[architecture](docs/04_architecture.md), [canonical model](docs/07_canonical_data_model.md),
the [execution plan](docs/execution_plan.md), the
[M1 discovery protocol](docs/m1_official_source_discovery_protocol.md), the
[M1-01/M1-02.2 review report](docs/m1_01_02_review_report.md), and the
[inventory receipt](docs/m1_02_1_inventory_receipt.md). M1-03A is documented in the
[acquisition checkpoint](docs/m1_acquisition_checkpoint.md) and
[completion report](docs/m1_03a_completion_report.md). M1-03B.1 is described by the
[live-comparison protocol](docs/m1_03b_live_comparison_protocol.md) and its
[readiness report](docs/m1_03b1_completion_report.md). M1-04 owner review is
summarized in the [M1-04B completion report](docs/m1_04b_completion_report.md), and
the transition is recorded in the [M1 completion report](docs/m1_completion_report.md).
None of these documents authorizes a new acquisition. M2-01 pilot packets are blank
protocol-review forms, not human gold.
