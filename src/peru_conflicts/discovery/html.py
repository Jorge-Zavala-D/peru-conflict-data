"""Deterministic, metadata-only HTML parsing for official discovery surfaces."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit

from peru_conflicts.discovery.models import (
    CandidateSourceRelation,
    CandidateSourceRelationType,
    IdentityEvidence,
    IdentityEvidenceType,
    IdentitySubject,
    ProvisionalDiscoveryRecord,
    UrlObservation,
    UrlRole,
)
from peru_conflicts.discovery.policy import normalize_url

_MONTHS: Final[dict[str, int]] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "setiembre": 9,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_MONTH_PATTERN: Final[str] = "|".join(_MONTHS)
_REPORT_NUMBER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bn\s*[.º°oª]*\s*[-:]?\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\b(?:reporte|report[eé])\s+(?:n\s*[.º°oª]*\s*)?(\d{1,4})\b", re.IGNORECASE),
)
_PUBLICATION_DATE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:publicad[oa]|fecha\s+de\s+publicaci[oó]n)[^0-9]{0,30}(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)
_SLASH_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_RELEVANT_TEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bconflictos?(?:\s+sociales)?\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class DiscoveredLink:
    """One visible link with a source-safe role classification."""

    url: str
    text: str
    role: UrlRole
    in_article: bool


@dataclass(frozen=True, slots=True)
class ParsedDiscoveryPage:
    """Parsed page metadata and provisional candidate records."""

    observation: UrlObservation
    records: tuple[ProvisionalDiscoveryRecord, ...]
    links: tuple[DiscoveredLink, ...]
    next_url: str | None
    page_title_original: str | None
    publication_date_original: str | None


@dataclass(slots=True)
class _Anchor:
    href: str
    rel: str
    chunks: list[str]
    in_article: bool

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self.chunks))


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[_Anchor] = []
        self.headings: list[str] = []
        self.visible_chunks: list[str] = []
        self.publication_metadata: str | None = None
        self._anchor: _Anchor | None = None
        self._heading_depth = 0
        self._article_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript", "footer"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lower_tag == "article":
            self._article_depth += 1
        if lower_tag == "a" and attributes.get("href"):
            self._anchor = _Anchor(
                href=attributes["href"],
                rel=attributes.get("rel", ""),
                chunks=[],
                in_article=self._article_depth > 0,
            )
        if lower_tag in {"h1", "h2"}:
            self._heading_depth += 1
        if lower_tag == "meta":
            key = attributes.get("property", "").lower() or attributes.get("name", "").lower()
            if key in {"article:published_time", "date", "publication_date"}:
                self.publication_metadata = attributes.get("content") or None

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript", "footer"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if lower_tag == "a" and self._anchor is not None:
            self.anchors.append(self._anchor)
            self._anchor = None
        if lower_tag == "article" and self._article_depth:
            self._article_depth -= 1
        if lower_tag in {"h1", "h2"} and self._heading_depth:
            self._heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = _clean_text(data)
        if not cleaned:
            return
        self.visible_chunks.append(cleaned)
        if self._anchor is not None:
            self._anchor.chunks.append(cleaned)
        if self._heading_depth:
            self.headings.append(cleaned)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _link_role(url: str) -> UrlRole | None:
    parsed = urlsplit(url)
    path = parsed.path.lower()
    if path.endswith(".pdf"):
        return UrlRole.DIRECT_DOWNLOAD
    if "/documentos/" in path:
        return UrlRole.LANDING_PAGE
    return None


def _parse_report_number(text: str) -> tuple[int | None, str | None]:
    for pattern in _REPORT_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            value = int(match.group(1))
            if value < 1900 or value > 2100:
                return value, match.group(0)
    return None, None


def _parse_reference_period(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        rf"\b({_MONTH_PATTERN})\s+(\d{{4}})\b|\b(\d{{4}})\s+({_MONTH_PATTERN})\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    if match.group(1):
        month_name, year_text = match.group(1).lower(), match.group(2)
    else:
        year_text, month_name = match.group(3), match.group(4).lower()
    return f"{int(year_text):04d}-{_MONTHS[month_name]:02d}", match.group(0)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _link_matches_candidate(
    link: DiscoveredLink,
    *,
    candidate_text: str,
    report_number: int | None,
) -> bool:
    """Associate only visibly related links; never attach every page PDF."""

    if link.role is UrlRole.LANDING_PAGE:
        return link.text == candidate_text
    if link.role is not UrlRole.DIRECT_DOWNLOAD:
        return False
    haystack = f"{link.url} {link.text}".lower()
    return report_number is not None and bool(re.search(rf"(?<!\d){report_number}(?!\d)", haystack))


def _candidate_texts(parser: _MetadataParser) -> list[str]:
    candidates: list[str] = []
    for anchor in parser.anchors:
        text = anchor.text
        if (
            text
            and not urlsplit(anchor.href).path.lower().endswith(".pdf")
            and _RELEVANT_TEXT_RE.search(text)
        ):
            candidates.append(text)
    for heading in parser.headings:
        if heading and _RELEVANT_TEXT_RE.search(heading) and heading not in candidates:
            candidates.append(heading)
    return candidates


def parse_discovery_page(
    html: str,
    *,
    page_url: str,
    page_role: UrlRole,
    observation_id: str,
    captured_at: datetime,
    observation: UrlObservation | None = None,
) -> ParsedDiscoveryPage:
    """Parse visible page metadata without requesting or interpreting linked files."""

    parser = _MetadataParser()
    parser.feed(html)
    parser.close()
    normalized_page_url = normalize_url(page_url)
    if observation is None:
        page_observation = UrlObservation(
            observation_id=observation_id,
            role=page_role,
            url=normalized_page_url,
            captured_at=captured_at,
        )
    else:
        if (
            observation.observation_id != observation_id
            or observation.role is not page_role
            or observation.url != normalized_page_url
        ):
            raise ValueError("supplied page observation does not match parser arguments")
        page_observation = observation

    seen_links: set[str] = set()
    links: list[DiscoveredLink] = []
    for anchor in parser.anchors:
        try:
            normalized = normalize_url(anchor.href, base_url=normalized_page_url)
        except ValueError:
            continue
        if normalized in seen_links:
            continue
        role = _link_role(normalized)
        if role is None:
            continue
        seen_links.add(normalized)
        links.append(
            DiscoveredLink(
                url=normalized,
                text=anchor.text,
                role=role,
                in_article=anchor.in_article,
            )
        )

    next_url: str | None = None
    for anchor in parser.anchors:
        rel_tokens = {token.lower() for token in anchor.rel.split()}
        if "next" in rel_tokens or anchor.text.lower() in {
            "next",
            "siguiente",
            "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}",
            "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}",
        }:
            next_url = anchor.href
            break

    page_title = parser.headings[0] if parser.headings else None
    visible_text = " ".join(parser.visible_chunks)
    publication_date = _PUBLICATION_DATE_RE.search(visible_text)
    if publication_date is None:
        publication_date = _SLASH_DATE_RE.search(visible_text)
    publication_date_original = (
        publication_date.group(1) if publication_date else parser.publication_metadata
    )
    candidate_texts = _candidate_texts(parser)
    if not candidate_texts and page_title and _RELEVANT_TEXT_RE.search(page_title):
        candidate_texts = [page_title]
    if not candidate_texts and links:
        candidate_texts = [link.text for link in links if _RELEVANT_TEXT_RE.search(link.text)]
    if not candidate_texts and links:
        candidate_texts = [" ".join(filter(None, (page_title, links[0].text)))]

    records: list[ProvisionalDiscoveryRecord] = []
    used_link_urls: set[str] = set()
    for index, text in enumerate(candidate_texts):
        report_number, number_observed = _parse_report_number(text)
        reference_period, period_observed = _parse_reference_period(text)
        record_key = _stable_id(
            "discovery",
            normalized_page_url,
            str(index),
            str(report_number),
            str(reference_period),
        )
        record_observations = [page_observation]
        relevant_links = [
            link
            for link in links
            if _link_matches_candidate(
                link,
                candidate_text=text,
                report_number=report_number,
            )
        ]
        relations: list[CandidateSourceRelation] = []
        for link_index, link in enumerate(relevant_links):
            used_link_urls.add(link.url)
            link_observation_id = _stable_id("url", record_key, str(link_index), link.url)
            link_observation = UrlObservation(
                observation_id=link_observation_id,
                role=link.role,
                url=link.url,
                captured_at=captured_at,
                content_type=None,
            )
            if link.url == normalized_page_url:
                continue
            record_observations.append(link_observation)
            relations.append(
                CandidateSourceRelation(
                    relation_id=_stable_id("relation", record_key, link.url),
                    source_observation_id=observation_id,
                    source_url=normalized_page_url,
                    related_observation_id=link_observation_id,
                    related_source_url=link.url,
                    relation_type=CandidateSourceRelationType.APPEARS_SAME_REPORT,
                    captured_at=captured_at,
                    rationale=(
                        "Official HTML page visibly links to this candidate URL; byte identity "
                        "is unverified."
                    ),
                )
            )

        evidence: list[IdentityEvidence] = []
        if report_number is not None and number_observed is not None:
            evidence.append(
                IdentityEvidence(
                    evidence_id=_stable_id("evidence", record_key, "report_number"),
                    subject=IdentitySubject.REPORT_NUMBER,
                    evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                    candidate_value=str(report_number),
                    observed_value=number_observed,
                    source_observation_id=observation_id,
                    source_url=normalized_page_url,
                    captured_at=captured_at,
                    source_excerpt=text,
                )
            )
        if reference_period is not None and period_observed is not None:
            evidence.append(
                IdentityEvidence(
                    evidence_id=_stable_id("evidence", record_key, "reference_period"),
                    subject=IdentitySubject.REFERENCE_PERIOD,
                    evidence_type=IdentityEvidenceType.DOCUMENT_VISIBLE,
                    candidate_value=reference_period,
                    observed_value=period_observed,
                    source_observation_id=observation_id,
                    source_url=normalized_page_url,
                    captured_at=captured_at,
                    source_excerpt=text,
                )
            )
        uncertainty_notes: list[str] = []
        if report_number is None:
            uncertainty_notes.append("No report number was visible in the parsed HTML metadata.")
        if reference_period is None:
            uncertainty_notes.append("No reference month was visible in the parsed HTML metadata.")
        records.append(
            ProvisionalDiscoveryRecord(
                discovery_record_id=record_key,
                candidate_report_number=report_number,
                candidate_reference_period=reference_period,
                page_title_original=page_title,
                publication_date_original=publication_date_original,
                identity_evidence=tuple(evidence),
                url_observations=tuple(record_observations),
                candidate_source_relations=tuple(relations),
                uncertainty_notes=tuple(uncertainty_notes),
            )
        )

    if page_role is UrlRole.LANDING_PAGE:
        for link in links:
            if (
                link.role is not UrlRole.DIRECT_DOWNLOAD
                or link.url in used_link_urls
                or not link.in_article
            ):
                continue
            unresolved_record_key = _stable_id(
                "discovery-unresolved", normalized_page_url, link.url
            )
            unresolved_observation = UrlObservation(
                observation_id=_stable_id("url", unresolved_record_key, link.url),
                role=UrlRole.DIRECT_DOWNLOAD,
                url=link.url,
                captured_at=captured_at,
                uncertainty_note=(
                    "A direct-download URL was visible on this landing page, but its URL and "
                    "link text did not establish a report identity."
                ),
            )
            records.append(
                ProvisionalDiscoveryRecord(
                    discovery_record_id=unresolved_record_key,
                    page_title_original=page_title,
                    publication_date_original=publication_date_original,
                    url_observations=(page_observation, unresolved_observation),
                    uncertainty_notes=(
                        "Direct-download URL preserved as an unresolved source candidate; "
                        "report identity was not inferred.",
                    ),
                )
            )

    return ParsedDiscoveryPage(
        observation=page_observation,
        records=tuple(records),
        links=tuple(links),
        next_url=next_url,
        page_title_original=page_title,
        publication_date_original=publication_date_original,
    )
