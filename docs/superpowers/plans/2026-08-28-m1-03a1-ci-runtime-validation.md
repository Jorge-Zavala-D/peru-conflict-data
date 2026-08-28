# M1-03A.1 CI Runtime Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every cross-version and cross-platform M1-03A validation claim
correspond to the interpreter and operating system that actually execute the
tests.

**Architecture:** Keep the acquisition subsystem and all reviewed plans/schemas
unchanged. Bind each Ubuntu matrix job to its `setup-python` interpreter through
`UV_PYTHON`, assert the active runtime before quality checks, pass the matrix
version explicitly to Pyright, and add one Windows runner job that executes
mandatory native-handle smoke coverage plus the complete test suite.

**Tech Stack:** GitHub Actions, uv 0.11.28, Python 3.12/3.13, Pyright strict mode,
pytest, Windows native directory-handle primitives.

**Spec:** `docs/superpowers/specs/2026-08-28-m1-03a-source-acquisition-design.md`
plus the research-owner M1-03A.1 release-gate instruction dated 2026-08-28.

## Global Constraints

- Keep `.python-version` and `pyproject.toml`'s local Python 3.12 default.
- Do not change either acquisition pilot, any scientific/discovery/acquisition
  schema snapshot, authorization scope, targets, paths, hashes, or bounds.
- Do not add or instantiate a live transport and do not write to Dropbox.
- PR #3 stays open and unmerged; M1-03B, M1-04, and M2 remain prohibited.
- Native Windows smoke tests use only pytest temporary directories and synthetic
  bytes; they require no symlink or junction privilege.

---

### Task 1: Native Windows handle-path smoke coverage

**Files:**
- Create: `tests/unit/test_acquisition_windows_native.py`

**Interfaces:**
- Consumes: `DirectoryLease.open_child_exclusive`, `open_child_read`,
  `rename_child_no_replace`, `unlink_child`, and
  `stage_copy_and_publish_no_replace`.
- Produces: two Windows-only tests that capability-skip only when the operating
  system is not Windows.

- [ ] **Step 1: Record the existing RED validation gap**

  Preserve the exact run `33181050511` evidence: the nominal 3.13 job says
  `Using CPython 3.12.3` and pytest says `Python 3.12.3`; no Windows job exists.

- [ ] **Step 2: Add the native directory-lease smoke test**

  Create a normal bound directory, create/write/read one child through the lease,
  rename it without replacement, verify the renamed bytes and resolved parent,
  unlink it, and assert the directory is empty.

- [ ] **Step 3: Add the native publication smoke test**

  Publish a synthetic `%PDF-` object from a temporary-system directory through a
  temporary raw `.staging` directory to `reports/`, assert `PUBLISHED`, exact
  bytes, an empty staging directory, and a destination resolved beneath raw.

- [ ] **Step 4: Run the smoke tests on local Windows**

  Run:
  `uv run pytest tests/unit/test_acquisition_windows_native.py -vv`

  Expected: both tests run and pass; neither is skipped on Windows.

### Task 2: Exact Python-version and platform CI binding

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: GitHub matrix `python-version`, `actions/setup-python`, `UV_PYTHON`,
  Pyright `--pythonversion` and `--pythonplatform`.
- Produces: truthful `quality (3.12)`, `quality (3.13)`, and exact
  `windows-acquisition-safety` jobs.

- [ ] **Step 1: Bind uv to the matrix interpreter**

  Set job-level `UV_PYTHON: ${{ matrix.python-version }}` for Ubuntu and `3.12`
  for Windows. Keep frozen sync and `.python-version` unchanged.

- [ ] **Step 2: Add an executable runtime assertion**

  Immediately after frozen sync, run Python through uv, print the expected and
  active major/minor plus executable, and exit nonzero unless they match.

- [ ] **Step 3: Make Pyright version claims explicit**

  Run strict Pyright for Windows and Linux with both
  `--pythonversion ${{ matrix.python-version }}` and the corresponding
  `--pythonplatform` argument.

- [ ] **Step 4: Add actual Windows execution**

  Add job `windows-acquisition-safety` on `windows-latest`, set up Python 3.12,
  frozen-sync with `UV_PYTHON=3.12`, assert the runtime, run the dedicated native
  smoke file with `-vv`, run the complete pytest suite, then run schema drift and
  repository data-policy checks.

- [ ] **Step 5: Validate the workflow locally**

  Run `uv run pre-commit run check-yaml --all-files` and inspect the rendered diff.
  Expected: valid YAML, unchanged quality job names, and exact Windows job name.

### Task 3: Documentation, complete validation, and remote proof

**Files:**
- Modify: `docs/m1_03a_completion_report.md`

**Interfaces:**
- Consumes: local Windows evidence, final GitHub job logs, dry-run output, and
  Dropbox read-only inventories.
- Produces: accurate validation-language distinctions and PR metadata receipts.

- [ ] **Step 1: Update stable documentation**

  Distinguish local Windows execution, Ubuntu Python 3.12/3.13 runtime tests,
  version/platform-specific static analysis, and actual GitHub Windows execution.
  Keep exact final run IDs in PR metadata to avoid a receipt-commit loop.

- [ ] **Step 2: Run both local runtime environments**

  Frozen-sync and run the complete suite with Python 3.12 and 3.13, run all four
  Pyright version/platform combinations, then restore the local 3.12 environment.

- [ ] **Step 3: Run the complete repository quality gate**

  Run Ruff format/lint, schema drift, repository and staged-blob policy, complete
  pytest, pre-commit, and Git diff checks. Expected: no failures or drift.

- [ ] **Step 4: Replay the real M1-03A dry run read-only**

  Take before/after inventories, run the pinned v2 plan once, assert 10 reports,
  20 URLs, 45 actions, zero network requests and Dropbox writes, verify the cache
  digest, rehash all 11 sources, and confirm all protected/derived boundaries.

- [ ] **Step 5: Obtain independent exact-snapshot review**

  Review the final diff read-only for truthful 3.13 binding, real Windows native
  execution, and any weakening of production behavior.

- [ ] **Step 6: Commit, push, and verify PR #3**

  Push one focused correction to `codex/m1-03-source-acquisition`; wait for all
  three exact-head jobs and inspect logs for actual runtimes, runner OS, native
  smoke execution, full acquisition coverage, and skip counts. Leave PR #3 open
  and unmerged.
