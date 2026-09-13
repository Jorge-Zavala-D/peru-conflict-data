"""Thin local readiness helper; no annotation launch or network capability."""

from peru_conflicts.execution.readiness_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
