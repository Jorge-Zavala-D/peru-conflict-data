# Peru social conflict data

Research-data infrastructure for a defensible historical reconstruction of Peru's Defensoría del Pueblo Social Conflicts Monitoring System, April 2004-present.

Status: **M1-01/M1-02.2 merged; M1-03A implements and verifies a zero-network,
zero-Dropbox dry run; M1-03B remains prohibited pending separate approval**. The
repository does not yet contain a historical dataset or benchmark parser.
Scientific schema `v0.2.0` is the M1 working baseline; technical contracts are
discovery `v0.3.0` and acquisition `v0.1.0`. Every earlier schema directory remains
immutable. Reports 260-269 are inventoried source material for a future independently
annotated benchmark. No new raw file was acquired, and M1-04/M2 remain out of scope.

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
[completion report](docs/m1_03a_completion_report.md); neither document authorizes
M1-03B network execution.
