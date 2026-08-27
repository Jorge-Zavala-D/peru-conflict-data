from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from peru_conflicts.discovery.html import parse_discovery_page
from peru_conflicts.discovery.models import UrlRole

CAPTURED_AT = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
CATALOGUE_URL = "https://www.defensoria.gob.pe/categorias_de_documentos/reportes/"


def _fixture(name: str) -> str:
    return Path("tests/fixtures/discovery", name).read_text(encoding="utf-8")


def test_parser_extracts_visible_identity_metadata_file_links_and_next_page() -> None:
    parsed = parse_discovery_page(
        _fixture("catalogue_page_1.html"),
        page_url=CATALOGUE_URL,
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id="catalogue-page-1",
        captured_at=CAPTURED_AT,
    )

    assert parsed.next_url == "/categorias_de_documentos/reportes/page/2/"
    assert parsed.publication_date_original == "13/08/2026"
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record.candidate_report_number == 269
    assert record.candidate_reference_period == "2026-07"
    assert record.url_observations[0].role is UrlRole.CATALOGUE_PAGE
    assert any(item.role is UrlRole.LANDING_PAGE for item in record.url_observations)
    assert any(item.role is UrlRole.DIRECT_DOWNLOAD for item in record.url_observations)
    assert any(
        evidence.evidence_type.value == "document_visible" for evidence in record.identity_evidence
    )


def test_parser_excludes_non_conflict_items_and_preserves_duplicate_link_once() -> None:
    html = _fixture("catalogue_page_1.html").replace(
        "</article>\n    <article>",
        "</article>\n    <article>",
    )
    parsed = parse_discovery_page(
        html,
        page_url=CATALOGUE_URL,
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id="catalogue-page-1",
        captured_at=CAPTURED_AT,
    )

    assert all(record.candidate_report_number != 0 for record in parsed.records)
    assert len(parsed.records) == 1
    assert len(parsed.links) == len({link.url for link in parsed.links})


def test_parser_keeps_unknown_identity_as_a_provisional_record() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><a href='/documentos/reporte-de-conflictos-sociales/'>"
            "Reporte mensual de conflictos sociales</a></body></html>"
        ),
        page_url=CATALOGUE_URL,
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="search-page-1",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 1
    assert parsed.records[0].candidate_report_number is None
    assert parsed.records[0].candidate_reference_period is None
    assert parsed.records[0].uncertainty_notes


def test_parser_uses_visible_heading_and_not_generic_html_title() -> None:
    parsed = parse_discovery_page(
        (
            "<html><head><title>Defensoria del Pueblo Peru</title></head><body><h1>"
            "Reporte de conflictos sociales N.° 268 - junio 2026</h1></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-268/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-268",
        captured_at=CAPTURED_AT,
    )

    assert parsed.records[0].candidate_report_number == 268
    assert parsed.records[0].candidate_reference_period == "2026-06"


def test_parser_does_not_treat_a_four_digit_year_as_a_report_number() -> None:
    parsed = parse_discovery_page(
        "<html><body><h1>Reporte Mensual de Conflictos Sociales 2004</h1></body></html>",
        page_url="https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/",
        page_role=UrlRole.THEMATIC_PAGE,
        observation_id="thematic-2004",
        captured_at=CAPTURED_AT,
    )

    assert parsed.records[0].candidate_report_number is None
    assert parsed.records[0].candidate_reference_period is None


def test_parser_does_not_attach_unrelated_page_pdfs_to_every_candidate() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body>"
            "<a href='/documentos/reporte-269-julio-2026/'>"
            "Reporte de conflictos sociales n.° 269 - julio 2026</a>"
            "<a href='/documentos/reporte-268-junio-2026/'>"
            "Reporte de conflictos sociales n.° 268 - junio 2026</a>"
            "<a href='/wp-content/uploads/2025/05/Organigrama.pdf'>Organigrama institucional</a>"
            "</body></html>"
        ),
        page_url=CATALOGUE_URL,
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id="catalogue-many",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 2
    assert all(
        all("Organigrama.pdf" not in observation.url for observation in record.url_observations)
        for record in parsed.records
    )
    assert any(
        "reporte-269-julio-2026" in observation.url
        for observation in parsed.records[0].url_observations
    )
    assert all(
        "reporte-268-junio-2026" not in observation.url
        for observation in parsed.records[0].url_observations
    )
