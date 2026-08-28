"""Run the M1-03A acquisition preflight without network or Dropbox writes."""

from __future__ import annotations

from peru_conflicts.acquisition.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
