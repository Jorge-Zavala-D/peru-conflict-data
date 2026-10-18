"""Attach explicit source-bound context to supplied documentary records for inspection."""

import sys
from pathlib import Path

# Bind this script to its checkout even when another editable install is present.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from peru_conflicts.execution.context_attachment import main

if __name__ == "__main__":
    raise SystemExit(main())
