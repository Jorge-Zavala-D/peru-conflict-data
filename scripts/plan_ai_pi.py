"""Print an AI/PI plan; never execute a real batch."""

from peru_conflicts.execution.ai_pi import main

if __name__ == "__main__":
    raise SystemExit(main())
