# Peru social conflict data

Research-data infrastructure for a defensible historical reconstruction of Peru's Defensoría del Pueblo Social Conflicts Monitoring System, April 2004-present.

Status: **Milestone 0 foundation**. This repository does not yet contain a historical dataset or a benchmark parser. Reports 260-269 are inventoried source material for a future, independently annotated modern benchmark.

## Storage boundary

Git contains code, tests, schemas, configuration, small synthetic fixtures, and documentation. Official reports, the administrative workbook, extracted artifacts, canonical Parquet/DuckDB, validation evidence, and releases live outside Git beneath `CONFLICT_DATA_ROOT`.

```powershell
$env:CONFLICT_DATA_ROOT = 'X:\path\to\Defensoria Social Conflicts Database'
uv sync --frozen --group dev
uv run pytest
```

Do not point `CONFLICT_DATA_ROOT` at this repository. Routine code refuses writes beneath `00_external`, `01_raw`, and `99_archive`.

Start with [AGENTS.md](AGENTS.md), [project charter](docs/01_project_charter.md), [architecture](docs/04_architecture.md), [canonical model](docs/07_canonical_data_model.md), and the [execution plan](docs/execution_plan.md).
