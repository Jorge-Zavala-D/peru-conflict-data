"""Write a source-neutral proposal to a new ignored cache snapshot; no launch."""

import argparse
from pathlib import Path

from peru_conflicts.execution.operational_plan import write_operational_proposal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="New directory name under .cache/m2-02b2")
    args = parser.parse_args()
    print(write_operational_proposal(Path(__file__).resolve().parents[1], args.snapshot))


if __name__ == "__main__":
    main()
