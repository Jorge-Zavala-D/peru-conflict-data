"""Shared strict types for source-preserving domain records."""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

SCHEMA_VERSION = "0.2.0"
Identifier = Annotated[str, StringConstraints(min_length=1, pattern=r".*\S.*")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
ScalarValue = str | int | float | bool | None


def _validate_reference_period(value: str) -> str:
    year_text, month_text = value.split("-", maxsplit=1)
    if not 1 <= int(year_text) <= 9999 or not 1 <= int(month_text) <= 12:
        raise ValueError("reference period must be a real YYYY-MM calendar month")
    return value


def _validate_json_document(value: str) -> str:
    try:
        json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("value must be a valid JSON document") from error
    return value


ReferencePeriod = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}$"),
    AfterValidator(_validate_reference_period),
]
JsonDocument = Annotated[str, AfterValidator(_validate_json_document)]
Confidence = Annotated[float, Field(ge=0, le=1)]


class StrictModel(BaseModel):
    """Immutable model that fails closed on unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class VersionedModel(StrictModel):
    schema_version: Literal["0.2.0"] = SCHEMA_VERSION


class SourceBBox(StrictModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def validate_coordinate_order(self) -> Self:
        if self.x1 < self.x0:
            raise ValueError("x1 must be greater than or equal to x0")
        if self.y1 < self.y0:
            raise ValueError("y1 must be greater than or equal to y0")
        return self


class SourceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_span_order(self) -> Self:
        if self.end < self.start:
            raise ValueError("span end must be greater than or equal to start")
        return self


class TransitionEvidence(StrictModel):
    transition_original: Identifier
    transition_normalized: str | None = None
    provenance_ids: tuple[Identifier, ...] = Field(min_length=1)


class ModelSetting(StrictModel):
    name: Identifier
    value: ScalarValue


class ModelInvocation(StrictModel):
    provider: Identifier
    model: Identifier
    prompt_version: Identifier
    output_schema_version: Identifier
    source_span_hash: Sha256
    output_hash: Sha256
    inference_settings: tuple[ModelSetting, ...] = ()
