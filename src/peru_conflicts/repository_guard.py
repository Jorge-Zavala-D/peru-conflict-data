"""Fail closed when Git contains private, raw, canonical, or oversized artifacts."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from re import compile as compile_pattern

PROHIBITED_EXTENSIONS = frozenset(
    {
        ".arrow",
        ".csv",
        ".db",
        ".dta",
        ".duckdb",
        ".feather",
        ".jpeg",
        ".jpg",
        ".jsonl",
        ".log",
        ".ndjson",
        ".parquet",
        ".pdf",
        ".png",
        ".rds",
        ".sav",
        ".sqlite",
        ".tif",
        ".tiff",
        ".tsv",
        ".xls",
        ".xlsx",
    }
)
SECRET_FILENAMES = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "cookies.txt",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "service-account.json",
        "service_account.json",
    }
)
SECRET_EXTENSIONS = frozenset({".key", ".p12", ".pem", ".pfx"})
SECRET_CONTENT_PATTERNS: tuple[Pattern[bytes], ...] = (
    compile_pattern(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    compile_pattern(rb"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    compile_pattern(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    compile_pattern(rb"\brlkey=[A-Za-z0-9_-]{10,}\b"),
)
DEFAULT_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    reason: str


def find_policy_violations(
    paths: Iterable[Path],
    *,
    repo_root: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    sizes: Mapping[Path, int] | None = None,
    contents: Mapping[Path, bytes] | None = None,
) -> list[Violation]:
    """Inspect candidate Git paths and small worktree content for forbidden artifacts."""

    root = repo_root.resolve()
    violations: list[Violation] = []
    for supplied in paths:
        path = supplied if supplied.is_absolute() else root / supplied
        staged_size = sizes.get(supplied) if sizes is not None else None
        if staged_size is None and not path.is_file():
            continue

        lower_name = path.name.lower()
        if path.suffix.lower() in PROHIBITED_EXTENSIONS:
            violations.append(Violation(path, f"prohibited data/source extension: {path.suffix}"))
            continue
        if (
            lower_name in SECRET_FILENAMES
            or (lower_name.startswith(".env.") and lower_name != ".env.example")
            or lower_name.startswith("client_secret")
            or path.suffix.lower() in SECRET_EXTENSIONS
            or "credential" in lower_name
        ):
            violations.append(Violation(path, "prohibited credential-like filename"))
            continue
        size = staged_size if staged_size is not None else path.stat().st_size
        if size > max_bytes:
            violations.append(Violation(path, f"file exceeds {max_bytes} bytes"))
            continue
        content = contents.get(supplied) if contents is not None else None
        if content is None and path.is_file():
            content = path.read_bytes()
        if content is not None and any(
            pattern.search(content) for pattern in SECRET_CONTENT_PATTERNS
        ):
            violations.append(Violation(path, "prohibited credential or temporary-link content"))
    return violations


def git_candidate_paths(repo_root: Path, *, staged: bool = False) -> list[Path]:
    command = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
        if staged
        else ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    output = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return [Path(value) for value in output.split("\0") if value]


def git_candidate_sizes(
    repo_root: Path,
    paths: Iterable[Path],
    *,
    staged: bool = False,
) -> dict[Path, int]:
    """Return candidate sizes from the index for staged checks or the worktree otherwise."""

    sizes: dict[Path, int] = {}
    for candidate in paths:
        if staged:
            output = subprocess.run(
                ["git", "cat-file", "-s", f":{candidate.as_posix()}"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            sizes[candidate] = int(output)
        else:
            path = candidate if candidate.is_absolute() else repo_root / candidate
            if path.is_file():
                sizes[candidate] = path.stat().st_size
    return sizes


def git_candidate_contents(
    repo_root: Path,
    paths: Iterable[Path],
    *,
    staged: bool = False,
    sizes: Mapping[Path, int] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[Path, bytes]:
    """Return small candidate bytes from the index for staged checks or worktree otherwise."""

    candidates = list(paths)
    known_sizes = sizes or git_candidate_sizes(repo_root, candidates, staged=staged)
    contents: dict[Path, bytes] = {}
    for candidate in candidates:
        if known_sizes.get(candidate, max_bytes + 1) > max_bytes:
            continue
        if staged:
            contents[candidate] = subprocess.run(
                ["git", "show", f":{candidate.as_posix()}"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            ).stdout
        else:
            path = candidate if candidate.is_absolute() else repo_root / candidate
            if path.is_file():
                contents[candidate] = path.read_bytes()
    return contents
