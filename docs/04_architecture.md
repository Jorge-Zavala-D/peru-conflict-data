# Architecture

GitHub stores code, tests, schemas, config, docs, ADRs, repo-local skills, and small source-safe fixtures. The external data root stores official files, raw PDFs, mechanical extraction, parsed objects, linkage/geography, Parquet/DuckDB, QA/adjudication, and releases.

Planned data flow: `DISCOVER -> MANIFEST -> INGEST/HASH -> PDF FORENSICS -> NATIVE/LAYOUT/OCR -> SEGMENT -> PARSE -> NORMALIZE -> ENTITY RESOLUTION -> GEO HARMONIZATION -> VALIDATE -> MANUAL REVIEW -> PARQUET -> DUCKDB -> EXPORT -> RELEASE`. Each stage is report-scoped, idempotent, inspectable, and cached by input/code/config/schema/parser/model/prompt identity. M0 implements only cross-cutting safety, schema, run-identity, logging, and quality foundations.
