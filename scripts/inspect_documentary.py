"""Inspect frozen documentary records without extracting or adjudicating source content."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from peru_conflicts.inspection.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
