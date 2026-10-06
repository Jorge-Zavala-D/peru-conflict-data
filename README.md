# Peru social conflict data

Reproducible reconstruction of social conflict **as monitored and published** by Peru's
Defensoría del Pueblo, April 2004–present. It is not an enumeration of all conflict or a
causal evaluation of policy.

## Active route: AI_PI_RECONSTRUCTION_V1

Jorge adopted progressive agentic-AI construction with substantive source-based PI
review on 6 October 2026. The [strategy](docs/ai_pi_strategy.md) and
[typed decision](config/ai_pi/strategy_v1.json) select this route; the
[successor roadmap](docs/ai_pi_roadmap.md) replaces the old staffing-first dependency
chain for new work. Two external RAs, exhaustive double-human gold and retired
RA/native-containment diagnostics are **not prerequisites** for bounded AI development.
Their records remain historical, not retrospectively passed.

M0/M1 and M2-01 are completed foundations. The retained M1 closure records 247
numbered reports/months and 237 deferred report-byte acquisitions: corpus identity
closure is not full historical acquisition. Ten prepared modern PDFs are not the
whole corpus. Scientific schema **0.3.1** and benchmark/metric contract **0.1.1** are
current; historical versions remain immutable.

No external-RA annotation or exhaustive human gold was produced. This migration
implements a **plan-only entry** and synthetic validation, not a real extractor.
No real extraction, PI source review, frozen reference, regime qualification,
canonical promotion or data release is claimed. Existing RA kits/workspaces and
all historical evidence remain preserved.

## Next bounded task

Authorize the [first small real-source batch](docs/ai_pi_first_batch.md) after the
grouped tool/budget/context choices. Implement one thin extraction-to-review path;
retain initial predictions; present a source-first PI packet and separate assisted
adjudication packet. Do not start it automatically.

The [reference/evaluation protocol](docs/ai_pi_reference_evaluation_protocol.md)
separates technical checks, scoped PI reference, exploratory continuation,
regime-scale qualification and public release. Software passes and model agreement
never establish source accuracy or PI approval.

## Plan entry and storage

`scripts/plan_ai_pi.py --strategy config/ai_pi/strategy_v1.json --envelope <run.json>`
prints a non-executing plan with exact missing parameters. See the strategy document
for the installed-tool invocation. Even a complete envelope cannot dispatch a model,
acquire sources or promote/release data through this command.

Git holds recipes, source-safe synthetic fixtures, schemas and documentation.
`CONFLICT_DATA_ROOT` holds PDFs/workbooks, representations, responses, candidate and
review data, Parquet/DuckDB and releases. Routine code treats `00_external`,
`01_raw` and `99_archive` as non-writable. Do not put the data root in Git.

Start with [AGENTS](AGENTS.md), the [charter](docs/01_project_charter.md),
[architecture](docs/04_architecture.md), [canonical model](docs/07_canonical_data_model.md),
[roadmap](docs/ai_pi_roadmap.md) and [methods basis](docs/ai_pi_methods_basis.md).
The [original execution plan](docs/execution_plan.md), legacy acquisition,
annotation, OMA and launch protocols remain reproduction records; their explicit
versioned invocations keep their original closed behavior.

Development uses Python 3.12–3.13, Pydantic, pytest, Ruff and direct local Pyright.
Use existing installed tooling for this migration; no package synchronization is
authorized by its tests. Hosted CI remains a separate native/full-repository check.
