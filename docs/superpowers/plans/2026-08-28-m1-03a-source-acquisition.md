# M1-03A Source Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed acquisition engine and prove its dry run makes zero
network requests and zero Dropbox writes.

**Architecture:** A new `peru_conflicts.acquisition` namespace owns a separately
versioned acquisition schema. The executable CLI exposes only preflight and
dry-run; future network and promotion logic is reachable only through injected
interfaces and a separate authorization gate, and is tested with synthetic
bytes and temporary directories.

**Tech Stack:** Python 3.12-3.13, Pydantic 2, PyYAML, pytest, Ruff, Pyright,
pre-commit, standard-library hashing/filesystem/URL/robots primitives.

**Spec:** `docs/superpowers/specs/2026-08-28-m1-03a-source-acquisition-design.md`

## Global Constraints

- No PDF or ZIP body retrieval and no live transport implementation.
- No write anywhere under `CONFLICT_DATA_ROOT`, including manifests or staging.
- Pilot v1 and every scientific/discovery schema snapshot remain byte-identical.
- Pilot v2 remains `authorization_status: not_authorized`.
- Tests precede production behavior and must be observed failing for the intended
  reason before the minimal implementation is added.
- One canonical writer owns shared plans, schemas, configuration, and code.
- The final PR remains open and unmerged.

---

### Task 1: Pin the Merged Baseline and Acquisition Schema Namespace

**Files:**
- Create: `config/acquisition_pilots/m1_03_reports_260_269_v2.yaml`
- Create: `src/peru_conflicts/acquisition/models.py`
- Create: `src/peru_conflicts/acquisition/plan.py`
- Create: `src/peru_conflicts/acquisition/schema_export.py`
- Create: `schemas/acquisition/v0.1.0/*.schema.json`
- Modify: `scripts/export_schemas.py`
- Test: `tests/unit/test_acquisition_plan.py`
- Test: `tests/unit/test_acquisition_schema_export.py`
- Modify: `tests/unit/test_discovery_schema_export.py`

**Interfaces:**
- Produces: `load_reviewed_pilot_plan(path, required_sha256) -> LoadedPilotPlan`.
- Produces: `rendered_acquisition_schemas() -> dict[str, str]`.
- Preserves: discovery v0.3 tree digest
  `00cbf40848c24d24eea454e25682061d5725abe01c24c6479ffa6d30fffd821b`.

- [x] **Step 1: Write failing plan and immutability tests.**

```python
loaded = load_reviewed_pilot_plan(V2_PATH, required_sha256=V2_FILE_SHA256)
assert loaded.plan.plan_id == "m1-03-reports-260-269-v2"
assert loaded.plan.baseline_receipt_git_commit == MERGED_M1_SHA
assert loaded.plan.authorization_status == "not_authorized"
assert sha256_file(V1_PATH) == V1_FILE_SHA256
assert schema_tree_digest(DISCOVERY_V030) == DISCOVERY_V030_TREE_SHA256
```

- [x] **Step 2: Run the focused tests and observe missing acquisition modules fail.**

Run: `uv run pytest tests/unit/test_acquisition_plan.py tests/unit/test_acquisition_schema_export.py -q`

- [x] **Step 3: Add the v2 plan and strict models.**

The loader hashes raw bytes before YAML parsing, validates the model, then checks
the reviewed raw-file, semantic, and ordered-target fingerprints. URL validation
requires HTTPS, exact approved hosts, no user information, and port absent or
443.

- [x] **Step 4: Add deterministic acquisition schema export without touching discovery output.**

Generate acquisition `v0.1.0` schemas for the v2 plan, dry-run result,
authorization artifact, attempt receipt, and ledger record. Extend the top-level
schema check to require both existing registries plus acquisition.

- [x] **Step 5: Run focused and existing schema tests green.**

Run: `uv run pytest tests/unit/test_acquisition_plan.py tests/unit/test_acquisition_schema_export.py tests/unit/test_discovery_schema_export.py -q`

### Task 2: Implement the Read-Only Dry-Run Preflight

**Files:**
- Create: `src/peru_conflicts/acquisition/preflight.py`
- Create: `src/peru_conflicts/acquisition/cli.py`
- Create: `src/peru_conflicts/acquisition/__init__.py`
- Create: `scripts/acquire_official_sources.py`
- Test: `tests/unit/test_acquisition_preflight.py`
- Test: `tests/integration/test_acquisition_dry_run.py`

**Interfaces:**
- Produces: `run_dry_run_preflight(...) -> DryRunResult`.
- Produces: `write_dry_run_result(path, result, repo_root, data_root) -> None`.
- Consumes no transport and exposes only `--mode dry-run`.

- [x] **Step 1: Write failing tests for ordered validation and side-effect closure.**

```python
before = snapshot_tree(data_root)
result = run_dry_run_preflight(
    plan_path=plan_path,
    required_plan_sha256=plan_sha,
    repo_root=repo_root,
    data_root=data_root,
)
assert result.network_requests == 0
assert result.dropbox_writes == 0
assert snapshot_tree(data_root) == before
assert not (data_root / "01_raw" / ".staging").exists()
```

Cover wrong plan digest before YAML parsing, unsafe roots, traversal/reparse
escapes, a late tenth-file mismatch, receipt mismatch, non-ancestor baseline,
output aliases, interrupted cache output, and unknown network/force/authorize
arguments.

- [x] **Step 2: Run focused tests RED.**

Run: `uv run pytest tests/unit/test_acquisition_preflight.py tests/integration/test_acquisition_dry_run.py -q`

- [x] **Step 3: Implement stable source fingerprinting and protected reads.**

Open each source once, count and hash its bytes, compare before/descriptor/after
metadata, and require both logical and resolved paths inside `01_raw/reports`.
Verify the baseline receipt in the worktree and with
`git show <baseline>:<receipt>` plus an ancestor check.

- [x] **Step 4: Implement deterministic dry-run actions and cache-only atomic output.**

The result contains relative paths only and no timestamp. Validate the output
path before creating its parent; write an adjacent unique temporary file,
`fsync`, replace only the ignored cache result, and remove the owned temporary
file in `finally`.

- [x] **Step 5: Run focused tests GREEN and execute a synthetic dry run.**

Run: `uv run pytest tests/unit/test_acquisition_preflight.py tests/integration/test_acquisition_dry_run.py -q`

### Task 3: Implement Authorization, Transport Policy, and Streaming Validation

**Files:**
- Create: `src/peru_conflicts/acquisition/policy.py`
- Create: `src/peru_conflicts/acquisition/engine.py`
- Test: `tests/unit/test_acquisition_policy.py`
- Test: `tests/unit/test_acquisition_engine.py`

**Interfaces:**
- Produces: `require_network_authorization(plan, artifact, transport_factory)`.
- Produces: `AcquisitionClient`, which requires an injected `StreamingTransport`.
- No concrete/live transport is implemented.

- [x] **Step 1: Write failing authorization and authority tests.**

```python
called = False
with pytest.raises(NetworkAuthorizationRequired):
    require_network_authorization(plan, None, factory)
assert called is False
```

Reject HTTP, non-default ports, user information, arbitrary subdomains,
off-host redirects, loops, and hop six before transport use.

- [x] **Step 2: Run the focused policy tests RED.**

Run: `uv run pytest tests/unit/test_acquisition_policy.py -q`

- [x] **Step 3: Implement the minimal authorization gate, attempt budget, serial scheduler, and URL policy.**

Debit the 60-attempt budget before every robots, initial, redirect, or retry
attempt. Ensure every actual attempt begins at least two seconds after the
previous one and a Retry-After value never shortens that interval.

- [x] **Step 4: Write and observe failing fake-transport streaming tests.**

Tests cover robots allow/deny, retry cap two, timeout 30, MIME before body,
Content-Length and total ceilings, identity encoding, status 200, exact `%PDF-`
prefix, chunk-independent SHA, truncated bodies, and interruption cleanup.

- [x] **Step 5: Implement header-first streaming into an owned system-temporary run directory.**

Every failure creates a typed receipt before the owned partial file is removed.
No raw path or operational ledger is touched.

- [x] **Step 6: Run policy and engine tests GREEN.**

Run: `uv run pytest tests/unit/test_acquisition_policy.py tests/unit/test_acquisition_engine.py -q`

### Task 4: Implement Disposition, Ledger, and Temporary Promotion Semantics

**Files:**
- Create: `src/peru_conflicts/acquisition/ledger.py`
- Create: `src/peru_conflicts/acquisition/storage.py`
- Test: `tests/unit/test_acquisition_ledger.py`
- Test: `tests/unit/test_acquisition_storage.py`

**Interfaces:**
- Produces: `decide_disposition(existing_sha256, observed_sha256)`.
- Produces: in-memory append-only ledger plus canonical serializer bytes.
- Produces: `stage_copy_and_publish_no_replace(...)`, usable only with explicit
  temporary test roots in M1-03A.

- [x] **Step 1: Write failing disposition and idempotency tests.**

Equal bytes create one byte object and multiple URL observations; different
bytes return `stop_for_review` with no storage call; repeated URL/hash pairs do
not duplicate observations.

- [x] **Step 2: Write failing storage and recovery tests.**

Cover same-name/different-byte, copy interruption, stage rehash mismatch,
different devices, destination-exists races, no overwrite, and owned-file-only
cleanup.

- [x] **Step 3: Run focused tests RED.**

Run: `uv run pytest tests/unit/test_acquisition_ledger.py tests/unit/test_acquisition_storage.py -q`

- [x] **Step 4: Implement minimal append-only records and atomic no-replace publication.**

Use `os.rename` only where the platform guarantees no replacement; otherwise
use same-filesystem link publication plus unlink of the unique stage. Never use
`os.replace` for a raw object.

- [x] **Step 5: Run focused tests GREEN.**

Run: `uv run pytest tests/unit/test_acquisition_ledger.py tests/unit/test_acquisition_storage.py -q`

### Task 5: Harden Repository Policy and Document M1-03A

**Files:**
- Modify: `src/peru_conflicts/repository_guard.py`
- Modify: `.gitignore`
- Test: `tests/unit/test_repository_guard.py`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/m1_acquisition_checkpoint.md`
- Create: `docs/m1_03a_completion_report.md`

**Interfaces:**
- Repository guard rejects ZIP in both worktree and staged index blobs.
- Durable documentation states M1-03A is dry-run-only and M1-03B remains
  prohibited.

- [x] **Step 1: Add failing worktree and staged ZIP guard tests.**

- [x] **Step 2: Run guard tests RED, add the minimal ZIP policy, and rerun GREEN.**

Run: `uv run pytest tests/unit/test_repository_guard.py -q`

- [x] **Step 3: Run the real v2 dry run against the read-only Dropbox root.**

Snapshot all protected hashes and active-layer counts before and after. Emit the
machine-readable result only beneath ignored repository `.cache` and record its
byte count/SHA-256 in the completion report.

- [x] **Step 4: Update milestone documentation without recording a self-referential CI result.**

### Task 6: Full Verification, Independent Review, and PR

**Files:**
- Review all M1-03A changes.

**Interfaces:**
- Produces an exact tested commit and an open, unmerged pull request.

- [x] **Step 1: Run the complete local gate.**

```powershell
uv sync --frozen --group dev
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run python scripts/export_schemas.py --check
uv run python scripts/check_git_data_policy.py
uv run pre-commit run --all-files
```

Also run staged-index policy checks, schema-tree digest checks, Git diff checks,
and a final eleven-source Dropbox hash comparison.

- [ ] **Step 2: Obtain independent read-only review of the exact integrated diff.**

Review focuses on dry-run network/data-root side effects, authorization bypass,
hash/disposition correctness, recovery, no-overwrite publication, and source
version preservation. Fix every Critical or Important issue and rerun the full
gate.

- [ ] **Step 3: Commit and push the exact branch, then open one PR to `main`.**

Use normal preconfigured Git authentication. Do not inspect a credential store or
bypass connector permissions.

- [ ] **Step 4: Wait for exact-head `quality (3.12)` and `quality (3.13)`.**

Stop with the PR open and unmerged. Do not begin M1-03B or M1-04.
