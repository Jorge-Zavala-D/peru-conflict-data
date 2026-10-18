"""Thin entry point; scope and immutable inputs are supplied in a private manifest."""

from peru_conflicts.execution.native_documentary.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
