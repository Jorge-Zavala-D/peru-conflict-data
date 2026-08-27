"""Strict loading for versioned project configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from peru_conflicts.models.common import ReferencePeriod


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class ProjectMetadata(StrictConfigModel):
    slug: str
    country: str
    source_institution: str
    coverage_start: ReferencePeriod
    canonical_table_format: Literal["parquet"]
    canonical_query_engine: Literal["duckdb"]


class ResearchPrinciples(StrictConfigModel):
    raw_immutable: Literal[True]
    field_level_provenance: Literal[True]
    preserve_original_strings: Literal[True]
    allow_silent_source_correction: Literal[False]
    missing_is_zero: Literal[False]
    deterministic_before_probabilistic: Literal[True]
    manual_review_is_data: Literal[True]


class BenchmarkConfig(StrictConfigModel):
    recent_report_numbers: tuple[int, ...] = Field(min_length=1)

    @field_validator("recent_report_numbers", mode="before")
    @classmethod
    def freeze_report_numbers(cls, value: object) -> object:
        """Accept YAML's native sequence container without coercing its elements."""

        return tuple(cast(list[object], value)) if isinstance(value, list) else value


class ProjectConfig(StrictConfigModel):
    config_version: Literal["1"]
    project: ProjectMetadata
    principles: ResearchPrinciples
    benchmark: BenchmarkConfig


def load_project_config(path: Path) -> ProjectConfig:
    """Load a YAML project contract and reject unknown or contradictory values."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Project configuration must be a mapping: {path}")
    return ProjectConfig.model_validate(payload)
