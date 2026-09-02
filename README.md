# Peru social conflict data

Research-data infrastructure for a defensible historical reconstruction of Peru's Defensoría del Pueblo Social Conflicts Monitoring System, April 2004-present.

Status: **M1-03 is complete and its one-shot authorization is spent. M1-04A
technical reconciliation is merged, M1-04B owner review is complete, and the 50
conservative adjudications are approved for the M1-04C.1 reviewed-manifest
contract.** Manifest technical schema `v0.2.0` adds explicit owner adjudication,
reviewed coverage, deferred acquisition, and write-once canonicalization semantics
while preserving the frozen v0.1.1 evidence bytes. Authoritative PDF byte-corpus
completeness remains false: reports 23–259 retain a 237-unit deferred acquisition
queue and every unresolved historical, byte-version, and opaque-filename condition
remains explicit. The canonical package is preview-only under ignored cache; no
package has been written to `06_validation/m1_corpus_manifest/v0.2.0/`. Scientific
schema `v0.2.0` remains the M1 working baseline, and M2 has not started.

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
summarized in the [M1-04B completion report](docs/m1_04b_completion_report.md).
None of these documents authorizes a new acquisition or the still-pending external
canonical package write.
