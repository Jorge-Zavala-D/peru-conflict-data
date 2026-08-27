# Architecture

GitHub stores code, tests, schemas, config, docs, ADRs, repo-local skills, and small source-safe fixtures. The external data root stores official files, raw PDFs, mechanical extraction, parsed objects, linkage/geography, Parquet/DuckDB, QA/adjudication, and releases.

Planned data flow: `DISCOVER -> OPERATIONAL MANIFEST (Dropbox 01_raw/manifests) -> INGEST/HASH -> PDF FORENSICS -> NATIVE/LAYOUT/OCR -> SEGMENT -> PARSE -> NORMALIZE -> ENTITY RESOLUTION -> GEO HARMONIZATION -> VALIDATE -> MANUAL REVIEW -> PARQUET -> DUCKDB -> EXPORT -> RELEASE`. Each stage is report-scoped, idempotent, inspectable, and cached by input/code/config/schema/parser/model/prompt identity. M0.1 implements only source-evidenced schema hardening and cross-cutting safety; M1 discovery/acquisition remains approval-gated.
