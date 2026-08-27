# Provenance standard

Every scientifically material extracted value traces to a report and source SHA-256, 1-indexed PDF page when applicable, section/table, bbox/span where feasible, and source text evidence for narrative fields. Derived variables document upstream fields and transformation version. Probabilistic extraction additionally stores provider/model, prompt/output-schema version, source-span hash, inference settings, output hash, and confidence/review status. Provenance is normalized into stable records; applicability rules, not fabricated coordinates, govern which locators may remain null.

Pipeline-controlled extraction methods are `native_text`, `layout`, `table`, `ocr`, `rule_based`, `probabilistic_model`, and `manual`. These are process categories, not historical source taxonomies. `probabilistic_model` requires a model invocation in both Pydantic validation and exported JSON Schema; other methods reject model metadata to prevent ambiguous run identity.
