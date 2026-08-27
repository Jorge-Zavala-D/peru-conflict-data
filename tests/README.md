# Tests

- `unit/`: deterministic behavior without external data.
- `integration/`: interactions among local configuration/package components using temporary synthetic roots.
- `regression/`: future small redistributable parser regressions.
- `benchmark/`: future benchmark harness; human gold artifacts remain outside Git unless explicitly proven small and redistributable.

Tests marked `external`, `benchmark`, or `slow` are excluded from ordinary CI unless explicitly invoked.
