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
