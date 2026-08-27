# Execution plan: Milestones 1-12

Version: 0.1.0 (Milestone 0 planning baseline)

## Plan contract

This document describes future work; it does not authorize it. Milestone 1 begins only after Jorge approves M0 and resolves the approval items in the M0 completion report. Each work package produces reviewable artifacts on a focused branch. No package may weaken the research contract or benchmark gates without a written decision.

Parallel work is limited to independent, read-heavy or isolated outputs. No two agents independently mutate a canonical manifest, schema, gold file, adjudication table, or identity graph.

## Global gates

| Gate | Requirement |
|---|---|
| Source integrity | Raw inputs retained byte-for-byte with SHA-256 and alternate-version relationships |
| Provenance | Material fields resolve to source hash/report/page/section and evidence span/bbox where feasible |
| Missingness | Unknown/unreported remains null; no zero imputation |
| Discrepancies | Parser errors, source inconsistencies, ambiguity, cross-source conflicts, and editorial suspicions remain distinct |
| Determinism | Native/layout/table methods precede OCR or model assistance |
| Benchmark | Modern parser targets >=99% exact central fields, >=99% case-detection precision and recall, >=99% page attribution, zero unresolved critical parser errors, classified arithmetic discrepancies, and review of every medium-confidence link |
| Scale | No full-regime/full-corpus run before relevant gates pass or an explicit revision is approved |

## Milestone 1: complete official corpus discovery and manifest

### M1-01 — discovery protocol and source registry

| Field | Plan |
|---|---|
| Goal | Define reproducible official-source search, retrieval, retry, and evidence rules before acquiring anything |
| Dependencies | M0 approval; decision on redistribution/storage and canonical official domains |
| Inputs | M0 inventories, Defensoría site structure, existing raw filenames |
| Outputs | Versioned discovery protocol, source-domain allowlist, manifest schema migration if required |
| Tests | URL normalization; retrieval timestamps; official-domain checks; nullable report/month handling; alternate-version representation |
| Acceptance | Independent reviewer can reproduce the protocol on a small predeclared sample without altering raw files |
| Human review | Jorge approves official-domain and rights assumptions |
| Tools | Browser/Playwright, GitHub, deterministic HTTP metadata; no LLM requirement |
| Compute/cost risk | Low; rate limits and site fragility |
| Parallelization | Protocol review and site reconnaissance may run in parallel; schema has one owner |

### M1-02 — official-source reconnaissance

| Field | Plan |
|---|---|
| Goal | Enumerate official indexes, archives, metadata pages, and download endpoints without yet claiming completeness |
| Dependencies | M1-01 |
| Inputs | Approved official domains and search protocol |
| Outputs | Search-source log, endpoint evidence, provisional discovery records |
| Tests | Pagination termination, duplicate URL handling, response/content-type checks, robots/rate-limit compliance |
| Acceptance | Every search path and stopping rule is recorded; no year-folder-as-regime assumption |
| Human review | Review suspected gaps and inaccessible official sources |
| Tools | Browser/Playwright and deterministic request tooling |
| Compute/cost risk | Low to medium; remote request volume bounded and cached |
| Parallelization | Independent official indexes can be inspected in parallel; outputs merge through one manifest owner |

### M1-03 — immutable acquisition and version preservation

| Field | Plan |
|---|---|
| Goal | Acquire approved official files into raw storage without overwriting any byte version |
| Dependencies | M1-02; explicit acquisition authorization |
| Inputs | Approved provisional discovery records |
| Outputs | Immutable raw objects, retrieval receipts, SHA-256, sizes, MIME signatures, version relationships |
| Tests | Atomic download; hash-before-promote; same-name/different-byte handling; interrupted download recovery; raw-write guard exceptions limited to acquisition command |
| Acceptance | Every acquired byte object has a receipt; repeated runs are idempotent; alternate official versions are retained |
| Human review | Review all collisions and non-PDF content |
| Tools | Deterministic downloader with rate limits; Dropbox raw storage |
| Compute/cost risk | Medium network/storage; no paid service |
| Parallelization | Downloads may be bounded-parallel; manifest and collision adjudication remain serialized |

### M1-04 — manifest reconciliation and completeness claim

| Field | Plan |
|---|---|
| Goal | Reconcile report number, publication/reference month, title, URLs, byte versions, and acquisition state |
| Dependencies | M1-03 |
| Inputs | Discovery records, receipts, PDFs, M0 reports 260-269 |
| Outputs | Versioned corpus manifest, gap register, duplicate/version graph, coverage report |
| Tests | Unique constraints that permit alternate bytes; month/number contradiction fixtures; manifest-to-file hash closure; no unreferenced acquired files |
| Acceptance | Every expected interval is present or explicitly classified with evidence; independent review signs the coverage claim |
| Human review | All gaps, ambiguous numbering, stale metadata, and version relationships |
| Tools | Python, hashes, PDF metadata/native first-page evidence |
| Compute/cost risk | Low to medium |
| Parallelization | Evidence verification can parallelize; canonical manifest has one writer |

## Milestone 2: human gold benchmark and workbook overlap

### M2-01 — benchmark protocol and sampling units

| Field | Plan |
|---|---|
| Goal | Freeze the annotation unit, field dictionary, page-evidence contract, adjudication process, and accuracy metrics for reports 260-269 |
| Dependencies | M1 accepted; benchmark reports' byte versions fixed |
| Inputs | Reports 260-269, schemas, research contract |
| Outputs | Annotation handbook, gold schemas, annotator forms, critical-field list, metric implementation spec |
| Tests | Schema validation; impossible-value and null/zero examples; metric unit tests with synthetic confusion matrices only |
| Acceptance | Two pilot annotations expose no unresolved definition-level ambiguity in critical fields |
| Human review | Jorge approves handbook and any proposed gate interpretation |
| Tools | PDF viewer, structured annotation files; no extraction model |
| Compute/cost risk | Low compute, high expert time |
| Parallelization | Independent handbook review allowed; handbook has one owner |

### M2-02 — double annotation of reports 260-269

| Field | Plan |
|---|---|
| Goal | Produce human gold objects and exact page/section/span evidence independently |
| Dependencies | M2-01 |
| Inputs | Ten fixed PDFs and annotation handbook |
| Outputs | Annotator A/B records, disagreement queue, provenance coverage receipt |
| Tests | Completeness against handbook; source-page resolution; schema checks; no canonical overwrite |
| Acceptance | Every required object and critical field has double annotation or documented not-applicable status |
| Human review | Required for all disagreements and uncertain source statements |
| Tools | Native PDF/text viewers, structured forms |
| Compute/cost risk | High human-time cost; no model calls |
| Parallelization | Reports can be assigned in parallel; annotators remain independent until adjudication |

### M2-03 — gold adjudication and freeze

| Field | Plan |
|---|---|
| Goal | Resolve disagreements without erasing annotator records and freeze a versioned benchmark |
| Dependencies | M2-02 |
| Inputs | A/B annotations, disagreement queue, source pages |
| Outputs | Append-only adjudications, gold release candidate, benchmark changelog/hash |
| Tests | Every resolved disagreement points to adjudication; critical items have second review; reproducible materialization |
| Acceptance | Zero unresolved critical annotation disagreements; benchmark hash approved |
| Human review | Jorge or delegated lead approves freeze |
| Tools | Validation CLI and PDF evidence |
| Compute/cost risk | Medium human time |
| Parallelization | Non-overlapping issue review can parallelize; materialization serialized |

### M2-04 — workbook overlap normalization

| Field | Plan |
|---|---|
| Goal | Describe and normalize `Base15-26.xlsx` overlap without treating it as the canonical universe |
| Dependencies | M2-03; workbook byte version fixed |
| Inputs | Workbook, gold reports, source-preserving schemas |
| Outputs | Workbook data dictionary, normalized staging tables, row/field provenance, overlap and discrepancy report |
| Tests | Sheet/range/hash guard; original cell preservation; null/blank semantics; duplicate-row and type-coercion tests |
| Acceptance | Every normalized value links to the original workbook cell; all report/workbook conflicts classified |
| Human review | Ambiguous headers/codes and all critical cross-source conflicts |
| Tools | Deterministic spreadsheet reader, Python |
| Compute/cost risk | Low compute, medium review |
| Parallelization | Header/field review can parallelize; normalized table has one writer |

## Milestone 3: modern parser meeting acceptance gates

### M3-01 — PDF regime diagnostics

| Field | Plan |
|---|---|
| Goal | Measure native text order, layout, table structure, and page-level OCR need for the benchmark bytes |
| Dependencies | M2 gold frozen |
| Inputs | Ten PDFs and gold page units |
| Outputs | Page diagnostics, evidence-based regime assignment, tool/version comparison |
| Tests | Repeatability by source hash; selected-page fixtures; engine disagreement capture |
| Acceptance | Parser strategy justified per observed format; OCR remains page-specific |
| Human review | Regime boundaries and any OCR authorization |
| Tools | Poppler first; add PDF/OCR tools only through a justified dependency decision |
| Compute/cost risk | Medium; OCR potentially high but bounded |
| Parallelization | Per-engine diagnostics can parallelize; regime decision reviewed centrally |

### M3-02 — deterministic report/case segmentation

| Field | Plan |
|---|---|
| Goal | Detect report sections and conflict-case units with exact source-page provenance |
| Dependencies | M3-01 |
| Inputs | Native/layout evidence, benchmark annotations |
| Outputs | Cached segments, report/case candidates, extraction traces |
| Tests | Unit fixtures from authorized pages; boundary cases; deterministic rerun hashes; no gold leakage into production rules |
| Acceptance | >=99% case-detection precision and recall and >=99% source-page attribution on held-out benchmark units |
| Human review | Every false negative/positive and any proposed gate revision |
| Tools | Deterministic Python/layout parser |
| Compute/cost risk | Medium |
| Parallelization | Separate section modules may develop in isolation; shared segmentation contract has one owner |

### M3-03 — field extraction and structured fallback

| Field | Plan |
|---|---|
| Goal | Extract central fields, actors, demands, transitions, protests, violence, dialogue, agreements, actions, and alerts with source evidence |
| Dependencies | M3-02 |
| Inputs | Segments, schemas, gold benchmark |
| Outputs | Strict structured records, provenance, confidence/review queues, cached model calls only if approved |
| Tests | Field-specific fixtures; missing/null tests; original/normalized pairing; schema and provenance closure; prompt/model cache identity if applicable |
| Acceptance | >=99% exact accuracy for designated central deterministic fields; unsupported values remain null |
| Human review | Low-confidence/probabilistic outputs and all critical discrepancies |
| Tools | Native/layout/table extraction; optional segmented model only after explicit design approval |
| Compute/cost risk | Medium deterministic; potentially paid model cost requires separate approval |
| Parallelization | Entity modules can parallelize after contracts freeze; core schemas/caches single-owned |

### M3-04 — benchmark evaluation and parser release gate

| Field | Plan |
|---|---|
| Goal | Run reproducible evaluation, error taxonomy, arithmetic checks, and critical-error closure |
| Dependencies | M3-03 |
| Inputs | Frozen gold, parser outputs, provenance traces |
| Outputs | Metrics by report/field/object, classified errors, reproducibility receipt, parser version decision |
| Tests | Metric implementation cross-check; blind holdout; repeat-run equality; deliberate parser/source inconsistency cases |
| Acceptance | All stated M3 targets met, zero unresolved critical parser errors, arithmetic discrepancies classified, or a written revision approved |
| Human review | Full error ledger and gate decision |
| Tools | Python evaluation/QA |
| Compute/cost risk | Low compute, high review near gate |
| Parallelization | Error reviews can parallelize; final gate decision centralized |

## Milestone 4: modern longitudinal linkage

### M4-01 — identity evidence contract

| Field | Plan |
|---|---|
| Goal | Freeze linkage features, blocking, relationship vocabulary, confidence bands, and review policy without hard-coding historical taxonomy |
| Dependencies | M3 accepted |
| Inputs | Modern parsed case-month data, official codes, schema foundation |
| Outputs | Linkage protocol, candidate schema migration, review handbook |
| Tests | Continuation/rename/merge/split/reactivation/related synthetic cases; missing-evidence behavior |
| Acceptance | Protocol represents every required relationship and never forces one-to-one continuity |
| Human review | Jorge approves confidence/review rules |
| Tools | Python, schema tools |
| Compute/cost risk | Low |
| Parallelization | Independent protocol critique allowed; graph contract single-owned |

### M4-02 — deterministic linkage

| Field | Plan |
|---|---|
| Goal | Apply official codes then deterministic multi-field rules and retain all evidence |
| Dependencies | M4-01 |
| Inputs | Modern case-month records, official codes, locations/actors/demands |
| Outputs | Deterministic edges, unmatched records, decision traces |
| Tests | Stable IDs; rule precedence; collision handling; no normalization-only identity claim |
| Acceptance | All deterministic links reproducible and evidence-complete; collisions queued, never silently broken |
| Human review | Every code contradiction and collision |
| Tools | Python/graph tables |
| Compute/cost risk | Low to medium |
| Parallelization | Blocking diagnostics can parallelize; canonical edge writer serialized |

### M4-03 — probabilistic candidates and adjudication

| Field | Plan |
|---|---|
| Goal | Generate high-recall candidates for unresolved records and adjudicate required confidence bands |
| Dependencies | M4-02 |
| Inputs | Unmatched records and deterministic graph |
| Outputs | Scored candidate sets, calibration results, append-only adjudications |
| Tests | Candidate recall on held-out reviewed pairs; calibration; competing-candidate retention; model/version capture |
| Acceptance | All medium-confidence links reviewed; no probabilistic edge becomes canonical without policy-compliant decision |
| Human review | Medium confidence and all structural relationships |
| Tools | Deterministic features first; statistical/model tooling only if justified |
| Compute/cost risk | Medium compute and high expert time |
| Parallelization | Candidate generation partitions can parallelize; adjudication records have controlled ownership |

### M4-04 — longitudinal QA and modern release candidate

| Field | Plan |
|---|---|
| Goal | Validate month-to-month stock/transition arithmetic, graph consistency, and provenance closure |
| Dependencies | M4-03 |
| Inputs | Modern identity graph, cases, case-months, transitions, adjudications |
| Outputs | Linkage benchmark report, graph invariants, discrepancy ledger, modern candidate tables |
| Tests | Impossible transition sequences; merge/split degree rules; stock-flow checks without treating missing as zero; reproducible rebuild |
| Acceptance | Zero unresolved critical linkage errors; every medium-confidence link reviewed; all arithmetic discrepancies classified |
| Human review | Final modern linkage gate |
| Tools | DuckDB/Parquet added only when this package materializes canonical tables |
| Compute/cost risk | Medium |
| Parallelization | QA checks parallelizable; release materialization serialized |

## Milestones 5-12: lower-granularity roadmap

| Milestone | Goal and principal work packages | Entry/exit gate | Main risks and review |
|---|---|---|---|
| M5 historical format reconnaissance | Sample evidence across change points; measure text/layout/table/OCR properties; propose format regimes from evidence, not folders | Enter after M4; exit with approved regime map and benchmark sample design | Format heterogeneity, poor scans, missing reports; human review of every regime boundary |
| M6 historical parsers | Build regime-specific deterministic parsers, page-specific OCR fallbacks, gold subsets, and acceptance reports | Each regime independently meets approved gates before scale | OCR cost/error, changing labels, sparse evidence; no universal parser |
| M7 full corpus extraction | Execute versioned parsers over the fixed manifest; produce resumable caches, coverage receipts, and discrepancy queues | All relevant regime gates pass; exit with provenance-complete parsed corpus candidate | Compute/storage volume, silent partial runs; checkpoint and hash every stage |
| M8 2004-present entity resolution | Extend deterministic/candidate/adjudication linkage across eras and organizational/name changes | Historical extraction accepted; exit with reviewed identity graph | False continuity, merges/splits, taxonomy drift; high human-review burden |
| M9 geographic harmonization | Preserve original geography, add versioned administrative crosswalks and coordinates with uncertainty | Identity graph stable enough; exit with reviewed geographic derivatives | Boundary change and ambiguous place names; never overwrite source geography |
| M10 full QA/adjudication | Cross-report arithmetic, provenance closure, anomaly review, adjudication freeze, reproducible materialization | M7-M9 candidates complete; exit with zero unresolved critical issues or approved limitations | Review backlog and hidden missingness; independent audit required |
| M11 public release | Build immutable Parquet/DuckDB plus documented exports, code/data dictionaries, checksums, licenses, citation, known limitations | Rights and M10 gates approved; exit with versioned release | Redistribution/privacy/license risk; Jorge approves public scope |
| M12 data paper and handoff | Produce methods/data paper evidence, Defensoría handoff, update SOP, monthly ingest/benchmark/monitoring process | Public release stable; exit with rehearsed monthly update and ownership transfer | Documentation drift, operational ownership, future format change; live dry run reviewed |

## Change control

Every future package records its branch, Git base/head, data manifest version, schema/config/parser versions, input hashes, environment and lock hash, tests, reviewers, cost, and open discrepancies. A failed gate creates evidence and a proposed decision; it does not authorize lowering the target. Milestone transitions require Jorge's explicit approval.
