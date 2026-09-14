"""Build a deterministic unissued neutral runtime candidate."""

import argparse
from pathlib import Path

from peru_conflicts.execution.runtime_build import build_runtime


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build_runtime(args.output).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
