# Contributing

Use focused branches and reviewable diffs. Preserve source fidelity, field-level provenance, original values, explicit missingness, and adjudication history. Add tests before behavior or schema changes; regenerate schemas with `uv run python scripts/export_schemas.py`; run `make quality`; keep all source and large generated artifacts outside Git. Architecture decisions belong in `docs/adr/`.
