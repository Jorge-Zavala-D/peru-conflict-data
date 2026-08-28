from __future__ import annotations

import pytest

from peru_conflicts.discovery.models import CoverageExpectation
from peru_conflicts.discovery.policy import (
    PaginationStopReason,
    PaginationTracker,
    build_coverage_grid,
    classify_host,
    normalize_url,
)

APPROVED = frozenset({"defensoria.gob.pe", "www.defensoria.gob.pe"})
CATALOGUE = "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"


def test_normalize_url_preserves_meaningful_queries_and_removes_tracking() -> None:
    observed = (
        "HTTPS://WWW.DEFENSORIA.GOB.PE:443/categorias_de_documentos/reportes/"
        "?s=Reporte+conflictos&utm_source=browser#top"
    )

    assert normalize_url(observed) == (
        "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/?s=Reporte+conflictos"
    )


def test_normalize_url_resolves_relative_urls_without_rewriting_path_case() -> None:
    assert normalize_url("../Documentos/Reporte-269/", base_url=CATALOGUE) == (
        "https://www.defensoria.gob.pe/categorias_de_documentos/Documentos/Reporte-269/"
    )


@pytest.mark.parametrize(
    "url",
    [
        "mailto:research@example.org",
        "https://user:password@www.defensoria.gob.pe/",
        "//www.defensoria.gob.pe/without-base",
        "https:///missing-host",
    ],
)
def test_normalize_url_rejects_non_http_credentials_and_malformed_urls(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_url(url)


def test_classify_host_does_not_trust_arbitrary_subdomains() -> None:
    assert classify_host(CATALOGUE, APPROVED) == "authoritative"
    assert classify_host("https://cdn.defensoria.gob.pe/report.pdf", APPROVED) == "pending_review"
    assert classify_host("https://example.org/report.pdf", APPROVED) == "pending_review"
    assert classify_host("mailto:research@example.org", APPROVED) == "unsupported"


def test_build_coverage_grid_starts_at_april_2004_and_is_a_hypothesis() -> None:
    grid = build_coverage_grid("2004-04", "2004-06")

    assert grid == (
        CoverageExpectation(
            reference_period="2004-04",
            rationale="Research coverage-grid hypothesis; observed source not asserted.",
        ),
        CoverageExpectation(
            reference_period="2004-05",
            rationale="Research coverage-grid hypothesis; observed source not asserted.",
        ),
        CoverageExpectation(
            reference_period="2004-06",
            rationale="Research coverage-grid hypothesis; observed source not asserted.",
        ),
    )


@pytest.mark.parametrize(
    "start_period,end_period", [("2004-07", "2004-06"), ("2004-13", "2005-01")]
)
def test_build_coverage_grid_rejects_reversed_or_impossible_ranges(
    start_period: str, end_period: str
) -> None:
    with pytest.raises(ValueError):
        build_coverage_grid(start_period, end_period)


def test_pagination_tracker_stops_on_repeated_page() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED, page_cap=5)

    assert tracker.visit(CATALOGUE) is True
    assert tracker.propose_next("/categorias_de_documentos/reportes/page/2/") is not None
    assert tracker.visit("/categorias_de_documentos/reportes/page/2/", base_url=CATALOGUE) is True
    assert tracker.propose_next(CATALOGUE) is None
    assert tracker.stop_reason is PaginationStopReason.REPEATED_URL
    assert tracker.reached_local_terminal is False


def test_missing_next_only_exhausts_a_verified_pagination_contract() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED, pagination_contract_verified=True)
    assert tracker.visit(CATALOGUE) is True
    assert tracker.propose_next(None) is None
    assert tracker.stop_reason is PaginationStopReason.NO_NEXT_LINK
    assert tracker.reached_local_terminal is True
    assert tracker.pagination_exhausted is True


def test_missing_next_does_not_imply_terminal_when_contract_is_unverified() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED, pagination_contract_verified=False)
    assert tracker.visit(CATALOGUE) is True
    assert tracker.propose_next(None) is None
    assert tracker.stop_reason is PaginationStopReason.NO_NEXT_LINK
    assert tracker.reached_local_terminal is True
    assert tracker.pagination_exhausted is False


def test_single_page_surface_terminates_without_claiming_pagination_exhaustion() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED, pagination_contract_verified=True)
    assert tracker.visit(CATALOGUE) is True
    tracker.stop_single_page()
    assert tracker.stop_reason is PaginationStopReason.SINGLE_PAGE
    assert tracker.reached_local_terminal is True
    assert tracker.pagination_exhausted is False


def test_pagination_tracker_rejects_non_authoritative_next_as_incomplete() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED)
    assert tracker.visit(CATALOGUE) is True
    assert tracker.propose_next("https://other.example.org/page/2/") is None
    assert tracker.stop_reason is PaginationStopReason.NON_AUTHORITATIVE_NEXT
    assert tracker.reached_local_terminal is False


def test_pagination_tracker_cap_is_not_complete() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED, page_cap=1)
    assert tracker.visit(CATALOGUE) is True
    assert tracker.propose_next("/categorias_de_documentos/reportes/page/2/") is None
    assert tracker.stop_reason is PaginationStopReason.PAGE_CAP
    assert tracker.reached_local_terminal is False


def test_pagination_tracker_records_explicit_errors_as_incomplete() -> None:
    tracker = PaginationTracker(CATALOGUE, APPROVED)
    tracker.visit(CATALOGUE)
    tracker.stop_error()
    assert tracker.stop_reason is PaginationStopReason.ERROR
    assert tracker.reached_local_terminal is False
