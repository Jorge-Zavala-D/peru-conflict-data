"""Foreign test repositories must not inherit a caller's Git administration paths."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = (
    ("integration/test_acquisition_dry_run.py", "_git"),
    ("unit/test_acquisition_authorization_v2.py", "_run"),
    ("unit/test_acquisition_preflight.py", "_run_git"),
    ("unit/test_manifest_cli_provenance.py", "_git"),
)


def _module(relative: str) -> ModuleType:
    name = "isolation_" + Path(relative).stem
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap_environment(root: Path) -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")
    }
    config = root / "global"
    config.write_bytes(b"")
    templates = root / "templates"
    templates.mkdir()
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=str(config),
        GIT_TEMPLATE_DIR=str(templates),
        GIT_OPTIONAL_LOCKS="0",
    )
    return environment


def _git(repo: Path, environment: dict[str, str], *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=repo, env=environment, text=True
    ).strip()


def _parent(root: Path, kind: str) -> tuple[Path, Path, Path, dict[str, str]]:
    environment = _bootstrap_environment(root)
    parent = root / "p"
    parent.mkdir()
    _git(parent, environment, "init", "-q", "-b", "main")
    _git(parent, environment, "config", "user.name", "Synthetic isolation")
    _git(parent, environment, "config", "user.email", "isolation@example.invalid")
    (parent / "base.txt").write_bytes(b"synthetic baseline\n")
    _git(parent, environment, "add", "base.txt")
    _git(parent, environment, "commit", "-qm", "synthetic baseline")
    caller = parent
    if kind == "linked":
        caller = root / "l"
        _git(parent, environment, "worktree", "add", "-q", "-b", "linked", str(caller))
    private = Path(_git(caller, environment, "rev-parse", "--absolute-git-dir"))
    common = Path(_git(caller, environment, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (caller / common).resolve()
    assert private.is_relative_to(root) and common.is_relative_to(root)
    return caller, private, common, environment


def _metadata(common: Path, private: Path) -> dict[str, bytes]:
    paths = {
        common / "config",
        common / "HEAD",
        common / "index",
        private / "HEAD",
        private / "index",
    }
    paths.update((common / "refs").rglob("*"))
    paths.update((common / "objects").rglob("*"))
    paths.add(common / "packed-refs")
    return {str(path): path.read_bytes() for path in sorted(paths) if path.is_file()}


@pytest.mark.parametrize("kind", ["normal", "linked"])
@pytest.mark.parametrize(("relative", "name"), HELPERS)
def test_real_foreign_git_helpers_preserve_caller_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, relative: str, name: str
) -> None:
    _, private, common, environment = _parent(tmp_path, kind)
    before = _metadata(common, private)
    repo = tmp_path / "f"
    repo.mkdir()
    module = _module(relative)
    helper = getattr(module, name)
    with monkeypatch.context() as context:
        for key in tuple(os.environ):
            if key.upper().startswith("GIT_"):
                context.delenv(key, raising=False)
        for key, value in environment.items():
            if key.startswith("GIT_"):
                context.setenv(key, value)
        context.setenv("GIT_DIR", str(private))
        context.setenv("GIT_INDEX_FILE", str(private / "index"))
        context.setenv("GIT_PREFIX", "")
        helper(repo, "init", "-q", "-b", "main")
        helper(repo, "config", "user.name", "Synthetic foreign fixture")
        helper(repo, "config", "user.email", "fixture@example.invalid")
        (repo / "foreign.txt").write_bytes(b"synthetic foreign content\n")
        helper(repo, "add", "foreign.txt")
        helper(repo, "commit", "-qm", "synthetic foreign commit")
    assert _metadata(common, private) == before
    assert (repo / ".git").is_dir()
    assert _git(repo, environment, "rev-parse", "--show-toplevel") == str(repo).replace("\\", "/")


@pytest.mark.parametrize("kind", ["normal", "linked"])
@pytest.mark.parametrize("reader", ["ci", "guard", "manifest", "preflight", "dry-run"])
def test_actual_synthetic_reader_boundaries_preserve_caller_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    reader: str,
) -> None:
    _, private, common, environment = _parent(tmp_path, kind)
    before = _metadata(common, private)
    fixture = tmp_path / "f"
    fixture.mkdir()
    with monkeypatch.context() as context:
        for key in tuple(os.environ):
            if key.upper().startswith("GIT_"):
                context.delenv(key, raising=False)
        for key, value in environment.items():
            if key.startswith("GIT_"):
                context.setenv(key, value)
        context.setenv("GIT_DIR", str(private))
        context.setenv("GIT_INDEX_FILE", str(private / "index"))
        context.setenv("GIT_PREFIX", "")
        if reader == "ci":
            module = _module("unit/test_ci_m2_gate.py")
            module.test_binding_requires_unchanged_tracked_source(fixture, context, "unchanged")
        elif reader == "guard":
            module = _module("unit/test_repository_guard.py")
            module.test_staged_neutral_guard_uses_index_not_worktree(fixture, "blank", False)
        elif reader == "manifest":
            module = _module("unit/test_manifest_cli_provenance.py")
            module.test_cli_resolves_execution_commit_and_exact_tree_from_real_git_repo(fixture)
        elif reader == "preflight":
            module = _module("unit/test_acquisition_preflight.py")
            module.test_preflight_verifies_ten_sources_and_builds_ordered_zero_side_effect_plan(
                fixture
            )
        else:
            module = _module("integration/test_acquisition_dry_run.py")
            module.test_complete_cli_dry_run_has_zero_network_and_preserves_data_tree_exactly(
                fixture, context, capsys
            )
    assert _metadata(common, private) == before


def test_foreign_env_preserves_runtime_and_reapplies_only_controlled_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.git_env import foreign_git_env

    runtime = {
        "PATH": "synthetic-path",
        "SYSTEMROOT": "synthetic-os",
        "TEMP": str(tmp_path),
        "PYTHONPATH": "synthetic-import",
    }
    for name, value in runtime.items():
        monkeypatch.setenv(name, value)
    for name in (
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_TEMPLATE_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_KEY_17",
        "GIT_CONFIG_VALUE_17",
        "git_config_key_18",
        "git_config_value_18",
    ):
        monkeypatch.setenv(name, str(tmp_path / "inherited"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "18")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Controlled synthetic author")
    environment = foreign_git_env()
    assert {name: environment[name] for name in runtime} == runtime
    assert environment["GIT_AUTHOR_NAME"] == "Controlled synthetic author"
    assert environment["GIT_CONFIG_COUNT"] == "0"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_CONFIG_SYSTEM"] == os.devnull
    assert not any(
        name.upper().startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) for name in environment
    )
    assert "GIT_DIR" not in environment and "GIT_INDEX_FILE" not in environment
    assert "GIT_OBJECT_DIRECTORY" not in environment and "GIT_TEMPLATE_DIR" not in environment
    assert os.environ["GIT_CONFIG_COUNT"] == "18"
    controlled = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.autocrlf",
        "GIT_CONFIG_VALUE_0": "false",
    }
    reapplied = foreign_git_env(controlled)
    assert {name: reapplied[name] for name in controlled} == controlled
    lower_case_input = {
        "git_dir": str(tmp_path / "inherited"),
        "Git_Config_Key_17": "core.fsmonitor",
        "git_config_value_18": "synthetic-command",
        "GIT_AUTHOR_NAME": "Controlled synthetic author",
    }
    with monkeypatch.context() as environment_context:
        environment_context.setattr(os, "environ", lower_case_input)
        case_insensitive_copy = foreign_git_env()
    assert "git_dir" not in case_insensitive_copy
    assert "Git_Config_Key_17" not in case_insensitive_copy
    assert "git_config_value_18" not in case_insensitive_copy
    assert case_insensitive_copy["GIT_AUTHOR_NAME"] == "Controlled synthetic author"


def test_foreign_reader_context_restores_the_hostile_enclosing_context_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.git_env import foreign_git_context

    enclosing = {
        "GIT_DIR": str(tmp_path / "caller"),
        "GIT_INDEX_FILE": str(tmp_path / "caller-index"),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "synthetic-command",
        "GIT_TEMPLATE_DIR": str(tmp_path / "caller-template"),
    }
    for name, value in enclosing.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PYTHONPATH", "synthetic-import")
    with pytest.raises(RuntimeError, match="synthetic interruption"), foreign_git_context():
        assert "GIT_DIR" not in os.environ and "GIT_INDEX_FILE" not in os.environ
        assert "GIT_CONFIG_KEY_0" not in os.environ
        assert os.environ["GIT_CONFIG_COUNT"] == "0"
        assert os.environ["PYTHONPATH"] == "synthetic-import"
        raise RuntimeError("synthetic interruption")
    assert {name: os.environ[name] for name in enclosing} == enclosing
