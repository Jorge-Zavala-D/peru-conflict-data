"""Run bounded, HTML-only reconnaissance of approved Defensoría surfaces."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from peru_conflicts.discovery.client import HtmlClient
from peru_conflicts.discovery.models import UrlRole
from peru_conflicts.discovery.reconnaissance import run_reconnaissance


def _load_sources(
    path: Path,
) -> tuple[frozenset[str], tuple[str, ...], dict[str, UrlRole], dict[str, object]]:
    raw_payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError(f"Source configuration must be a mapping: {path}")
    payload = cast(dict[str, object], raw_payload)
    hosts = payload.get("approved_hosts")
    surfaces = payload.get("starting_surfaces")
    retrieval = payload.get("retrieval")
    if (
        not isinstance(hosts, list)
        or not isinstance(surfaces, list)
        or not isinstance(retrieval, dict)
    ):
        raise ValueError(
            "Source configuration is missing approved_hosts, starting_surfaces, or retrieval"
        )
    host_values = cast(list[object], hosts)
    surface_values = cast(list[object], surfaces)
    if not all(isinstance(host, str) for host in host_values):
        raise ValueError("approved_hosts must contain strings")
    if not all(isinstance(surface, dict) for surface in surface_values):
        raise ValueError("starting_surfaces must contain mappings")
    typed_surfaces = [cast(dict[str, object], surface) for surface in surface_values]
    typed_retrieval = cast(dict[str, object], retrieval)
    urls: list[str] = []
    roles: dict[str, UrlRole] = {}
    for surface in typed_surfaces:
        if not isinstance(surface.get("url"), str):
            raise ValueError("Each starting surface must have a URL")
        url = cast(str, surface["url"])
        role_value = surface.get("role", "catalogue")
        if not isinstance(role_value, str):
            raise ValueError("Surface role must be a string")
        role_name = role_value
        role = {
            "catalogue": UrlRole.CATALOGUE_PAGE,
            "search": UrlRole.SEARCH_RESULT_PAGE,
            "thematic": UrlRole.THEMATIC_PAGE,
        }.get(role_name)
        if role is None:
            raise ValueError(f"Unsupported starting surface role: {role_name}")
        urls.append(url)
        roles[url] = role
    return frozenset(cast(list[str], host_values)), tuple(urls), roles, typed_retrieval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/official_sources.yaml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".cache") / f"m1-discovery-{date.today().isoformat()}",
    )
    parser.add_argument("--page-cap", type=int, default=120)
    parser.add_argument("--max-landing-pages", type=int, default=24)
    parser.add_argument("--delay-seconds", type=float, default=None)
    parser.add_argument("--retry-cap", type=int, default=None)
    arguments = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config_path = (
        arguments.config if arguments.config.is_absolute() else repo_root / arguments.config
    )
    hosts, start_urls, roles, retrieval = _load_sources(config_path)
    configured_delay = retrieval.get("delay_seconds")
    configured_retries = retrieval.get("retry_cap")
    if not isinstance(configured_delay, (int, float)) or isinstance(configured_delay, bool):
        raise ValueError("retrieval.delay_seconds must be numeric")
    if not isinstance(configured_retries, int) or isinstance(configured_retries, bool):
        raise ValueError("retrieval.retry_cap must be an integer")
    delay = float(
        arguments.delay_seconds if arguments.delay_seconds is not None else configured_delay
    )
    retry_cap = int(arguments.retry_cap if arguments.retry_cap is not None else configured_retries)
    client = HtmlClient(hosts, delay_seconds=delay, retry_cap=retry_cap)
    run_reconnaissance(
        start_urls,
        output_dir=arguments.output,
        client=client,
        surface_roles=roles,
        page_cap=arguments.page_cap,
        max_landing_pages=arguments.max_landing_pages,
        repo_root=repo_root,
    )
    print(f"Wrote HTML-only reconnaissance receipts to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
