from __future__ import annotations

import subprocess
from pathlib import Path

from peru_conflicts.repository_guard import (
    find_policy_violations,
    git_candidate_contents,
    git_candidate_paths,
    git_candidate_sizes,
)


def test_guard_rejects_raw_and_canonical_data_extensions(tmp_path: Path) -> None:
    names = ["report.pdf", "benchmark.xlsx", "table.parquet", "database.duckdb"]
    paths: list[Path] = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"small")
        paths.append(path)

    violations = find_policy_violations(paths, repo_root=tmp_path)

    assert {violation.path.name for violation in violations} == set(names)
    assert all("prohibited" in violation.reason for violation in violations)


def test_guard_rejects_credential_like_files(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    key = tmp_path / "service-account-credentials.json"
    secret.write_text("TOKEN=secret", encoding="utf-8")
    key.write_text("{}", encoding="utf-8")

    violations = find_policy_violations([secret, key], repo_root=tmp_path)

    assert {violation.path.name for violation in violations} == {secret.name, key.name}


def test_guard_allows_documented_environment_template(tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    template.write_text("CONFLICT_DATA_ROOT=replace-me", encoding="utf-8")

    assert find_policy_violations([template], repo_root=tmp_path) == []


def test_guard_rejects_tabular_logs_and_cookie_exports(tmp_path: Path) -> None:
    paths: list[Path] = []
    for name in ["export.csv", "events.jsonl", "audit.log", "cookies.txt", "client_secret.json"]:
        path = tmp_path / name
        path.write_text("small", encoding="utf-8")
        paths.append(path)

    violations = find_policy_violations(paths, repo_root=tmp_path)

    assert {violation.path.name for violation in violations} == {path.name for path in paths}


def test_guard_rejects_oversized_otherwise_allowed_file(tmp_path: Path) -> None:
    artifact = tmp_path / "large-fixture.txt"
    artifact.write_bytes(b"x" * 11)

    violations = find_policy_violations([artifact], repo_root=tmp_path, max_bytes=10)

    assert len(violations) == 1
    assert violations[0].reason == "file exceeds 10 bytes"


def test_guard_accepts_small_code_schema_fixture_and_documentation(tmp_path: Path) -> None:
    paths: list[Path] = []
    for name in ["module.py", "report.schema.json", "fixture.txt", "protocol.md"]:
        path = tmp_path / name
        path.write_text("reviewable", encoding="utf-8")
        paths.append(path)

    assert find_policy_violations(paths, repo_root=tmp_path) == []


def test_guard_ignores_deleted_or_untracked_argument_that_no_longer_exists(tmp_path: Path) -> None:
    missing = tmp_path / "removed.pdf"

    assert find_policy_violations([missing], repo_root=tmp_path) == []


def test_default_git_candidates_include_untracked_nonignored_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    untracked = tmp_path / "untracked.pdf"
    untracked.write_bytes(b"source bytes")

    assert Path("untracked.pdf") in git_candidate_paths(tmp_path)


def test_staged_guard_uses_index_blob_size_not_worktree_size(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    artifact = tmp_path / "artifact.txt"
    artifact.write_bytes(b"x" * 11)
    subprocess.run(["git", "add", "artifact.txt"], cwd=tmp_path, check=True)
    artifact.write_bytes(b"x")

    candidates = git_candidate_paths(tmp_path, staged=True)
    sizes = git_candidate_sizes(tmp_path, candidates, staged=True)
    violations = find_policy_violations(
        candidates,
        repo_root=tmp_path,
        max_bytes=10,
        sizes=sizes,
    )

    assert violations[0].reason == "file exceeds 10 bytes"


def test_staged_guard_scans_index_blob_content_not_worktree_content(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    artifact = tmp_path / "settings.txt"
    fake_token = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    artifact.write_text(f"token={fake_token}", encoding="utf-8")
    subprocess.run(["git", "add", "settings.txt"], cwd=tmp_path, check=True)
    artifact.write_text("safe placeholder", encoding="utf-8")

    candidates = git_candidate_paths(tmp_path, staged=True)
    sizes = git_candidate_sizes(tmp_path, candidates, staged=True)
    contents = git_candidate_contents(tmp_path, candidates, staged=True, sizes=sizes)
    violations = find_policy_violations(
        candidates,
        repo_root=tmp_path,
        sizes=sizes,
        contents=contents,
    )

    assert violations[0].reason == "prohibited credential or temporary-link content"


def test_repository_policy_forbids_agent_side_credential_extraction() -> None:
    agents = " ".join(Path("AGENTS.md").read_text(encoding="utf-8").lower().split())
    security = " ".join(Path("SECURITY.md").read_text(encoding="utf-8").lower().split())

    for policy in (agents, security):
        assert "git credential fill" in policy
        assert "authorization header" in policy
        assert "normal `git push`" in policy
        assert "explicit user confirmation" in policy
        assert "least privilege" in policy
        assert "similar credential stores. agents must never" in policy
