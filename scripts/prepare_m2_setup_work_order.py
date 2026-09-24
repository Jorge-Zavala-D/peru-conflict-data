"""Source-neutral operator boundary. No credentials, HTTP or live admission."""

from __future__ import annotations

import argparse

from peru_conflicts.execution.setup_authority import admit
from peru_conflicts.execution.setup_offline import main as offline_main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("offline-demo", "admit", "next", "import", "status"))
    args = parser.parse_args()
    if args.operation == "offline-demo":
        offline_main()
        return
    # Real authority is checked before private-path or credential lookup. There is
    # deliberately no grant-registry, token, endpoint or enable-live CLI parameter.
    try:
        admit(b"", lambda: None)
    except ValueError as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
