# Peru social conflict data

Research-data infrastructure for a defensible historical reconstruction of Peru's Defensoría del Pueblo Social Conflicts Monitoring System, April 2004-present.

Status: **M1-01/M1-02 read-only discovery complete; M1-03 acquisition checkpoint pending**. The repository does not yet contain a historical dataset or a benchmark parser. The source contract for discovery work is schema `v0.2.0`; `schemas/v0.1.0/` is retained as the immutable M0 snapshot. Reports 260-269 are inventoried source material for a future, independently annotated modern benchmark. No new raw files were acquired, and M2 remains out of scope.

## Storage boundary

Git contains code, tests, schemas, configuration, small synthetic fixtures, and documentation. Official reports, the administrative workbook, extracted artifacts, canonical Parquet/DuckDB, validation evidence, operational acquisition manifests, and releases live outside Git beneath `CONFLICT_DATA_ROOT` (operational manifests under `01_raw/manifests/`).

```powershell
$env:CONFLICT_DATA_ROOT = 'X:\path\to\Defensoria Social Conflicts Database'
uv sync --frozen --group dev
uv run pytest
```

Do not point `CONFLICT_DATA_ROOT` at this repository. Routine code refuses writes beneath `00_external`, `01_raw`, and `99_archive`.

Start with [AGENTS.md](AGENTS.md), [project charter](docs/01_project_charter.md), [architecture](docs/04_architecture.md), [canonical model](docs/07_canonical_data_model.md), the [execution plan](docs/execution_plan.md), the [M1 discovery protocol](docs/m1_official_source_discovery_protocol.md), and the [M1-01/M1-02 review report](docs/m1_01_02_review_report.md). M1-03 requires the separate [acquisition checkpoint](docs/m1_acquisition_checkpoint.md).
