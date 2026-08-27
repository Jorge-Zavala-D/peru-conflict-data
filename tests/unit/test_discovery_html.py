from __future__ import annotations

# ruff: noqa: RUF001 -- exact source-original Spanish punctuation is test evidence.
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    assert parsed.source_page_title_original == "Reportes institucionales"
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record.candidate_report_number == 269
    assert record.candidate_reference_period == "2026-07"
    assert record.source_page_title_original == parsed.source_page_title_original
    assert record.entry_title_original == ("Reporte de conflictos sociales n.° 269 – julio 2026")
    assert record.entry_publication_date_original == "13/08/2026"
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


def test_catalogue_nested_cards_keep_each_source_entry_isolated() -> None:
    parsed = parse_discovery_page(
        _fixture("catalogue_nested_cards.html"),
        page_url="https://www.defensoria.gob.pe/categorias_de_documentos/reportes/page/3/",
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id="catalogue-nested-cards",
        captured_at=CAPTURED_AT,
    )

    assert [record.candidate_report_number for record in parsed.records] == [260, 259]
    assert [record.candidate_reference_period for record in parsed.records] == [
        "2025-10",
        "2025-09",
    ]
    assert [record.entry_publication_date_original for record in parsed.records] == [
        "noviembre 14,2025",
        "octubre 21,2025",
    ]
    direct_urls = [
        [
            observation.url
            for observation in record.url_observations
            if observation.role is UrlRole.DIRECT_DOWNLOAD
        ]
        for record in parsed.records
    ]
    assert direct_urls == [
        ["https://www.defensoria.gob.pe/wp-content/uploads/2025/11/Conflictos-260.pdf"],
        ["https://www.defensoria.gob.pe/wp-content/uploads/2025/10/Conflictos-259.pdf"],
    ]


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


def test_parser_preserves_landing_date_with_time_without_publication_label() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><h1>Reporte de conflictos sociales n.° 269 - julio 2026</h1>"
            "<div class='box-fecha'><span>5:24 pm 13/08/2026</span></div></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-269/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-269-date",
        captured_at=CAPTURED_AT,
    )

    assert parsed.records[0].entry_publication_date_original == "13/08/2026"


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


@pytest.mark.parametrize(
    ("source_title", "expected_period", "observed_value"),
    [
        ("Reporte Mensual de Conflictos Sociales N° 112 – Jun-2013", "2013-06", "Jun-2013"),
        (
            "Reporte de Conflictos Sociales N° 206 Abril -2021",
            "2021-04",
            "Abril -2021",
        ),
        (
            "Reporte Mensual de Conflictos Sociales N° 23 Enero 2006",
            "2006-01",
            "Enero 2006",
        ),
        (
            "Reporte Mensual de Conflictos Sociales N° 23 - Enero 2006",
            "2006-01",
            "Enero 2006",
        ),
        (
            "Reporte Mensual de Conflictos Sociales N° 31 Junio 2006",
            "2006-06",
            "Junio 2006",
        ),
    ],
)
def test_parser_preserves_historical_abbreviated_or_hyphenated_month_evidence(
    source_title: str,
    expected_period: str,
    observed_value: str,
) -> None:
    parsed = parse_discovery_page(
        f"<html><body><article><h4>{source_title}</h4></article></body></html>",
        page_url=CATALOGUE_URL,
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id=f"historical-month-{expected_period}",
        captured_at=CAPTURED_AT,
    )

    record = parsed.records[0]
    assert record.candidate_reference_period == expected_period
    period_evidence = [
        evidence
        for evidence in record.identity_evidence
        if evidence.subject.value == "reference_period"
    ]
    assert [evidence.observed_value for evidence in period_evidence] == [observed_value]


@pytest.mark.parametrize(
    "source_title",
    [
        "Reporte de conflictos sociales N° 112 publicado el 12 Jun 2013",
        "Reporte de conflictos sociales N° 112 publicado el 12 junio 2013",
        "Reporte de conflictos sociales N° 112 publicado el 12, junio 2013",
        "Reporte de conflictos sociales N° 112 publicado el 12. junio 2013",
        "Reporte de conflictos sociales N° 112 publicado el 2013-junio-12",
        "Reporte de conflictos sociales N° 112 publicado el 2013 junio 12",
        "Reporte de conflictos sociales N° 206 código abril2021",
        "Reporte de conflictos sociales N° 112 código 2013abril",
    ],
)
def test_parser_does_not_turn_dates_or_compact_identifiers_into_reference_periods(
    source_title: str,
) -> None:
    parsed = parse_discovery_page(
        f"<html><body><article><h4>{source_title}</h4></article></body></html>",
        page_url=CATALOGUE_URL,
        page_role=UrlRole.CATALOGUE_PAGE,
        observation_id="non-reference-month-context",
        captured_at=CAPTURED_AT,
    )

    record = parsed.records[0]
    assert record.candidate_reference_period is None
    assert all(
        evidence.subject.value != "reference_period" for evidence in record.identity_evidence
    )


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


def test_parser_preserves_opaque_landing_download_as_unresolved_observation() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><article><h1>Reporte de conflictos sociales n.° 263 - enero 2026</h1>"
            "<a href='/wp-content/uploads/2026/02/10.pdf'>Descargar</a>"
            "</article><aside><a href='/wp-content/uploads/2025/05/Global-policy.pdf'>"
            "Política global</a></aside>"
            "<footer><a href='/wp-content/uploads/2025/05/Organigrama.pdf'>"
            "Organigrama</a></footer></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-263/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-263-opaque",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 2
    candidate, unresolved = parsed.records
    assert candidate.candidate_report_number == 263
    assert all(
        observation.role is not UrlRole.DIRECT_DOWNLOAD
        for observation in candidate.url_observations
    )
    assert unresolved.candidate_report_number is None
    assert any(
        observation.role is UrlRole.DIRECT_DOWNLOAD and observation.url.endswith("/10.pdf")
        for observation in unresolved.url_observations
    )
    assert all(
        not observation.url.endswith(("/Organigrama.pdf", "/Global-policy.pdf"))
        for record in parsed.records
        for observation in record.url_observations
    )
    assert unresolved.uncertainty_notes


def test_parser_preserves_2004_2005_bundle_entries_and_zip_links_without_months() -> None:
    parsed = parse_discovery_page(
        _fixture("thematic_historical_bundles.html"),
        page_url=(
            "https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/"
        ),
        page_role=UrlRole.THEMATIC_PAGE,
        observation_id="thematic-bundles",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 2
    by_title = {record.entry_title_original: record for record in parsed.records}
    report_2005 = by_title["Reporte Conflictos Sociales 2005"]
    report_2004 = by_title["Reporte Mensual de Conflictos Sociales 2004"]
    assert report_2005.candidate_report_number is None
    assert report_2005.candidate_reference_period is None
    assert report_2005.entry_publication_date_original == "diciembre 12,2005"
    assert report_2004.candidate_report_number is None
    assert report_2004.candidate_reference_period is None
    assert report_2004.entry_publication_date_original == "diciembre 23,2004"
    assert {
        observation.url
        for record in parsed.records
        for observation in record.url_observations
        if observation.role is UrlRole.DIRECT_DOWNLOAD
    } == {
        "https://www.defensoria.gob.pe/wp-content/uploads/2018/08/conflictos_sociales2004.zip",
        "https://www.defensoria.gob.pe/wp-content/uploads/2018/08/conflictos_sociales2005.zip",
    }


def test_parser_extracts_exact_number_month_pairs_from_scoped_2006_cards() -> None:
    parsed = parse_discovery_page(
        _fixture("thematic_historical_numbered_2006.html"),
        page_url=(
            "https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/"
        ),
        page_role=UrlRole.THEMATIC_PAGE,
        observation_id="thematic-2006",
        captured_at=CAPTURED_AT,
    )

    observed = {
        record.candidate_report_number: record.candidate_reference_period
        for record in parsed.records
    }
    assert observed == {number: f"2006-{number - 22:02d}" for number in range(23, 35)}
    assert len(parsed.records) == 12
    assert all(number not in observed for number in range(1, 23))
    assert {record.entry_title_original for record in parsed.records} == {"Conflictos Sociales"}
    expected_publication_dates = {
        23: "marzo 28,2006",
        24: "marzo 28,2006",
        25: "mayo 02,2006",
        26: "junio 06,2006",
        27: "junio 06,2006",
        28: "julio 10,2006",
        29: "agosto 08,2006",
        30: "septiembre 15,2006",
        31: "octubre 11,2006",
        32: "diciembre 05,2006",
        33: "diciembre 05,2006",
        34: "enero 08,2007",
    }
    assert {
        record.candidate_report_number: record.entry_publication_date_original
        for record in parsed.records
    } == expected_publication_dates
    report_23 = next(record for record in parsed.records if record.candidate_report_number == 23)
    report_24 = next(record for record in parsed.records if record.candidate_report_number == 24)
    report_34 = next(record for record in parsed.records if record.candidate_report_number == 34)
    assert report_23.entry_publication_date_original == "marzo 28,2006"
    assert report_24.entry_publication_date_original == "marzo 28,2006"
    assert report_34.entry_publication_date_original == "enero 08,2007"
    assert report_23.entry_description_original == (
        "Reporte Mensual N° 23 Conflictos Sociales – Enero 2006"
    )
    assert all(
        "documento-dialogo" not in observation.url
        for record in parsed.records
        for observation in record.url_observations
    )
    assert all(
        len(
            [
                observation
                for observation in record.url_observations
                if observation.role is UrlRole.DIRECT_DOWNLOAD
            ]
        )
        == 1
        for record in parsed.records
    )
    assert all("press-note" not in link.url for link in parsed.links)


def test_parser_uses_immediate_numeric_search_page_not_last_page_shortcut() -> None:
    parsed = parse_discovery_page(
        _fixture("search_page_1_live_pagination.html"),
        page_url=("https://www.defensoria.gob.pe/?s=Reporte+Mensual+de+Conflictos+Sociales"),
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="search-page-1-live",
        captured_at=CAPTURED_AT,
    )

    assert parsed.next_url == (
        "https://www.defensoria.gob.pe/page/2/?s=Reporte+Mensual+de+Conflictos+Sociales"
    )
    assert all("navigation-report" not in link.url for link in parsed.links)


def test_parser_uses_next_numeric_page_midstream_and_stops_at_terminal_page() -> None:
    page_two = parse_discovery_page(
        _fixture("search_page_2_live_pagination.html"),
        page_url=("https://www.defensoria.gob.pe/page/2/?s=Reporte+Mensual+de+Conflictos+Sociales"),
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="search-page-2-live",
        captured_at=CAPTURED_AT,
    )
    terminal = parse_discovery_page(
        _fixture("search_page_9_live_terminal.html"),
        page_url=("https://www.defensoria.gob.pe/page/9/?s=Reporte+Mensual+de+Conflictos+Sociales"),
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="search-page-9-live",
        captured_at=CAPTURED_AT,
    )

    assert page_two.next_url == (
        "https://www.defensoria.gob.pe/page/3/?s=Reporte+Mensual+de+Conflictos+Sociales"
    )
    assert terminal.next_url is None


def test_pagination_ignores_article_rel_next_and_supports_accessible_next_controls() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><article><a rel='next' href='/documentos/next-article/'>"
            "Siguiente artículo</a></article><nav class='pagination'>"
            "<a class='next page-numbers' aria-label='Página siguiente' "
            "href='/page/2/?s=Reporte+conflictos'>Avanzar</a></nav></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/?s=Reporte+conflictos",
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="accessible-pagination",
        captured_at=CAPTURED_AT,
    )

    assert parsed.next_url == "/page/2/?s=Reporte+conflictos"


@pytest.mark.parametrize(
    "next_attributes",
    [
        "rel='next'",
        "class='next page-numbers'",
        "aria-label='Página siguiente'",
        "title='Siguiente página'",
    ],
)
def test_pagination_uses_explicit_next_before_numeric_last_page_and_ignores_post_nav(
    next_attributes: str,
) -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><nav class='post-navigation'>"
            "<div class='nav-links'><a rel='next' href='/documentos/articulo-siguiente/'>"
            "Siguiente artículo</a></div></nav><nav aria-label='Paginación'>"
            "<span aria-current='page'>2</span>"
            f"<a {next_attributes} href='/page/3/?s=Reporte+conflictos'>Avanzar</a>"
            "<a class='page-numbers' href='/page/9/?s=Reporte+conflictos'>9</a>"
            "</nav></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/page/2/?s=Reporte+conflictos",
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id=f"explicit-next-{next_attributes}",
        captured_at=CAPTURED_AT,
    )

    assert parsed.next_url == "/page/3/?s=Reporte+conflictos"


def test_accessible_pagination_terminal_does_not_reverse_to_a_previous_page() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><nav aria-label='Paginación'>"
            "<a class='page-numbers' href='/page/8/?s=Reporte+conflictos'>8</a>"
            "<span aria-current='page'>9</span></nav></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/page/9/?s=Reporte+conflictos",
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="accessible-terminal",
        captured_at=CAPTURED_AT,
    )

    assert parsed.next_url is None


def test_parser_keeps_search_result_titles_dates_descriptions_and_links_independent() -> None:
    parsed = parse_discovery_page(
        _fixture("search_result_item_dates.html"),
        page_url="https://www.defensoria.gob.pe/?s=Reporte+conflictos",
        page_role=UrlRole.SEARCH_RESULT_PAGE,
        observation_id="search-independent-items",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 2
    by_number = {record.candidate_report_number: record for record in parsed.records}
    assert by_number[269].source_page_title_original == "Resultados de su búsqueda"
    assert by_number[269].entry_title_original == (
        "Reporte de conflictos sociales n.º 269 – julio 2026"
    )
    assert by_number[269].entry_publication_date_original == "jueves, 13 agosto 2026"
    assert by_number[268].entry_publication_date_original == "jueves, 16 julio 2026"
    assert all(
        "reporte-268" not in observation.url for observation in by_number[269].url_observations
    )
    assert all(
        "reporte-269" not in observation.url for observation in by_number[268].url_observations
    )


def test_generic_page_metadata_and_chrome_do_not_create_or_contaminate_entries() -> None:
    parsed = parse_discovery_page(
        _fixture("thematic_page_chrome.html"),
        page_url=(
            "https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/"
        ),
        page_role=UrlRole.THEMATIC_PAGE,
        observation_id="thematic-chrome",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record.candidate_report_number == 35
    assert record.candidate_reference_period == "2007-01"
    assert record.entry_title_original == "Reporte Mensual de Conflictos Sociales N° 35"
    assert record.entry_publication_date_original == "febrero 12,2007"
    assert all("navegacion" not in observation.url for observation in record.url_observations)


@pytest.mark.parametrize(
    ("page_role", "html"),
    [
        (
            UrlRole.SEARCH_RESULT_PAGE,
            "<html><body><div class='search-content'></div><main>"
            "<a href='/documentos/falso/'>Reporte de conflictos sociales N.° 999"
            " - enero 2020</a></main></body></html>",
        ),
        (
            UrlRole.THEMATIC_PAGE,
            "<html><body><div id='pills-otraspub'></div><div id='pills-prensa'>"
            "<h3>Reporte de conflictos sociales N.° 999 - enero 2020</h3>"
            "</div></body></html>",
        ),
    ],
)
def test_existing_canonical_container_prevents_page_wide_candidate_fallback(
    page_role: UrlRole,
    html: str,
) -> None:
    parsed = parse_discovery_page(
        html,
        page_url="https://www.defensoria.gob.pe/superficie-oficial/",
        page_role=page_role,
        observation_id=f"empty-canonical-{page_role.value}",
        captured_at=CAPTURED_AT,
    )

    assert parsed.records == ()
    assert parsed.links == ()


def test_landing_page_root_fallback_excludes_header_navigation_and_aside_chrome() -> None:
    parsed = parse_discovery_page(
        (
            "<html><body><header><h1>Defensoría del Pueblo</h1>"
            "<time>01/01/2000</time>"
            "<nav><a href='/documentos/otro/'>Reporte de conflictos sociales N.° 999"
            " - enero 2020</a></nav></header><main>"
            "<h1>Reporte de conflictos sociales N.° 269 - julio 2026</h1>"
            "<p>Reporte de conflictos sociales correspondiente a julio 2026.</p>"
            "<span>13/08/2026</span>"
            "<a href='/wp-content/uploads/2026/08/Reporte-269.pdf'>Descargar PDF</a>"
            "</main><aside><h2>Reporte de conflictos sociales N.° 998</h2>"
            "<span>02/02/2000</span></aside>"
            "</body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-269/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-with-chrome",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record.candidate_report_number == 269
    assert record.candidate_reference_period == "2026-07"
    assert record.source_page_title_original == (
        "Reporte de conflictos sociales N.° 269 - julio 2026"
    )
    assert record.entry_title_original == record.source_page_title_original
    assert record.entry_publication_date_original == "13/08/2026"
    assert all("/documentos/otro/" not in item.url for item in record.url_observations)


def test_landing_primary_heading_wins_over_related_report_links() -> None:
    related = "https://www.defensoria.gob.pe/documentos/reporte-268/"
    parsed = parse_discovery_page(
        (
            "<html><body><main><h1>Reporte de conflictos sociales N.° 269 - julio 2026</h1>"
            "<p>Reporte de conflictos sociales correspondiente a julio 2026.</p>"
            "<a href='/wp-content/uploads/2026/08/Reporte-269.pdf'>Descargar PDF</a>"
            "<section><h2>También puede consultar</h2>"
            "<a href='/documentos/reporte-268/'>Reporte de conflictos sociales N.° 268"
            " - junio 2026</a></section></main></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-269/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-primary-heading",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 1
    assert parsed.records[0].candidate_report_number == 269
    assert all(item.url != related for item in parsed.records[0].url_observations)
    assert all(link.url != related for link in parsed.links)


def test_landing_main_scope_preserves_opaque_download_as_unresolved_observation() -> None:
    opaque = "https://www.defensoria.gob.pe/wp-content/uploads/2026/02/10.pdf"
    parsed = parse_discovery_page(
        (
            "<html><body><main><h1>Reporte de conflictos sociales N.° 263 - enero 2026</h1>"
            "<p>Reporte de conflictos sociales correspondiente a enero 2026.</p>"
            "<a href='/wp-content/uploads/2026/02/10.pdf'>Descargar PDF</a>"
            "</main></body></html>"
        ),
        page_url="https://www.defensoria.gob.pe/documentos/reporte-263/",
        page_role=UrlRole.LANDING_PAGE,
        observation_id="landing-opaque-download",
        captured_at=CAPTURED_AT,
    )

    assert any(record.candidate_report_number == 263 for record in parsed.records)
    unresolved = [
        record
        for record in parsed.records
        if any(observation.url == opaque for observation in record.url_observations)
    ]
    assert len(unresolved) == 1
    assert unresolved[0].candidate_report_number is None
    assert "unresolved source candidate" in unresolved[0].uncertainty_notes[0]


def test_heading_fragments_are_aggregated_once_across_h3_through_h6() -> None:
    html = (
        "<html><body><h1>Paz social y prevención de conflictos</h1>"
        "<div class='card'><div class='card-body'>"
        "<h3>Reporte <span>Mensual</span> de Conflictos Sociales N° 36</h3>"
        "<h5><strong>marzo 07,2007</strong></h5>"
        "<p>Reporte Mensual Nº 36 Conflictos Sociales – Febrero 2007</p>"
        "<a href='/wp-content/uploads/2018/05/conflictos_sociales36.pdf'>"
        "<button>Descargar</button></a></div></div></body></html>"
    )
    parsed = parse_discovery_page(
        html,
        page_url=(
            "https://www.defensoria.gob.pe/areas_tematicas/paz-social-y-prevencion-de-conflictos/"
        ),
        page_role=UrlRole.THEMATIC_PAGE,
        observation_id="thematic-fragmented-heading",
        captured_at=CAPTURED_AT,
    )

    assert len(parsed.records) == 1
    assert parsed.records[0].entry_title_original == (
        "Reporte Mensual de Conflictos Sociales N° 36"
    )
    assert parsed.records[0].entry_publication_date_original == "marzo 07,2007"
    assert parsed.records[0].candidate_reference_period == "2007-02"
