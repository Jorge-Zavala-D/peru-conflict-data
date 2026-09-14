"""Create an append-only ignored review snapshot from independently pinned evidence."""

import argparse
from pathlib import Path

from peru_conflicts.execution.launch_review import ReviewInputs, prepare_review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", type=Path, help="Coordinator JSON input manifest with independent pins"
    )
    parser.add_argument("snapshot", help="New directory name under .cache/m2-02b1")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    inputs = ReviewInputs.model_validate_json(args.inputs.read_bytes())
    output = prepare_review(
        Path(__file__).resolve().parents[1],
        args.snapshot,
        inputs,
        require_complete=args.require_complete,
    )
    print(output)
    print((output / "SHA256SUMS.txt").read_text(), end="")


if __name__ == "__main__":
    main()
