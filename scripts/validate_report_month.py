"""Read one aggregate from stdin; emit its validated internal derivative to stdout."""

from __future__ import annotations

import sys

from peru_conflicts.execution.aggregate_processing import parse_report_month_aggregate


def main() -> int:
    try:
        record = parse_report_month_aggregate(sys.stdin.buffer.read())
    except ValueError as error:
        print(f"Aggregate validation failed: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write((record.model_dump_json() + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
