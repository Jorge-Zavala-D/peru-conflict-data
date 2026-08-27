"""Export or verify the repository's generated JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from peru_conflicts.schema_export import export_json_schemas, schemas_are_current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("schemas"))
    arguments = parser.parse_args()

    if arguments.check:
        if schemas_are_current(arguments.output):
            return 0
        print("Generated JSON Schemas differ from the registered models.")
        return 1

    written = export_json_schemas(arguments.output)
    print(f"Exported {len(written)} JSON Schemas to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
