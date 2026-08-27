"""CLI for the repository data-policy guard."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from peru_conflicts.repository_guard import (
    find_policy_violations,
    git_candidate_contents,
    git_candidate_paths,
    git_candidate_sizes,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024)
    arguments = parser.parse_args()

    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    candidates = git_candidate_paths(root, staged=arguments.staged)
    sizes = git_candidate_sizes(root, candidates, staged=arguments.staged)
    violations = find_policy_violations(
        candidates,
        repo_root=root,
        max_bytes=arguments.max_bytes,
        sizes=sizes,
        contents=git_candidate_contents(
            root,
            candidates,
            staged=arguments.staged,
            sizes=sizes,
            max_bytes=arguments.max_bytes,
        ),
    )
    for violation in violations:
        print(f"{violation.path.relative_to(root)}: {violation.reason}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
