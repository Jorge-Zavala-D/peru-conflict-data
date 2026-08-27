from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from peru_conflicts.config import load_project_config

VALID_CONFIG = """
config_version: '1'
project:
  slug: peru-conflict-data
  country: Peru
  source_institution: Defensoria del Pueblo
  coverage_start: 2004-04
  canonical_table_format: parquet
  canonical_query_engine: duckdb
principles:
  raw_immutable: true
  field_level_provenance: true
  preserve_original_strings: true
  allow_silent_source_correction: false
  missing_is_zero: false
  deterministic_before_probabilistic: true
  manual_review_is_data: true
benchmark:
  recent_report_numbers: [260, 261, 262]
"""


def test_load_project_config_parses_versioned_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_project_config(config_path)

    assert config.config_version == "1"
    assert config.project.coverage_start == "2004-04"
    assert config.principles.missing_is_zero is False
    assert config.benchmark.recent_report_numbers == (260, 261, 262)


def test_load_project_config_rejects_unknown_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(VALID_CONFIG + "unexpected: true\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="unexpected"):
        load_project_config(config_path)


def test_load_project_config_rejects_missingness_contract_change(tmp_path: Path) -> None:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(
        VALID_CONFIG.replace("missing_is_zero: false", "missing_is_zero: true"), encoding="utf-8"
    )

    with pytest.raises(ValidationError, match="missing_is_zero"):
        load_project_config(config_path)


def test_load_project_config_rejects_unknown_version_and_coerced_numbers(tmp_path: Path) -> None:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(
        VALID_CONFIG.replace("config_version: '1'", "config_version: '2'").replace(
            "[260, 261, 262]", "['260', 261, 262]"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_project_config(config_path)


def test_load_project_config_rejects_impossible_coverage_month(tmp_path: Path) -> None:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(VALID_CONFIG.replace("2004-04", "2004-99"), encoding="utf-8")

    with pytest.raises(ValidationError, match="calendar month"):
        load_project_config(config_path)
