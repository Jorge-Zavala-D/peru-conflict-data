# Generated schemas

`scripts/export_schemas.py` generates two separately versioned contracts:

- `v0.2.0/` is the M1 working scientific content contract generated from
  `peru_conflicts.models.MODEL_REGISTRY`; `v0.1.0/` is the immutable M0 snapshot.
- `discovery/v0.1.0/` is the provisional M1 source-discovery contract generated from
  `peru_conflicts.discovery.ProvisionalDiscoveryRecord`. It does not version or modify the
  scientific content contract.

Regenerate only the current versions and preserve prior version directories.
`scripts/export_schemas.py --check` checks both current contracts for drift. Python/Pydantic
validation remains authoritative for semantic cross-field invariants, including exact paired
identity evidence, while the scientific model is documented in
`docs/07_canonical_data_model.md`.

The discovery JSON Schema conditionally requires a nonempty identity-evidence array containing
the corresponding subject and a qualifying `document_visible` or `official_metadata` evidence
type whenever a candidate report number or reference period is present. Standard JSON Schema
cannot dynamically compare that candidate scalar to a value inside an array, so Pydantic remains
authoritative for exact `candidate_value` equality. Each identity-evidence and candidate-relation
endpoint links to a stable URL-observation ID, and record validation checks both existence and URL
agreement. Catalogue, search-result, thematic, landing, direct-download, and redirect-hop roles
remain distinct structured records. Technical discovery issues preserve evidence links and keep
`SOURCE_INCONSISTENCY`, `SOURCE_AMBIGUITY`, and `COVERAGE_GAP` separate; they do not carry parser
corrections. `CoverageExpectation` remains a standalone research-grid hypothesis that can be
constructed and returned independently of observed URLs.
