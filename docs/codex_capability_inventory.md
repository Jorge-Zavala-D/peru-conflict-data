# Codex capability and environment inventory

Inventory date: 2026-08-27 (Europe/Berlin)

This document distinguishes four states that are easy to conflate: installed on disk, configured, visible/callable in this task, and authentication actually verified. Configuration alone is not evidence that a service works.

## Instruction hierarchy inspected

| Layer | State |
|---|---|
| User/developer session instructions | Active for this task; included filesystem, safety, skills, memory, app, plugin, and subagent policies |
| Project instructions | Root `AGENTS.md`, finalized for the M0 contract |
| Project skills | Eight concise `.agents/skills/*/SKILL.md` guides, structurally validated; milestone-gated and not yet behaviorally benchmarked |
| Project custom agents | Five `.codex/agents/*.toml` definitions with current `name`, `description`, and `developer_instructions` fields; all are read-only by design |
| Project configuration | `.codex/config.toml.example` only; not activated |
| User rules | `%USERPROFILE%\.codex\rules\default.rules` present; no project `.rules` file |
| Hooks | No project hook configured or activated; an installed academic-research plugin ships optional hook assets, but they are not project policy |

Current official Codex documentation confirms that instructions may live in `AGENTS.md`, project skills in `.agents/skills`, custom subagents under `.codex/agents`, and repository-local `.codex/config.toml` is loaded only for trusted projects. The reviewed references are the official pages for [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [skills](https://learn.chatgpt.com/docs/build-skills), [configuration](https://learn.chatgpt.com/docs/config-file/config-reference), [rules](https://learn.chatgpt.com/docs/agent-configuration/rules), and [hooks](https://learn.chatgpt.com/docs/hooks).

The example project configuration is intentionally minimal: it sets only the concurrent-agent limit and does not duplicate user-level GitHub, Dropbox, Context7, Playwright, or documentation registrations. It must be reviewed and copied locally before activation.

## Task-visible Codex capabilities

### Verified and used during M0

| Capability | Evidence and scope |
|---|---|
| Local shell and filesystem | PowerShell commands ran in the Git checkout; Dropbox reads succeeded; project writes stayed in Git |
| Git | Local remote/branch/commit inspection and branch creation succeeded |
| GitHub app/connector | Authenticated profile and repository lookup succeeded; repository permissions were reported; no mutation used |
| Dropbox app/connector | Authenticated personal-account identity and complete root listing succeeded; only read operations used |
| Web/browser retrieval | Official Codex documentation and live action tags were retrieved; no corpus crawling |
| OpenAI Developer Docs skill | Current local manual was refreshed from official OpenAI documentation |
| Subagents | Parallel read-only capability, repository, Dropbox, schema, QA, and foundation reviews were available and used |
| Spreadsheet runtime | Bundled workbook reader opened `Base15-26.xlsx` read-only and verified sheet/range metadata |
| PDF runtime/system tools | `pdfinfo` and `pdftotext` inspected page counts and native-text availability; no OCR or conversions |

### Callable but not required for M0

- Context7 documentation lookup.
- Playwright browser MCP and the browser-control plugins.
- Zotero, SurveyCTO, Stata, NotebookLM, Node REPL, document, PDF, presentation, spreadsheet, visualization, site-building, and computer-use capabilities.
- GitHub pull-request, issue, review, workflow-log, and CI-artifact operations.

The presence of a callable tool does not authorize it. In particular, no external model service, bulk browser workflow, NotebookLM notebook, Stata session, or corpus-scale operation was used.

## Plugins, apps, connectors, and MCP servers

### Enabled user plugins found in configuration

`visualize`, `google-calendar`, `slack`, `sites`, `documents`, `pdf`, `spreadsheets`, `presentations`, `template-creator`, `computer-use`, `browser`, `chrome`, `ars-codex`, `outlook-email`, `codex-app-tools`, and `context7`.

Plugin cache providers present on disk were `ars-codex`, `codex-marketplace-global`, `context7-marketplace`, `openai-bundled`, `openai-curated`, `openai-curated-remote`, and `openai-primary-runtime`.

Only GitHub and Dropbox authentication were explicitly verified for this project. Calendar, Slack, Outlook, Sites, and other app account scopes were not tested and must not be described as authenticated merely because their plugin is enabled.

### User-configured MCP servers

| Server | Configured | Callable in this task | M0 use/auth result |
|---|---:|---:|---|
| `node_repl` | Yes | Yes | Not needed |
| `stata-mcp` | Yes | Not exposed in this task's callable surface | Not tested |
| `surveycto_tools` | Yes | Yes | Not tested |
| `llm_for_zotero` | Yes | Yes | Not tested |
| `notebooklm` | Yes | Yes | Not tested |
| `playwright` | Yes | Yes | Available; command-line version also verified |
| Context7 plugin MCP | Plugin-enabled | Yes | Available; no project dependency lookup needed |

GitHub and Dropbox are exposed as Codex app connectors rather than duplicate project-local MCP registrations.

## Skills relevant to this project

The task-visible catalog included:

- system skills for OpenAI documentation, image generation, skill creation, and skill installation;
- project/research skills for Graphify, causal inference, Stata, Stata causal inference, R analysis, Jupyter, Quarto, bibliography validation, literature review, qualitative research, meta-analysis, SurveyCTO, document/PDF/spreadsheet/presentation work, and economics/manuscript workflows;
- plugin-provided browser/Chrome/computer control, Context7, security review, academic research, Outlook, and engineering-discipline skills;
- engineering workflow skills for design, implementation plans, test-driven development, systematic debugging, subagent delegation, code review, and verification.

No new user-level skill or plugin was installed. The existing capability set already satisfies the M0 conceptual minimum: GitHub, Dropbox, shell/Git/Python, browser/web, official OpenAI documentation, Context7, Playwright, execution planning, skill creation/installation, and subagents. GitHub workflow-log tools cover CI diagnosis; a separate duplicate CI plugin is not justified.

The eight project-local skills were checked with the current official structural validator. Each passed frontmatter/name/scaffold validation. They are intentionally short and milestone-scoped; behavioral pressure tests are deferred until the associated workflow is authorized and designed. Structural validity is not claimed as behavioral proof.

## Local system inventory

| Component | Verified result |
|---|---|
| OS | Windows 11 Pro, 64-bit, build 26200 |
| CPU | AMD Ryzen 7 PRO 8840HS; 16 logical processors |
| RAM | 59.67 GiB physical memory |
| Disk | System volume had 1,186.79 GiB free at inspection |
| Git | 2.55.0.windows.2 |
| Codex CLI | 0.147.0 |
| Python | 3.12.13 selected through uv; Python 3.13 also installed |
| uv | 0.11.28 |
| Node.js | 24.19.0 |
| npm / npx | 11.17.0 / 11.17.0 |
| Java | Not found on `PATH` |
| Tesseract | Not found; Spanish language data therefore unverified/absent |
| qpdf | Not found |
| Ghostscript | Not found |
| Poppler | `pdftotext` 24.04 and `pdfinfo` 26.05.0 available |
| Playwright | CLI 1.62.1 available; MCP browser tools visible |
| Dropbox mount | Reparse-point/cloud-sync behavior observed; local ACL permits writes |

The version difference between the two Poppler executables is recorded rather than normalized. Tool provenance must capture the actual executable and version used per run.

## Python environment resolution

- Supported project range: Python `>=3.12,<3.14`.
- Core runtime dependencies are deliberately small: Pydantic and PyYAML.
- Development dependencies cover pytest, coverage, Ruff, Pyright, pre-commit, and type stubs.
- `uv.lock` was generated by uv 0.11.28 from the actual `pyproject.toml`; it is not a placeholder.
- `uv sync --frozen --group dev` succeeded with Python 3.12.13.
- DuckDB, PyArrow, OCR, geospatial, PDF parsing, semantic, and model SDK stacks were not added preemptively. They should enter only when an authorized work package demonstrates a concrete need and supplies tests/system requirements.

## Authentication and limitation summary

| Area | Status |
|---|---|
| GitHub | Verified authenticated and repository-accessible; no write exercised |
| Dropbox | Verified authenticated and root-accessible; no write exercised |
| OpenAI docs/web | Public official documentation accessible |
| Context7 | Tool visible; no authentication issue tested |
| Playwright | Tool and CLI visible; browser installation/site-specific login not exhaustively tested |
| Other MCP/plugin accounts | Configuration/callability varies; authentication and scopes unverified |
| Paid/external services | None added or invoked for project processing |

## Minimal capability recommendation

Retain the current core: local Git/Python/uv, GitHub and Dropbox read access, official OpenAI docs, web/browser/Playwright, Context7, project tests, and subagents. Do not add OCR, PDF-engine, geospatial, semantic, LLM, or CI-diagnosis dependencies until an authorized milestone has a measured requirement. Before any future connector mutation, verify both authentication and least-privilege scope in the active task.
