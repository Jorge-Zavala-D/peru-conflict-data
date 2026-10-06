# Contributing

The active route is [AI_PI_RECONSTRUCTION_V1](docs/ai_pi_strategy.md).
Read its reference/evaluation protocol and successor roadmap before work.
Preserve legacy versioned contracts; do not reopen retired RA/native prerequisites.
Use existing installed tooling when synchronization is not authorized. Tests do
not grant real extraction, PI approval or release authority.

Use focused branches and reviewable diffs. Preserve source fidelity, field-level provenance, original values, explicit missingness, and adjudication history. Add tests before behavior or schema changes; regenerate schemas with `uv run python scripts/export_schemas.py`; run `make quality`; keep all source and large generated artifacts outside Git. Architecture decisions belong in `docs/adr/`.
