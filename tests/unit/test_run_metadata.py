from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from peru_conflicts.models import ModelInvocation
from peru_conflicts.run_metadata import GitState, capture_run_metadata


def prepare_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "repo"
    (project / "schemas").mkdir(parents=True)
    config = project / "config.yaml"
    config.write_text("version: 1\n", encoding="utf-8")
    (project / "schemas" / "report.schema.json").write_text("{}\n", encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"official bytes")
    return project, config, source


def test_capture_run_metadata_records_reproducibility_identity(tmp_path: Path) -> None:
    project, config, source = prepare_project(tmp_path)
    started = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)

    metadata = capture_run_metadata(
        project_root=project,
        config_paths=[config],
        input_paths={"report_260": source},
        parser_versions={"inventory": "m0.1"},
        git_state=GitState(commit="abc123", dirty=False),
        started_at=started,
        run_id="run_test",
    )

    assert metadata.run_id == "run_test"
    assert metadata.started_at == started
    assert metadata.git.commit == "abc123"
    assert metadata.git.dirty is False
    assert len(metadata.config_hash) == 64
    assert len(metadata.schema_hash) == 64
    assert len(metadata.lockfile_hash or "") == 64
    assert len(metadata.input_hashes["report_260"]) == 64
    assert metadata.parser_versions == {"inventory": "m0.1"}
    assert metadata.environment.python_version
    assert metadata.environment.package_versions["pydantic"]
    assert "pydantic-settings" not in metadata.environment.package_versions


def test_capture_run_metadata_preserves_dirty_state_and_model_identity(tmp_path: Path) -> None:
    project, config, source = prepare_project(tmp_path)
    invocation = ModelInvocation(
        provider="openai",
        model="model-name",
        prompt_version="prompt-v1",
        output_schema_version="0.1.0",
        source_span_hash="a" * 64,
        output_hash="b" * 64,
    )

    metadata = capture_run_metadata(
        project_root=project,
        config_paths=[config],
        input_paths={"report_260": source},
        parser_versions={},
        git_state=GitState(commit="def456", dirty=True),
        model_invocations=[invocation],
    )

    assert metadata.git.dirty is True
    assert metadata.model_invocations[0].prompt_version == "prompt-v1"


def test_capture_run_metadata_allows_no_probabilistic_calls(tmp_path: Path) -> None:
    project, config, source = prepare_project(tmp_path)

    metadata = capture_run_metadata(
        project_root=project,
        config_paths=[config],
        input_paths={"report_260": source},
        parser_versions={},
        git_state=GitState(commit="abc123", dirty=False),
    )

    assert metadata.model_invocations == ()
    assert metadata.started_at.tzinfo is not None


def test_external_same_named_configs_do_not_collapse(tmp_path: Path) -> None:
    project, _, source = prepare_project(tmp_path)
    first = tmp_path / "first" / "settings.yaml"
    second = tmp_path / "second" / "settings.yaml"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("source: first\n", encoding="utf-8")
    second.write_text("source: second\n", encoding="utf-8")

    before = capture_run_metadata(
        project_root=project,
        config_paths=[first, second],
        input_paths={"source": source},
        parser_versions={},
        git_state=GitState(commit="abc123", dirty=False),
    )
    first.write_text("source: changed\n", encoding="utf-8")
    after = capture_run_metadata(
        project_root=project,
        config_paths=[first, second],
        input_paths={"source": source},
        parser_versions={},
        git_state=GitState(commit="abc123", dirty=False),
    )

    assert before.config_hash != after.config_hash
