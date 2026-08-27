# Bootstrap audit

Audit date: 2026-08-27

## Audit basis

The proposed foundation was read from:

```text
99_archive/peru-conflict-data_codex-initialization/repo_seed
```

The archive was treated as read-only. Its package manifest contained 96 entries and all 96 matched their recorded SHA-256 hashes. The repository seed itself contained 90 scaffold files, including `AGENTS.md`, docs 00-31, six ADRs, six YAML configurations, sixteen JSON Schema stubs, eight project skills, five custom agents, and CI/pre-commit examples.

Live `main` was independently checked at commit `14b913f390056a74b598de08742be1120515dda6`; it contained only `README.md` and the MIT `LICENSE`. The seed was therefore evidence and design input, not live repository state.

## What was retained

- The research contract: primary-source priority, immutable hashes, explicit contradictions and missingness, status/transition separation, case/event separation, staged identity resolution, provenance, versioned adjudication, deterministic-first extraction, Parquet/DuckDB canon, and benchmark-before-scale.
- The external-data boundary and nine-zone Dropbox layout.
- The numbered documentation map and future milestone sequence.
- The eight narrowly scoped project skill concepts, now milestone-gated.
- The MIT software license, unchanged byte-for-byte.

## What required correction

| Seed element | Audit finding | M0 resolution |
|---|---|---|
| `pyproject.toml` | Broad optional dependency surface without implemented need | Reduced to Pydantic/PyYAML runtime plus a focused quality group |
| `uv.lock` | Absent | Generated a real lock with uv 0.11.28; frozen sync verified |
| `schemas/*.json` | Sixteen permissive stubs, generally allowing arbitrary properties | Replaced by generated strict schemas backed by typed models and retained under `schemas/v0.1.0/` |
| Domain coverage | Missing coherent joins for several material entities and insufficient review/provenance detail | Added 23 models/schemas spanning reports, cases, months, locations, actors, demands, protests, violence, dialogue, agreements, actions, alerts, relationships, provenance, discrepancies, and adjudication |
| Transition vocabulary | Did not clearly accommodate `became_latent` | Transition value stored as source-preserving, non-enumerated text; no historical vocabulary frozen in M0 |
| Missingness | Stubs could not enforce unknown/null semantics | Optional quantitative and normalized fields remain nullable; validation rejects invalid negative values and silent coercions |
| OCR configuration | Seed default enabled OCR too early | Default is disabled; future use must be page-specific and evidence-driven |
| Report regimes | Proposed historical era names risked hard-coding year folders as parser regimes | Replaced with an unassigned placeholder and evidence-required regime policy |
| `.codex/config.toml` | Example risked duplicating user capabilities and implied activation | Replaced by a minimal, non-active `.example`; activation requires trust and manual review |
| Custom agents | Five seed TOMLs did not match current required fields | Added `name`, `description`, and `developer_instructions`; constrained every project agent to read-only work |
| CI | Seed installed all optional extras and could not be reproduced without a lock | CI uses frozen minimal dependencies and pinned action commit SHAs |
| Implementation/tests | Package and tests were absent | Added safe paths, config, hashing, IDs, models, schema export, run metadata, JSON logging, repository guard, and unit/integration tests |
| Benchmark tests | No gold data exists yet | No fake benchmark tests added; benchmark directory remains documented and empty |

## Current Codex syntax audit

The seed was compared to official Codex documentation refreshed on 2026-08-27:

- Root/project `AGENTS.md` is the correct persistent instruction mechanism.
- Project skills are discoverable under `.agents/skills`.
- Custom agent definitions under `.codex/agents` use `name`, `description`, and `developer_instructions`.
- Agent concurrency is configured in an `[agents]` table.
- Repository-local `.codex/config.toml` is honored only after the project is trusted.
- Hooks and rules are distinct mechanisms; neither was activated at project scope in M0.

The current sources are [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [skills](https://learn.chatgpt.com/docs/build-skills), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced), [rules](https://learn.chatgpt.com/docs/agent-configuration/rules), and [hooks](https://learn.chatgpt.com/docs/hooks).

The eight local skills pass the current structural validator. They have not been claimed as behaviorally benchmarked. Behavioral testing is deferred to the first authorized milestone in which each workflow could actually run.

## Licensing audit

`LICENSE` remains the original MIT license with SHA-256:

```text
7838bc30d3402b894dc236cc3cc9a62933f3dd6ec71ff21f02f1044f38b5edff
```

MIT applies to repository software. It does not itself establish permission to redistribute Defensoría PDFs, `Base15-26.xlsx`, or every derivative dataset. Release rights remain an explicit approval item before M11.

## Scope audit

No full historical crawl, parser, OCR pass, entity resolution, taxonomy harmonization, geocoding, benchmark annotation, bulk model call, or canonical dataset was produced. M0 source inspection was limited to workbook metadata and reports 260-269. Empty historical year folders were not treated as discovered sources or parser regimes.

## Result

The archive seed was useful as a requirements map, but it was not executable or safe enough to copy verbatim. The M0 branch retains its research logic while replacing permissive stubs, speculative dependencies, and obsolete configuration assumptions with tested, versioned foundations. The live license and all raw-source bytes remain outside those adaptations.
