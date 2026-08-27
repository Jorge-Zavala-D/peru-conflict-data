from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from peru_conflicts.discovery.cli import select_starting_surfaces, validate_cli_output_dir
from peru_conflicts.discovery.settings import (
    DiscoveryRuntimeLimits,
    load_official_source_config,
    resolve_runtime_limits,
)


def test_repository_source_config_has_fixed_m1_safety_envelope() -> None:
    configuration = load_official_source_config(Path("config/official_sources.yaml"))

    assert configuration.retrieval.concurrency == 1
    assert configuration.retrieval.delay_seconds == 2.0
    assert configuration.retrieval.retry_cap == 2
    assert configuration.retrieval.page_cap == 120
    assert configuration.retrieval.landing_page_cap == 24
    assert all(surface.pagination_contract_verified for surface in configuration.starting_surfaces)


def test_source_config_cannot_replace_the_authoritative_hosts(tmp_path: Path) -> None:
    payload = yaml.safe_load(Path("config/official_sources.yaml").read_text(encoding="utf-8"))
    payload["approved_hosts"] = ["example.org"]
    payload["starting_surfaces"][0]["url"] = "https://example.org/reports/"
    path = tmp_path / "unapproved.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="exactly the reviewed authoritative hosts"):
        load_official_source_config(path)


def test_every_starting_surface_must_be_https_and_authoritative(tmp_path: Path) -> None:
    payload = yaml.safe_load(Path("config/official_sources.yaml").read_text(encoding="utf-8"))
    payload["starting_surfaces"][0]["url"] = "http://www.defensoria.gob.pe/reports/"
    path = tmp_path / "http.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="HTTPS authoritative URL"):
        load_official_source_config(path)


def test_source_config_cannot_replace_reviewed_surface_with_another_official_path(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(Path("config/official_sources.yaml").read_text(encoding="utf-8"))
    payload["starting_surfaces"][0]["url"] = "https://www.defensoria.gob.pe/wp-admin/"
    path = tmp_path / "different-surface.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="exact reviewed starting surfaces"):
        load_official_source_config(path)


def test_source_config_cannot_weaken_reviewed_body_or_redirect_bounds(tmp_path: Path) -> None:
    payload = yaml.safe_load(Path("config/official_sources.yaml").read_text(encoding="utf-8"))
    payload["retrieval"]["max_html_body_bytes"] = 6_000_000
    path = tmp_path / "weaker-retrieval.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="exact reviewed retrieval contract"):
        load_official_source_config(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("delay_seconds", 1.99, "at least 2.0"),
        ("retry_cap", 3, "at most 2"),
        ("page_cap", 121, "at most 120"),
        ("landing_page_cap", 25, "at most 24"),
    ],
)
def test_absolute_m1_runtime_limits_reject_unsafe_values(
    field: str, value: float | int, message: str
) -> None:
    payload: dict[str, float | int] = {
        "delay_seconds": 2.0,
        "retry_cap": 2,
        "page_cap": 120,
        "landing_page_cap": 24,
    }
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        DiscoveryRuntimeLimits.model_validate(payload)


def test_cli_style_overrides_may_only_make_the_configured_run_safer() -> None:
    configuration = load_official_source_config(Path("config/official_sources.yaml"))

    safer = resolve_runtime_limits(
        configuration,
        delay_seconds=3.0,
        retry_cap=1,
        page_cap=4,
        landing_page_cap=0,
    )
    assert safer.delay_seconds == 3.0
    assert safer.retry_cap == 1
    assert safer.page_cap == 4
    assert safer.landing_page_cap == 0

    with pytest.raises(ValueError, match="approved configuration"):
        resolve_runtime_limits(configuration, page_cap=121)


def test_live_client_rejects_subminimum_delay_before_any_request() -> None:
    from peru_conflicts.discovery.client import HtmlClient

    with pytest.raises(ValueError, match=r"at least 2\.0"):
        HtmlClient(
            frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"}),
            delay_seconds=1.0,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ("--delay-seconds", "1.99"),
        ("--retry-cap", "3"),
        ("--page-cap", "121"),
        ("--max-landing-pages", "25"),
    ],
)
def test_discovery_cli_rejects_unsafe_limits_before_network_or_output(
    tmp_path: Path,
    arguments: tuple[str, str],
) -> None:
    from peru_conflicts.discovery.cli import main

    output = tmp_path / "must-not-exist"
    with pytest.raises((ValueError, ValidationError)):
        main(["--output", str(output), *arguments])
    assert not output.exists()


def test_cli_output_is_confined_to_repository_cache(tmp_path: Path) -> None:
    repo_root = Path.cwd().resolve()
    assert (
        validate_cli_output_dir(repo_root / ".cache" / "targeted", repo_root)
        == (repo_root / ".cache" / "targeted").resolve()
    )
    with pytest.raises(ValueError, match=r"repository \.cache"):
        validate_cli_output_dir(tmp_path / "external", repo_root)


def test_repeatable_surface_selector_rejects_unknown_and_duplicate_ids() -> None:
    configuration = load_official_source_config(Path("config/official_sources.yaml"))
    selected = select_starting_surfaces(
        configuration,
        ("paz_social_conflict_prevention", "conflict_search_monthly"),
    )
    assert [surface.id for surface in selected] == [
        "paz_social_conflict_prevention",
        "conflict_search_monthly",
    ]
    with pytest.raises(ValueError, match="unknown surface ID"):
        select_starting_surfaces(configuration, ("not_configured",))
    with pytest.raises(ValueError, match="duplicate surface ID"):
        select_starting_surfaces(
            configuration,
            ("conflict_search_monthly", "conflict_search_monthly"),
        )
