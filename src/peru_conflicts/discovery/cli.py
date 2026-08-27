"""Command-line boundary for bounded, HTML-only official-source reconnaissance."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from peru_conflicts.discovery.client import HtmlClient
from peru_conflicts.discovery.models import UrlRole
from peru_conflicts.discovery.reconnaissance import run_reconnaissance
from peru_conflicts.discovery.settings import (
    OfficialSourceConfiguration,
    ReviewedTargetedLanding,
    StartingSurface,
    load_official_source_config,
    resolve_runtime_limits,
)


def validate_cli_output_dir(output_dir: Path, repo_root: Path) -> Path:
    """Confine ordinary live M1 receipts to the repository's ignored cache."""

    target = output_dir.expanduser().resolve()
    cache = (repo_root.expanduser().resolve() / ".cache").resolve()
    if not target.is_relative_to(cache):
        raise ValueError("ordinary M1 discovery output must be beneath repository .cache")
    return target


def select_starting_surfaces(
    configuration: OfficialSourceConfiguration,
    requested_ids: tuple[str, ...] | None,
) -> tuple[StartingSurface, ...]:
    """Select configured surfaces in caller order without widening authority."""

    if not requested_ids:
        return configuration.starting_surfaces
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("duplicate surface ID in --surface-id arguments")
    by_id = {surface.id: surface for surface in configuration.starting_surfaces}
    unknown = [surface_id for surface_id in requested_ids if surface_id not in by_id]
    if unknown:
        raise ValueError(f"unknown surface ID: {', '.join(unknown)}")
    return tuple(by_id[surface_id] for surface_id in requested_ids)


def select_targeted_landings(
    configuration: OfficialSourceConfiguration,
    requested_ids: tuple[str, ...] | None,
) -> tuple[ReviewedTargetedLanding, ...]:
    """Select only exact reviewed targets; absence means no targeted requests."""

    if not requested_ids:
        return ()
    if len(set(requested_ids)) != len(requested_ids):
        raise ValueError("duplicate targeted landing ID in --targeted-landing-id arguments")
    by_id = {target.id: target for target in configuration.reviewed_targeted_landings}
    unknown = [target_id for target_id in requested_ids if target_id not in by_id]
    if unknown:
        raise ValueError(f"unknown targeted landing ID: {', '.join(unknown)}")
    return tuple(by_id[target_id] for target_id in requested_ids)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the safety envelope before constructing a live HTTP client."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/official_sources.yaml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache") / f"m1-discovery-{date.today().isoformat()}",
    )
    parser.add_argument("--page-cap", type=int, default=None)
    parser.add_argument("--max-landing-pages", type=int, default=None)
    parser.add_argument("--delay-seconds", type=float, default=None)
    parser.add_argument("--retry-cap", type=int, default=None)
    parser.add_argument("--surface-id", action="append", default=None)
    parser.add_argument("--targeted-landing-id", action="append", default=None)
    arguments = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[3]
    config_path = (
        arguments.config if arguments.config.is_absolute() else repo_root / arguments.config
    )
    configuration = load_official_source_config(config_path)
    limits = resolve_runtime_limits(
        configuration,
        delay_seconds=arguments.delay_seconds,
        retry_cap=arguments.retry_cap,
        page_cap=arguments.page_cap,
        landing_page_cap=arguments.max_landing_pages,
    )
    output_dir = validate_cli_output_dir(arguments.output, repo_root)
    requested_surface_ids = (
        tuple(arguments.surface_id) if arguments.surface_id is not None else None
    )
    selected_surfaces = select_starting_surfaces(configuration, requested_surface_ids)
    requested_target_ids = (
        tuple(arguments.targeted_landing_id) if arguments.targeted_landing_id is not None else None
    )
    selected_targets = select_targeted_landings(configuration, requested_target_ids)
    role_names = {
        "catalogue": UrlRole.CATALOGUE_PAGE,
        "search": UrlRole.SEARCH_RESULT_PAGE,
        "thematic": UrlRole.THEMATIC_PAGE,
    }
    start_urls = tuple(surface.url for surface in (*selected_surfaces, *selected_targets))
    roles = {surface.url: role_names[surface.role] for surface in selected_surfaces}
    roles.update({target.url: UrlRole.LANDING_PAGE for target in selected_targets})
    verified = {surface.url: surface.pagination_contract_verified for surface in selected_surfaces}
    verified.update(
        {target.url: target.pagination_contract_verified for target in selected_targets}
    )
    pagination_modes = {surface.url: surface.pagination_mode for surface in selected_surfaces}
    pagination_modes.update({target.url: target.pagination_mode for target in selected_targets})
    retrieval = configuration.retrieval
    client = HtmlClient(
        frozenset(configuration.approved_hosts),
        delay_seconds=limits.delay_seconds,
        retry_cap=limits.retry_cap,
        max_html_body_bytes=retrieval.max_html_body_bytes,
        max_robots_body_bytes=configuration.robots.max_body_bytes,
        max_redirects=retrieval.max_redirects,
    )
    run_reconnaissance(
        start_urls,
        output_dir=output_dir,
        client=client,
        surface_roles=roles,
        pagination_contract_verified=verified,
        surface_pagination_modes=pagination_modes,
        page_cap=limits.page_cap,
        max_landing_pages=limits.landing_page_cap,
        repo_root=repo_root,
    )
    print(f"Wrote HTML-only reconnaissance receipts to {arguments.output}")
    return 0
