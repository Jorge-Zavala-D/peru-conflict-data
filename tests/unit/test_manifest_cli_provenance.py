from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _load_cli_module() -> ModuleType:
    script = Path(__file__).parents[2] / "scripts" / "reconcile_corpus_manifest.py"
    specification = importlib.util.spec_from_file_location("reconcile_corpus_manifest", script)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_resolves_execution_commit_and_exact_tree_from_real_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Manifest provenance tests")
    (repo / "tracked.txt").write_text("stable tree\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "Synthetic tree")
    expected_head = _git(repo, "rev-parse", "HEAD")
    expected_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    module = _load_cli_module()
    resolver = getattr(module, "_resolve_repository_provenance", None)

    assert callable(resolver)
    assert resolver(repo) == (expected_head, expected_tree)
