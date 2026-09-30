"""Source-neutral operator boundary. No credentials, HTTP or live admission."""

from __future__ import annotations

import sys


def main() -> None:
    if sys.argv[1:] == ["offline-demo"]:
        from peru_conflicts.execution.setup_offline import main as offline_main

        offline_main()
        return
    # Real authority is checked before private-path or credential lookup. There is
    # deliberately no grant-registry, token, endpoint or enable-live CLI parameter.
    print("M2 operator rejected: use the prescribed verified startup", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
