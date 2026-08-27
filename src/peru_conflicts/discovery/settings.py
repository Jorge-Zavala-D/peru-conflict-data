"""Strict configuration and non-bypassable bounds for M1 HTML discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self, cast
from urllib.parse import urlsplit

import yaml
from pydantic import Field, field_validator, model_validator

from peru_conflicts.discovery.policy import classify_host
from peru_conflicts.models.common import Identifier, StrictModel

MIN_LIVE_DELAY_SECONDS = 2.0
MAX_LIVE_RETRY_CAP = 2
MAX_SURFACE_PAGE_CAP = 120
MAX_LANDING_PAGE_CAP = 24
AUTHORITATIVE_HOSTS = ("defensoria.gob.pe", "www.defensoria.gob.pe")
REVIEWED_STARTING_SURFACES = (
    (
        "reports_catalogue",
        "catalogue",
        "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/",
        "numeric_or_rel_next",
        True,
    ),
    (
        "conflict_search",
        "search",
        "https://www.defensoria.gob.pe/?s=Reporte+conflictos",
        "numeric_or_rel_next",
        True,
    ),
    (
        "conflict_search_monthly",
        "search",
        "https://www.defensoria.gob.pe/?s=Reporte+Mensual+de+Conflictos+Sociales",
        "numeric_or_rel_next",
        True,
    ),
    (
        "paz_social_conflict_prevention",
        "thematic",
        "https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/",
        "single_page",
        True,
    ),
)
_REVIEWED_REJECTION_POLICY = {
    "reject_pdf": True,
    "reject_binary": True,
    "reject_unlisted_content_types": True,
    "body_retrieval": "html_only",
}
_REVIEWED_ROBOTS_REJECTION_POLICY = {
    "reject_pdf": True,
    "reject_binary": True,
    "reject_unlisted_content_types": True,
}


class DiscoveryRuntimeLimits(StrictModel):
    """Hard M1 envelope; an ordinary run has no CLI escape hatch."""

    delay_seconds: float
    retry_cap: int = Field(ge=0)
    page_cap: int = Field(ge=1)
    landing_page_cap: int = Field(ge=0)

    @model_validator(mode="after")
    def enforce_absolute_bounds(self) -> Self:
        if self.delay_seconds < MIN_LIVE_DELAY_SECONDS:
            raise ValueError(f"live delay must be at least {MIN_LIVE_DELAY_SECONDS:.1f} seconds")
        if self.retry_cap > MAX_LIVE_RETRY_CAP:
            raise ValueError(f"retry cap must be at most {MAX_LIVE_RETRY_CAP}")
        if self.page_cap > MAX_SURFACE_PAGE_CAP:
            raise ValueError(f"page cap must be at most {MAX_SURFACE_PAGE_CAP}")
        if self.landing_page_cap > MAX_LANDING_PAGE_CAP:
            raise ValueError(f"landing page cap must be at most {MAX_LANDING_PAGE_CAP}")
        return self


class RetrievalConfiguration(DiscoveryRuntimeLimits):
    """Reviewed retrieval values plus body and redirect safety bounds."""

    concurrency: Literal[1]
    max_redirects: int = Field(ge=0, le=5)
    max_html_body_bytes: int = Field(ge=1, le=10_000_000)
    allowed_content_types: tuple[Literal["text/html", "application/xhtml+xml"], ...]
    rejection_policy: dict[str, object]

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def freeze_content_types(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_exact_reviewed_retrieval_contract(self) -> Self:
        observed = (
            self.concurrency,
            self.delay_seconds,
            self.retry_cap,
            self.page_cap,
            self.landing_page_cap,
            self.max_redirects,
            self.max_html_body_bytes,
            self.allowed_content_types,
            self.rejection_policy,
        )
        expected = (
            1,
            2.0,
            2,
            120,
            24,
            5,
            5_000_000,
            ("text/html", "application/xhtml+xml"),
            _REVIEWED_REJECTION_POLICY,
        )
        if observed != expected:
            raise ValueError("configuration must match the exact reviewed retrieval contract")
        return self


class RobotsConfiguration(StrictModel):
    path: Literal["/robots.txt"]
    allowed_content_types: tuple[Literal["text/plain"], ...]
    max_body_bytes: int = Field(ge=1, le=1_000_000)
    body_retrieval: Literal["robots_txt_only"]
    rejection_policy: dict[str, object]

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def freeze_content_types(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_exact_reviewed_robots_contract(self) -> Self:
        if (
            self.allowed_content_types != ("text/plain",)
            or self.max_body_bytes != 500_000
            or self.rejection_policy != _REVIEWED_ROBOTS_REJECTION_POLICY
        ):
            raise ValueError("configuration must match the exact reviewed robots contract")
        return self


class StartingSurface(StrictModel):
    id: Identifier
    role: Literal["catalogue", "search", "thematic"]
    url: Identifier
    pagination_mode: Literal["numeric_or_rel_next", "single_page"]
    pagination_contract_verified: bool

    @model_validator(mode="after")
    def require_authoritative_https_url(self) -> Self:
        if urlsplit(self.url).scheme != "https":
            raise ValueError("starting surface must be an HTTPS authoritative URL")
        return self


class OfficialSourceConfiguration(StrictModel):
    config_version: Literal["2"]
    approved_hosts: tuple[Identifier, ...] = Field(min_length=1)
    starting_surfaces: tuple[StartingSurface, ...] = Field(min_length=1)
    retrieval: RetrievalConfiguration
    robots: RobotsConfiguration

    @field_validator("approved_hosts", "starting_surfaces", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_exact_authority_contract(self) -> Self:
        if self.approved_hosts != AUTHORITATIVE_HOSTS:
            raise ValueError("approved_hosts must be exactly the reviewed authoritative hosts")
        approved = frozenset(AUTHORITATIVE_HOSTS)
        if any(
            classify_host(surface.url, approved) != "authoritative"
            for surface in self.starting_surfaces
        ):
            raise ValueError("starting surface must be an HTTPS authoritative URL")
        observed_surfaces = tuple(
            (
                surface.id,
                surface.role,
                surface.url,
                surface.pagination_mode,
                surface.pagination_contract_verified,
            )
            for surface in self.starting_surfaces
        )
        if observed_surfaces != REVIEWED_STARTING_SURFACES:
            raise ValueError("configuration must contain the exact reviewed starting surfaces")
        return self


def load_official_source_config(path: Path) -> OfficialSourceConfiguration:
    """Load the reviewed source policy without YAML type coercion downstream."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return OfficialSourceConfiguration.model_validate(payload)


def resolve_runtime_limits(
    configuration: OfficialSourceConfiguration,
    *,
    delay_seconds: float | None = None,
    retry_cap: int | None = None,
    page_cap: int | None = None,
    landing_page_cap: int | None = None,
) -> DiscoveryRuntimeLimits:
    """Resolve CLI inputs, allowing only changes safer than the reviewed configuration."""

    configured = configuration.retrieval
    if (
        (delay_seconds is not None and delay_seconds < configured.delay_seconds)
        or (retry_cap is not None and retry_cap > configured.retry_cap)
        or (page_cap is not None and page_cap > configured.page_cap)
        or (landing_page_cap is not None and landing_page_cap > configured.landing_page_cap)
    ):
        raise ValueError(
            "runtime arguments may not weaken the approved configuration; a separately "
            "reviewed code/configuration change is required"
        )
    resolved = DiscoveryRuntimeLimits(
        delay_seconds=configured.delay_seconds if delay_seconds is None else delay_seconds,
        retry_cap=configured.retry_cap if retry_cap is None else retry_cap,
        page_cap=configured.page_cap if page_cap is None else page_cap,
        landing_page_cap=(
            configured.landing_page_cap if landing_page_cap is None else landing_page_cap
        ),
    )
    return resolved
