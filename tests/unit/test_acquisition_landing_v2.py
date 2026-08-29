"""Source-preserving landing-page association without global-page inference."""

from __future__ import annotations

import hashlib

import pytest

from peru_conflicts.acquisition.landing import (
    LANDING_ASSOCIATION_PARSER_VERSION,
    LandingAssociationAmbiguous,
    LandingAssociationMissing,
    verify_landing_association,
)

HOSTS = frozenset(("defensoria.gob.pe", "www.defensoria.gob.pe"))
REVIEWED = "https://www.defensoria.gob.pe/wp-content/uploads/2025/12/10.pdf.pdf"


def test_exact_opaque_link_preserves_source_span_without_resolving_identity() -> None:
    html = f"""<!doctype html>
    <html lang="es"><body>
      <article class="documento">
        <h1>Reporte de Conflictos Sociales N.° 261</h1>
        <p>Documento oficial publicado por la Defensoría del Pueblo.</p>
        <a class="download" href="{REVIEWED}">Descargar reporte 261</a>
      </article>
    </body></html>""".encode()

    evidence = verify_landing_association(
        html,
        landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
        reviewed_direct_url=REVIEWED,
        approved_hosts=HOSTS,
        report_number=261,
        association_status="unresolved_opaque_filename",
    )

    assert evidence.parser_version == LANDING_ASSOCIATION_PARSER_VERSION
    assert evidence.landing_body_sha256 == hashlib.sha256(html).hexdigest()
    assert evidence.landing_body_bytes == len(html)
    assert evidence.reviewed_href_original == REVIEWED
    assert "Descargar reporte 261" in evidence.source_span_text
    assert html[evidence.byte_start : evidence.byte_end].decode() == evidence.source_span_text
    assert evidence.character_end > evidence.character_start
    assert evidence.identity_association_status == "unresolved_opaque_filename"
    assert evidence.candidate_url_sha256s == (hashlib.sha256(REVIEWED.encode()).hexdigest(),)


def test_unicode_and_percent_encoded_duplicate_anchors_collapse_to_one_candidate() -> None:
    original = (
        "https://www.defensoria.gob.pe/wp-content/uploads/"
        "Reporte-N\N{DEGREE SIGN}-260\N{EN DASH}Acción.pdf"
    )
    encoded = (
        "https://www.defensoria.gob.pe/wp-content/uploads/"
        "Reporte-N%C2%B0-260%E2%80%93Acci%C3%B3n.pdf"
    )
    html = (
        "<article><h2>Reporte de Conflictos Sociales N.° 260</h2>"
        f'<a href="{original}">Descargar</a><a href="{encoded}">Otra etiqueta</a>'
        "</article>"
    ).encode()

    evidence = verify_landing_association(
        html,
        landing_url="https://www.defensoria.gob.pe/documentos/reporte-260/",
        reviewed_direct_url=encoded,
        approved_hosts=HOSTS,
        report_number=260,
        association_status="visibly_associated",
    )
    assert len(evidence.candidate_url_sha256s) == 1
    assert evidence.reviewed_url_normalized.endswith("Reporte-N%C2%B0-260%E2%80%93Acci%C3%B3n.pdf")


def test_missing_reviewed_link_ignores_unrelated_institutional_pdf() -> None:
    html = b"""
    <main>
      <article><h2>Reporte de Conflictos Sociales N. 261</h2><p>Sin descarga.</p></article>
      <aside>
        <a href="https://www.defensoria.gob.pe/informe-institucional.pdf">
          Informe anual
        </a>
      </aside>
    </main>"""

    with pytest.raises(LandingAssociationMissing):
        verify_landing_association(
            html,
            landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
            reviewed_direct_url=REVIEWED,
            approved_hosts=HOSTS,
            report_number=261,
            association_status="unresolved_opaque_filename",
        )


def test_distinct_pdf_candidate_in_same_qualified_card_is_ambiguous() -> None:
    html = f"""
    <article>
      <h2>Reporte de Conflictos Sociales N.° 261</h2>
      <a href="{REVIEWED}">Descargar</a>
      <a href="https://www.defensoria.gob.pe/wp-content/uploads/reporte-261-revisado.pdf">
        Otra descarga del reporte 261
      </a>
    </article>""".encode()

    with pytest.raises(LandingAssociationAmbiguous):
        verify_landing_association(
            html,
            landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
            reviewed_direct_url=REVIEWED,
            approved_hosts=HOSTS,
            report_number=261,
            association_status="unresolved_opaque_filename",
        )


@pytest.mark.parametrize(
    "attributes",
    (
        'class="grid-column" id="documento"',
        'id="documento" class="grid-column"',
    ),
)
@pytest.mark.parametrize("report_number", (261, 263))
def test_card_id_and_class_attribute_order_cannot_hide_competing_pdf(
    attributes: str,
    report_number: int,
) -> None:
    reviewed = f"https://www.defensoria.gob.pe/wp-content/uploads/{report_number}.pdf"
    competing = (
        f"https://www.defensoria.gob.pe/wp-content/uploads/reporte-{report_number}-revisado.pdf"
    )
    html = f"""
    <div {attributes}>
      <h2>Reporte de Conflictos Sociales N.° {report_number}</h2>
      <a href="{reviewed}">Descargar</a>
      <a href="{competing}">Otra descarga del reporte {report_number}</a>
    </div>""".encode()

    with pytest.raises(LandingAssociationAmbiguous):
        verify_landing_association(
            html,
            landing_url=f"https://www.defensoria.gob.pe/documentos/reporte-{report_number}/",
            reviewed_direct_url=reviewed,
            approved_hosts=HOSTS,
            report_number=report_number,
            association_status="unresolved_opaque_filename",
        )


def test_competing_candidate_uses_final_outer_card_context_independent_of_order() -> None:
    competing = "https://www.defensoria.gob.pe/wp-content/uploads/reporte-261-revisado.pdf"
    html = f"""
    <article>
      <div class="downloads">
        <a href="{REVIEWED}">Descargar</a>
        <div><a href="{competing}">Otra descarga</a></div>
      </div>
      <h2>Reporte de Conflictos Sociales N.° 261</h2>
    </article>""".encode()

    with pytest.raises(LandingAssociationAmbiguous):
        verify_landing_association(
            html,
            landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
            reviewed_direct_url=REVIEWED,
            approved_hosts=HOSTS,
            report_number=261,
            association_status="unresolved_opaque_filename",
        )


def test_shared_layout_wrapper_does_not_turn_unrelated_pdf_into_competitor() -> None:
    unrelated = "https://www.defensoria.gob.pe/wp-content/uploads/reporte-261-anual.pdf"
    html = f"""
    <div class="page-layout">
      <article class="documento">
        <a href="{REVIEWED}">Descargar</a>
        <h2>Reporte de Conflictos Sociales N.° 261</h2>
      </article>
      <aside>
        <a href="{unrelated}">Reporte anual institucional</a>
      </aside>
    </div>""".encode()

    evidence = verify_landing_association(
        html,
        landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
        reviewed_direct_url=REVIEWED,
        approved_hosts=HOSTS,
        report_number=261,
        association_status="unresolved_opaque_filename",
    )

    assert evidence.candidate_url_sha256s == (hashlib.sha256(REVIEWED.encode()).hexdigest(),)


def test_unsafe_href_is_hashed_but_never_retained_verbatim_in_error() -> None:
    secret_href = "https://www.defensoria.gob.pe/file.pdf?token=secret-value"
    html = f"""
    <article><h2>Reporte de Conflictos Sociales N.° 261</h2>
      <a href="{secret_href}">Descarga temporal</a>
    </article>""".encode()

    with pytest.raises(LandingAssociationMissing) as caught:
        verify_landing_association(
            html,
            landing_url="https://www.defensoria.gob.pe/documentos/reporte-261/",
            reviewed_direct_url=REVIEWED,
            approved_hosts=HOSTS,
            report_number=261,
            association_status="unresolved_opaque_filename",
        )
    assert "secret-value" not in str(caught.value)
    assert hashlib.sha256(secret_href.encode()).hexdigest() in caught.value.rejected_href_sha256s
