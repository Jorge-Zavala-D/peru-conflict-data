# Milestone 0.1 hardening completion report

Status: **local hardening complete; remote pull-request verification pending**.
This report records the owner-authorized M0.1 pass on
`codex/milestone-0-foundation`. It does not authorize Milestone 1. M1-01, M1-02,
and M1-03 remain stopped; M1-03 still requires its separate acquisition checkpoint.

Date: 2026-08-27 (Europe/Berlin)  
Branch: `codex/milestone-0-foundation`  
Commit at local/remote verification: `a63b6bf09e15dfa81f035d72eaf532a7b190a3de`  
Base: `origin/main` at `14b913f390056a74b598de08742be1120515dda6`  
Pull request: pending creation; no merge performed  
Remote Actions: pending pull-request run

## Scope and outcome

The pass preserved `schemas/v0.1.0/` byte-for-byte and superseded it with the
source-evidenced working contract `schemas/v0.2.0/`. It added no corpus discovery,
acquisition, parsing, OCR, benchmark annotation, entity resolution, geocoding,
taxonomy harmonization, LLM calls, raw writes, or derived-data production.

The repository now has 24 registered strict Pydantic models and generated JSON
Schemas, including a process-level `mediation_process` relation. Source-original
values remain beside nullable derivatives; open historical vocabularies remain
open. Monthly indicators explicitly distinguish `source_reported` from `derived`.
Source-reported rows retain metric, value, unit, optional scope, and provenance;
derived rows require derivation name/version and upstream record IDs and never
replace a source-reported row.

## Required M0.1 changes

- Demand preserves `theme_original`, `category_original`, optional
  `category_normalized`, and `competent_entity_original` as separate dimensions.
- `MediationProcess` preserves process-level start date/precision, status,
  requester, actors, mediation type, mediator, case description, demands, and
  progress. Dated `DialogueEvent` records remain separate; a populated process
  link requires provenance in both Pydantic validation and JSON Schema.
- `Agreement` separates source agreement text from `Avances de cumplimiento` and
  keeps optional source responsibility/deadline strings without actor linking or
  date interpretation.
- `DefensoriaAction`, `Alert`, `Location`, `ProtestEvent`, and `ViolenceEvent`
  preserve the additional nullable source dimensions evidenced in report 269,
  including intervention hierarchy, alert type/risk/location, structured original
  geography, date precision, and violence type.
- Report identity evidence requires document-visible and/or official metadata for
  report number and reference period; an embedded PDF `/Title` such as `RCS N° 126`
  cannot stand alone.
- The operational acquisition ledger is assigned to Dropbox
  `01_raw/manifests/`; Git holds schemas, code, configuration, tests, rules, and
  optional small reviewed indexes, not a mutable duplicate ledger.
- `docs/source_discrepancy_reconnaissance.md` records the report-269 alert-total
  contradiction (58 narrative versus 34 in Cuadro N.° 1) and the July-report case
  `1514-0726` stating `Ingresó como caso nuevo: Agosto 2026`; neither was repaired.
- `docs/m1_acquisition_checkpoint.md` specifies atomic download, hash-before-promote,
  collision, retry/idempotency, rate-limit, and bounded dry-run controls for the
  separately authorized first raw write.

## Schema/version evidence

- `schemas/v0.1.0/` is retained unchanged. Its fixed Python tree digest is
  `da34082dabb4dc7020f078d7f5902c68cc2dd4ef6f430d7bf7cfe98e6e829f28`.
- `schemas/v0.2.0/` contains one generated schema for every registry key (24 total),
  including `mediation_process`, monthly-indicator guards, report-identity guards,
  and the mediation-link provenance guard.
- `docs/schema_migrations/v0.1.0_to_v0.2.0.md` defines explicit review-required
  migration rules; changing a version string alone is not a migration.
- `docs/08_data_dictionary.md` is a field-level dictionary synchronized by test
  with every registered model field, documenting meaning, representation,
  original/normalized status, null semantics, multiplicity, provenance,
  relationships, and source/derived/technical origin.

## Quality-gate receipt

| Check | Result |
|---|---|
| `uv lock --check` | Passed; 26 packages resolved |
| `uv sync --frozen --group dev` | Passed |
| Ruff format check | Passed |
| Ruff lint | Passed |
| strict Pyright | Passed; 0 errors, 0 warnings, 0 informations |
| `uv run pytest -q` | Passed; 92 tests |
| generated-schema drift check | Passed |
| repository data-policy check | Passed |
| `git diff --check` | Passed |
| pre-commit (`--all-files`) | All hooks passed |

The independent review found three important issues and two documentation issues;
all were addressed with tests, regenerated schemas, and documentation updates:
monthly scope is represented, mediation links require provenance, M1-01 now depends
on M0.1 review plus explicit authorization, the historical receipt link is valid,
and derived-indicator provenance semantics are documented and tested.

## Source-integrity receipt

Read-only verification was rerun at `2026-08-27T11:39:00.7485378Z` UTC. All 11
allowed external/raw inputs match their pre-M0 SHA-256 and byte sizes recorded in
`docs/source_integrity_receipt_m0_1.md`: `Base15-26.xlsx` plus reports 260-269.
The connected Dropbox root remains 82 directories, 110 files, and 33,453,193 bytes.
File counts under `02_extracted`, `03_parsed`, `04_linked`, `05_database`,
`06_validation`, and `07_releases` are all zero. The MIT `LICENSE` SHA-256 remains
`7838bc30d3402b894dc236cc3cc9a62933f3dd6ec71ff21f02f1044f38b5edff`.

No raw PDF, workbook, archive, or other Dropbox file was modified, and no file was
added to a derived-data layer.

## Git and review summary

- Previous pushed foundation: `12433154ac54cb4f2ae0842ae2df47b8fd0ae23c`.
- M0.1 review-fix commit: `a63b6bf09e15dfa81f035d72eaf532a7b190a3de`.
- Remote branch was fetched and equals the local commit; `origin/main` remains
  unchanged.
- The diff contains only repository code, tests, schemas, configuration, and
  documentation. No source or credential files are tracked.
- Pull-request and independent GitHub Actions identifiers will be filled in after
  the owner-confirmed browser submission and completion of the remote workflow.

## Decisions requiring Jorge before M1

1. Review and approve `v0.2.0` as the M1/M2 working schema and its explicit
   v0.1-to-v0.2 migration boundary.
2. Explicitly authorize M1-01 and M1-02, with official-domain and rights/storage
   assumptions confirmed.
3. Separately approve M1-03 only after reviewing the acquisition command/design and
   bounded dry-run receipt in `docs/m1_acquisition_checkpoint.md`.
4. Decide whether a small reviewed public source index should be kept in Git; the
   mutable operational ledger remains in Dropbox and canonical normalized manifests
   remain future Parquet/DuckDB outputs.
5. Approve or revise the proposed `main` branch ruleset in
   `docs/github_branch_protection_proposal.md`. No repository-admin setting was
   changed during M0.1.

No benchmark-gate weakening, licensing change, paid service, or significant new
dependency is proposed. The project must stop here until Jorge reviews the remote
CI result and explicitly authorizes the next milestone.
