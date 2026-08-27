# Milestone 0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the complete Milestone 0 repository foundation without changing raw sources or beginning corpus discovery.

**Architecture:** Keep immutable source evidence outside Git behind a validated `CONFLICT_DATA_ROOT`; implement strict source-preserving Pydantic models and small deterministic infrastructure modules; generate JSON Schemas mechanically; make every repository gate runnable without private data.

**Tech Stack:** Python 3.12-3.13, uv, Pydantic 2, PyYAML, pytest, Ruff, Pyright, pre-commit, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-milestone-0-foundation-design.md`

## Global Constraints

- Milestone 0 only; do not crawl, extract, OCR, geocode, link the historical corpus, or call paid models.
- Preserve `LICENSE` byte-for-byte and keep PDFs, workbooks, Parquet, DuckDB, images, OCR, credentials, and logs out of Git.
- Treat `00_external` and `01_raw` as read-only in routine code; never infer zero from missing data.
- Keep original Spanish values beside normalized derivatives and preserve contradictions as evidence.
- Do not commit, push, open a pull request, or merge.

---

### Task 1: Repository and dependency foundation

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.gitattributes`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`
- Create: `src/peru_conflicts/__init__.py`
- Generate: `uv.lock`

**Interfaces:**
- Produces a Python package importable as `peru_conflicts` and locked `dev` dependency group.
- CI consumes `uv.lock` with `uv sync --frozen --group dev`.

- [ ] Add a minimal runtime dependency set: Pydantic and PyYAML; keep PDF/OCR/geospatial/semantic packages deferred.
- [ ] Configure Ruff, Pyright, pytest, coverage, and package build metadata for Python 3.12 and 3.13.
- [ ] Generate `uv.lock` with `uv lock`, then verify `uv sync --frozen --group dev` succeeds.
- [ ] Configure pre-commit and CI to run format check, lint, typing, unit/integration tests, schema drift check, and the Git data-policy guard.

### Task 2: Safe external-data-root contract

**Files:**
- Test: `tests/unit/test_paths.py`, `tests/integration/test_config.py`
- Create: `src/peru_conflicts/paths.py`, `src/peru_conflicts/config.py`
- Create: `config/project.yaml`, `config/paths.example.yaml`, `.env.example`

**Interfaces:**
- Produces `DataPaths.resolve(repo_root: Path, data_root: Path | None = None) -> DataPaths`.
- Produces `DataPaths.require_writable(path: Path) -> Path` and `load_project_config(path: Path) -> ProjectConfig`.

- [ ] Write tests proving missing roots fail, the Git repository is rejected, traversal is rejected, expected directories are validated, raw/external targets are refused, derived targets are accepted, and temporary synthetic roots work.
- [ ] Run the focused tests and confirm they fail because the interfaces do not exist.
- [ ] Implement only the validation and classification needed for those tests.
- [ ] Run the focused tests and full unit suite until green.

### Task 3: Hashing and stable identity

**Files:**
- Test: `tests/unit/test_hashing.py`, `tests/unit/test_ids.py`
- Create: `src/peru_conflicts/hashing.py`, `src/peru_conflicts/ids.py`

**Interfaces:**
- Produces `sha256_file(path: Path) -> str`, `hash_mapping(value: Mapping[str, object]) -> str`, and `stable_id(kind: str, *parts: object) -> str`.

- [ ] Write literal-vector tests for an empty file, a known byte fixture, mapping key-order independence, identifier repeatability, namespace separation, and explicit distinction between `None`, empty string, and zero.
- [ ] Run the focused tests and confirm expected import failures.
- [ ] Implement streaming SHA-256, canonical JSON mapping hashes, and UUID5-based stable IDs.
- [ ] Run focused and full tests until green.

### Task 4: Versioned domain and provenance models

**Files:**
- Test: `tests/unit/test_models.py`, `tests/unit/test_schema_export.py`
- Create: `src/peru_conflicts/models/common.py`, `src/peru_conflicts/models/domain.py`, `src/peru_conflicts/models/__init__.py`
- Create: `src/peru_conflicts/schema_export.py`, `scripts/export_schemas.py`
- Generate: `schemas/v0.1.0/*.schema.json`

**Interfaces:**
- Produces strict Pydantic classes exported through `peru_conflicts.models.MODEL_REGISTRY`.
- Produces `export_json_schemas(output_dir: Path) -> list[Path]` with deterministic filenames and formatting.

- [ ] Write tests for unknown-field rejection, original/normalized separation, stock/transition separation, nullable casualty semantics, case/protest separation, provenance bounds, discrepancy classes, versioned adjudication, relationship openness, and complete model registry coverage.
- [ ] Run the focused tests and confirm they fail for missing models.
- [ ] Implement strict models with schema version `0.1.0`; avoid closed historical taxonomy enums.
- [ ] Export schemas, test deterministic output and schema validity, and run the model suite until green.

### Task 5: Run identity and structured logging

**Files:**
- Test: `tests/unit/test_run_metadata.py`, `tests/unit/test_json_logging.py`
- Create: `src/peru_conflicts/run_metadata.py`, `src/peru_conflicts/json_logging.py`

**Interfaces:**
- Produces `capture_run_metadata(...) -> RunMetadata` and `JsonLineFormatter`.
- Run metadata records Git commit/dirty state, hashes for config/lock/schema/inputs, parser and schema versions, environment versions, and optional model/prompt invocations.

- [ ] Write tests for clean/dirty Git metadata inputs, stable content hashes, absent optional model metadata, populated probabilistic metadata, UTC timestamps, and one-valid-JSON-object-per-log-line behavior.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement metadata capture and logging without writing outside a caller-supplied derived log destination.
- [ ] Run focused and full tests until green.

### Task 6: Repository data-policy guard and complete project structure

**Files:**
- Test: `tests/unit/test_repository_guard.py`
- Create: `src/peru_conflicts/repository_guard.py`, `scripts/check_git_data_policy.py`
- Create/adapt: `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `CITATION.cff`, `Makefile`
- Create/adapt: `.agents/skills/*/SKILL.md`, `.codex/config.toml.example`, `.codex/agents/*.toml`
- Create/adapt: `docs/01_*.md` through `docs/31_*.md`, `docs/adr/*.md`, and directory README files.

**Interfaces:**
- Produces `find_policy_violations(paths: Iterable[Path], repo_root: Path, max_bytes: int) -> list[Violation]` and a zero/nonzero CLI.

- [ ] Write tests showing PDF/XLSX/Parquet/DuckDB/credential-like files and oversized files are rejected while small source, schema, fixture, and documentation files are accepted.
- [ ] Run focused tests and confirm the guard is absent.
- [ ] Implement the guard and wire it into pre-commit and CI.
- [ ] Adapt all seed documentation and Codex examples to current verified syntax; custom agents require `developer_instructions`, project config remains example-only, and no duplicate MCP installation is proposed.
- [ ] Run focused tests, schema export check, and repository guard until green.

### Task 7: Live inventories, ADRs, execution plan, and completion evidence

**Files:**
- Create: `docs/live_resource_inventory.md`, `docs/codex_capability_inventory.md`, `docs/bootstrap_audit.md`, `docs/execution_plan.md`, `docs/milestone0_completion_report.md`
- Create/adapt: `docs/adr/001_*.md` through `docs/adr/010_*.md`

**Interfaces:**
- Documents report exact commands, timestamps, hashes, source limitations, acceptance criteria, and decisions requiring Jorge's approval.

- [ ] Record GitHub/Dropbox live inventory, reports 260-269 hashes/pages/native-text evidence, workbook hash/sheet metadata, permissions, and differences from the bootstrap snapshot.
- [ ] Record the actual callable tool surface separately from configured-but-unverified plugins/MCPs, including authentication/scope limitations and missing local binaries.
- [ ] Expand ADRs for path safety, schema/provenance versioning, run identity, and dependency minimization.
- [ ] Decompose M1-M4 into small work packages with dependencies, inputs, outputs, tests, acceptance criteria, human review, tools, compute/cost risk, and parallelization; sketch M5-M12.
- [ ] Re-hash all eleven raw/external benchmark files and compare them with the pre-implementation baseline.
- [ ] Run `uv lock --check`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `uv run pytest`, `uv run python scripts/export_schemas.py --check`, and `uv run python scripts/check_git_data_policy.py`.
- [ ] Review `git diff --check`, `git status --short`, file sizes, and license hash; record exact results and remaining approval decisions without committing.
