"""Export or verify the repository's generated JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from peru_conflicts.acquisition.schema_export import (
    acquisition_schemas_are_current,
    export_acquisition_schemas,
)
from peru_conflicts.benchmark.schema_export import (
    benchmark_schemas_are_current,
    export_benchmark_schemas,
)
from peru_conflicts.discovery.schema_export import (
    discovery_schemas_are_current,
    export_discovery_schemas,
)
from peru_conflicts.manifest.schema_export import (
    export_manifest_schemas,
    manifest_schemas_are_current,
)
from peru_conflicts.schema_export import export_json_schemas, schemas_are_current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("schemas"))
    arguments = parser.parse_args()

    if arguments.check:
        scientific_current = schemas_are_current(arguments.output)
        discovery_current = discovery_schemas_are_current(arguments.output)
        acquisition_current = acquisition_schemas_are_current(arguments.output)
        manifest_current = manifest_schemas_are_current(arguments.output)
        benchmark_current = benchmark_schemas_are_current(arguments.output / "benchmark")
        if (
            scientific_current
            and discovery_current
            and acquisition_current
            and manifest_current
            and benchmark_current
        ):
            return 0
        if not scientific_current:
            print("Generated scientific JSON Schemas differ from the registered models.")
        if not discovery_current:
            print("Generated discovery JSON Schemas differ from the registered models.")
        if not acquisition_current:
            print("Generated acquisition JSON Schemas differ from the registered models.")
        if not manifest_current:
            print("Generated manifest JSON Schemas differ from the registered models.")
        if not benchmark_current:
            print("Generated benchmark JSON Schemas differ from the registered models.")
        return 1

    written = export_json_schemas(arguments.output)
    written.extend(export_discovery_schemas(arguments.output))
    written.extend(export_acquisition_schemas(arguments.output))
    written.extend(export_manifest_schemas(arguments.output))
    written.extend(export_benchmark_schemas(arguments.output / "benchmark"))
    print(f"Exported {len(written)} JSON Schemas to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
