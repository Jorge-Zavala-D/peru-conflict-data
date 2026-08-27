"""Deterministic, entry-scoped HTML parsing for official discovery surfaces."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
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
_REFERENCE_MONTHS: Final[dict[str, int]] = {**_MONTHS, "jun": 6}
_REFERENCE_PERIOD_RE: Final[re.Pattern[str]] = re.compile(
    rf"\b({_MONTH_PATTERN})(?:\s+|\s*[-\u2013\u2014]\s*)(\d{{4}})\b|"
    rf"\b(\d{{4}})(?:\s+|\s*[-\u2013\u2014]\s*)({_MONTH_PATTERN})\b|"
    rf"\b(jun)\s*[-\u2013\u2014]\s*(\d{{4}})\b",
    re.IGNORECASE,
)
_DAY_TOKEN_BEFORE_PERIOD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])"
    r"(?:\s+de\s+|\s+|\s*[,./:\-\u2013\u2014]\s*)$",
    re.IGNORECASE,
)
_DAY_TOKEN_AFTER_PERIOD_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:\s+de\s+|\s+|\s*[,./:\-\u2013\u2014]\s*)"
    r"(?:0?[1-9]|[12]\d|3[01])\b",
    re.IGNORECASE,
)
_REPORT_NUMBER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bn\s*[.º°oª]*\s*[-:]?\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\breporte\s+(?:n\s*[.º°oª]*\s*)?(\d{1,4})\b", re.IGNORECASE),
)
_REPORT_SOURCE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\breporte(?:\s+mensual)?\s+de\s+conflictos?\s+sociales\b",
        re.IGNORECASE,
    ),
    re.compile(r"\breporte\s+conflictos?\s+sociales\b", re.IGNORECASE),
    re.compile(
        r"\breporte\s+mensual(?:\s+n\s*[.º°oª]*\s*\d{1,4})?\s+"
        r"conflictos?\s+sociales\b",
        re.IGNORECASE,
    ),
)
_SLASH_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_MONTH_DATE_RE: Final[re.Pattern[str]] = re.compile(
    rf"\b({_MONTH_PATTERN})\s+\d{{1,2}},\s*\d{{4}}\b", re.IGNORECASE
)
_WEEKDAY_DATE_RE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo),\s*"
    rf"\d{{1,2}}\s+(?:{_MONTH_PATTERN})\s+\d{{4}}\b",
    re.IGNORECASE,
)
_DIRECT_DOWNLOAD_SUFFIXES: Final[tuple[str, ...]] = (
    ".pdf",
    ".zip",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
)
_IGNORED_CONTENT_TAGS: Final[frozenset[str]] = frozenset({"script", "style", "noscript", "footer"})
_VOID_TAGS: Final[frozenset[str]] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


@dataclass(frozen=True, slots=True)
class DiscoveredLink:
    """One visible link with a source-safe role classification."""

    url: str
    text: str
    role: UrlRole
    in_article: bool
    scope_id: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDiscoveryPage:
    """Parsed page metadata and provisional candidate records."""

    observation: UrlObservation
    records: tuple[ProvisionalDiscoveryRecord, ...]
    links: tuple[DiscoveredLink, ...]
    next_url: str | None
    source_page_title_original: str | None


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=lambda: {})
    parent: _Node | None = None
    contents: list[str | _Node] = field(default_factory=lambda: [])
    sequence: int = 0

    def text(self) -> str:
        pieces: list[str] = []
        for item in self.contents:
            if isinstance(item, str):
                pieces.append(item)
            elif item.tag not in _IGNORED_CONTENT_TAGS:
                pieces.append(item.text())
        return _clean_text(" ".join(pieces))

    def class_tokens(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").lower().split())

    def has_ignored_ancestor(self) -> bool:
        current: _Node | None = self
        while current is not None:
            if current.tag in _IGNORED_CONTENT_TAGS:
                return True
            current = current.parent
        return False

    def has_ancestor_class(self, token: str) -> bool:
        current: _Node | None = self
        while current is not None:
            if token in current.class_tokens():
                return True
            current = current.parent
        return False

    def has_ancestor_tag(self, tags: frozenset[str]) -> bool:
        current = self.parent
        while current is not None:
            if current.tag in tags:
                return True
            current = current.parent
        return False

    def is_descendant_of(self, ancestor: _Node) -> bool:
        current = self.parent
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent
        return False


class _TreeParser(HTMLParser):
    """Small source-order DOM sufficient for scoped, deterministic extraction."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(tag="document")
        self.nodes: list[_Node] = []
        self._stack = [self.root]
        self._sequence = 0
        self.publication_metadata: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        node = _Node(
            tag=lower_tag,
            attrs=attributes,
            parent=self._stack[-1],
            sequence=self._sequence,
        )
        self._sequence += 1
        self._stack[-1].contents.append(node)
        self.nodes.append(node)
        if lower_tag == "meta":
            key = attributes.get("property", "").lower() or attributes.get("name", "").lower()
            if key in {"article:published_time", "date", "publication_date"}:
                self.publication_metadata = attributes.get("content") or None
        if lower_tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == lower_tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].contents.append(data)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _iter_descendants(node: _Node, *, tags: frozenset[str] | None = None) -> list[_Node]:
    descendants: list[_Node] = []
    for item in node.contents:
        if not isinstance(item, _Node):
            continue
        if not item.has_ignored_ancestor() and (tags is None or item.tag in tags):
            descendants.append(item)
        descendants.extend(_iter_descendants(item, tags=tags))
    return descendants


def _is_nested_entry_boundary(scope: _Node, node: _Node) -> bool:
    """Identify a peer entry nested by malformed or source-order HTML."""

    if "card" in scope.class_tokens() and "card" in node.class_tokens():
        return True
    return scope.tag in {"article", "li"} and node.tag == scope.tag


def _iter_scope_descendants(
    scope: _Node,
    *,
    tags: frozenset[str] | None = None,
) -> list[_Node]:
    """Walk one entry without crossing into a nested peer entry."""

    descendants: list[_Node] = []

    def visit(current: _Node) -> None:
        for item in current.contents:
            if not isinstance(item, _Node):
                continue
            if item.has_ignored_ancestor() or _is_nested_entry_boundary(scope, item):
                continue
            if tags is None or item.tag in tags:
                descendants.append(item)
            visit(item)

    visit(scope)
    return descendants


def _scope_visible_text(scope: _Node, excluded_tags: frozenset[str]) -> str:
    """Collect local entry text while pruning chrome and nested peer entries."""

    pieces: list[str] = []

    def visit(current: _Node) -> None:
        for item in current.contents:
            if isinstance(item, str):
                pieces.append(item)
            elif (
                item.tag not in excluded_tags
                and item.tag not in _IGNORED_CONTENT_TAGS
                and not _is_nested_entry_boundary(scope, item)
            ):
                visit(item)

    visit(scope)
    return _clean_text(" ".join(pieces))


def _is_report_source_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _REPORT_SOURCE_PATTERNS)


def _link_role(url: str) -> UrlRole | None:
    parsed = urlsplit(url)
    path = parsed.path.lower()
    if path.endswith(_DIRECT_DOWNLOAD_SUFFIXES):
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


def _preceded_by_calendar_day(text: str, period_start: int) -> bool:
    prefix = text[:period_start]
    day_match = _DAY_TOKEN_BEFORE_PERIOD_RE.search(prefix)
    if day_match is None:
        return False

    day_span = day_match.span(1)
    for report_pattern in _REPORT_NUMBER_PATTERNS:
        for report_match in report_pattern.finditer(prefix):
            if report_match.span(1) == day_span:
                return False
    return True


def _parse_reference_period(text: str) -> tuple[str | None, str | None]:
    for match in _REFERENCE_PERIOD_RE.finditer(text):
        if _preceded_by_calendar_day(text, match.start()):
            continue
        if match.group(3) and _DAY_TOKEN_AFTER_PERIOD_RE.match(text[match.end() :]):
            continue
        if match.group(1):
            month_name, year_text = match.group(1).lower(), match.group(2)
        elif match.group(3):
            year_text, month_name = match.group(3), match.group(4).lower()
        else:
            month_name, year_text = match.group(5).lower(), match.group(6)
        return f"{int(year_text):04d}-{_REFERENCE_MONTHS[month_name]:02d}", match.group(0)
    return None, None


def _extract_date(text: str) -> str | None:
    for pattern in (_SLASH_DATE_RE, _WEEKDAY_DATE_RE, _MONTH_DATE_RE):
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _landing_entry_scope(heading: _Node) -> _Node:
    """Choose the nearest content boundary that contains the primary landing heading."""

    recognized_classes = {
        "content",
        "document-content",
        "entry-content",
        "post-content",
        "single-content",
    }
    current = heading.parent
    body_fallback: _Node = heading
    while current is not None and current.tag != "document":
        if current.tag in {"article", "main"} or current.class_tokens() & recognized_classes:
            return current
        if current.tag == "body":
            body_fallback = current
        current = current.parent
    return body_fallback


def _candidate_scopes(parser: _TreeParser, page_role: UrlRole) -> list[_Node]:
    nodes = [node for node in parser.nodes if not node.has_ignored_ancestor()]
    excluded_entry_ancestors = frozenset({"nav", "header", "aside"})
    fallback_nodes = [node for node in nodes if not node.has_ancestor_tag(excluded_entry_ancestors)]
    if page_role is UrlRole.THEMATIC_PAGE:
        canonical = next((node for node in nodes if node.attrs.get("id") == "pills-otraspub"), None)
        thematic_nodes = (
            [node for node in nodes if node.is_descendant_of(canonical)]
            if canonical is not None
            else fallback_nodes
        )
        fallback_nodes = thematic_nodes
        preferred = [
            node
            for node in thematic_nodes
            if node.tag == "div"
            and "card" in node.class_tokens()
            and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
        ]
    elif page_role is UrlRole.SEARCH_RESULT_PAGE:
        canonical = next((node for node in nodes if "search-content" in node.class_tokens()), None)
        search_nodes = (
            [node for node in nodes if node.is_descendant_of(canonical)]
            if canonical is not None
            else fallback_nodes
        )
        fallback_nodes = search_nodes
        preferred = [
            node
            for node in search_nodes
            if node.tag == "li"
            and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
        ]
    elif page_role is UrlRole.LANDING_PAGE:
        landing_headings = [
            node
            for node in fallback_nodes
            if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
            and _is_report_source_text(node.text())
        ]
        if landing_headings:
            return [_landing_entry_scope(landing_headings[0])]
        preferred = [
            node
            for node in fallback_nodes
            if node.tag == "article"
            and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
        ]
    elif page_role is UrlRole.CATALOGUE_PAGE:
        preferred = [
            node
            for node in fallback_nodes
            if node.tag == "article"
            and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
        ]
        if not preferred:
            preferred = [
                node
                for node in fallback_nodes
                if (node.tag == "li" or "card" in node.class_tokens())
                and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
            ]
    else:
        preferred = [
            node
            for node in fallback_nodes
            if node.tag == "article"
            and _is_report_source_text(_scope_visible_text(node, excluded_entry_ancestors))
        ]

    if preferred:
        return preferred

    anchors = [
        node
        for node in fallback_nodes
        if node.tag == "a" and node.attrs.get("href") and _is_report_source_text(node.text())
    ]
    if anchors:
        return anchors

    headings = [
        node
        for node in fallback_nodes
        if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and _is_report_source_text(node.text())
    ]
    if headings:
        return headings
    return []


def _scope_metadata(scope: _Node) -> tuple[str, str | None, str | None, str | None]:
    excluded = frozenset({"nav", "header", "aside"})
    descendants = [
        node for node in _iter_scope_descendants(scope) if not node.has_ancestor_tag(excluded)
    ]
    headings = [node for node in descendants if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}]
    anchors = [
        node
        for node in descendants
        if node.tag == "a" and node.attrs.get("href") and _is_report_source_text(node.text())
    ]
    paragraphs = [
        node for node in descendants if node.tag == "p" and _is_report_source_text(node.text())
    ]

    scope_text = scope.text() if scope.tag in {"h1", "h2", "h3", "h4", "h5", "h6", "a"} else ""
    title = headings[0].text() if headings else anchors[0].text() if anchors else scope_text
    description = paragraphs[0].text() if paragraphs else None
    identity_text = _clean_text(" ".join(part for part in (title, description) if part))
    publication_text = _scope_visible_text(scope, excluded)
    publication_date = _extract_date(publication_text)
    return identity_text, title or None, publication_date, description


def _scope_links(
    scope: _Node,
    *,
    base_url: str,
    scope_id: str,
) -> list[DiscoveredLink]:
    anchor_nodes = (
        [scope] if scope.tag == "a" else _iter_scope_descendants(scope, tags=frozenset({"a"}))
    )
    links: list[DiscoveredLink] = []
    seen: set[str] = set()
    for anchor in anchor_nodes:
        if anchor.has_ancestor_tag(frozenset({"nav", "header", "aside"})):
            continue
        href = anchor.attrs.get("href")
        if not href:
            continue
        try:
            normalized = normalize_url(href, base_url=base_url)
        except ValueError:
            continue
        role = _link_role(normalized)
        if role is None or normalized in seen:
            continue
        seen.add(normalized)
        current = anchor.parent
        in_article = False
        while current is not None:
            if current.tag == "article":
                in_article = True
                break
            current = current.parent
        links.append(
            DiscoveredLink(
                url=normalized,
                text=anchor.text(),
                role=role,
                in_article=in_article,
                scope_id=scope_id,
            )
        )
    return links


def _next_page_url(parser: _TreeParser) -> str | None:
    containers = [
        node
        for node in parser.nodes
        if not node.has_ignored_ancestor()
        and not node.has_ancestor_class("post-navigation")
        and (
            bool(node.class_tokens() & {"pagination", "nav-links", "wp-pagenavi"})
            or (
                node.tag == "nav"
                and "pagin"
                in " ".join(
                    (
                        node.attrs.get("aria-label", ""),
                        node.attrs.get("title", ""),
                    )
                ).lower()
            )
        )
    ]
    for container in containers:
        pagination_nodes = [
            node
            for node in parser.nodes
            if node.is_descendant_of(container) and not node.has_ignored_ancestor()
        ]
        pagination_anchors = [
            node for node in pagination_nodes if node.tag == "a" and node.attrs.get("href")
        ]

        # ``rel=next`` also appears in article-navigation controls. It is
        # pagination evidence only inside one explicit pagination container.
        for anchor in pagination_anchors:
            rel_tokens = {token.lower() for token in anchor.attrs.get("rel", "").split()}
            if "next" in rel_tokens:
                return anchor.attrs["href"]

        # Prefer an explicit accessible next control over numeric page links,
        # which often include a last-page shortcut.
        for anchor in pagination_anchors:
            text = anchor.text().strip().lower()
            aria_label = anchor.attrs.get("aria-label", "").strip().lower()
            title = anchor.attrs.get("title", "").strip().lower()
            classes = anchor.class_tokens()
            explicitly_next = (
                "next" in classes
                or any(token in aria_label for token in ("siguiente", "next"))
                or any(token in title for token in ("siguiente", "next"))
                or text in {"next", "siguiente", f"-{chr(8250)}", chr(8250), chr(187)}
            )
            if explicitly_next:
                return anchor.attrs["href"]

        current_page = 1
        for node in pagination_nodes:
            if (
                "current" not in node.class_tokens()
                and node.attrs.get("aria-current", "").lower() != "page"
            ):
                continue
            match = re.search(r"\b(\d+)\b", node.text())
            if match:
                current_page = int(match.group(1))
                break

        expected_next = current_page + 1
        for anchor in pagination_anchors:
            text = anchor.text().strip()
            if text.isdigit() and int(text) == expected_next:
                return anchor.attrs["href"]
    return None


def _direct_link_visibly_matches(link: DiscoveredLink, report_number: int | None) -> bool:
    if report_number is None:
        return False
    return bool(re.search(rf"(?<!\d){report_number}(?!\d)", f"{link.url} {link.text}"))


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

    parser = _TreeParser()
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

    page_headings = [
        node
        for node in parser.nodes
        if node.tag == "h1"
        and not node.has_ignored_ancestor()
        and not node.has_ancestor_tag(frozenset({"nav", "header", "aside"}))
        and node.text()
    ]
    source_page_title = page_headings[0].text() if page_headings else None
    page_links: list[DiscoveredLink] = []
    seen_page_links: set[str] = set()
    records: list[ProvisionalDiscoveryRecord] = []
    unresolved_downloads: list[tuple[str, DiscoveredLink]] = []

    for scope in _candidate_scopes(parser, page_role):
        identity_text, entry_title, entry_date, entry_description = _scope_metadata(scope)
        if not identity_text:
            continue
        if page_role is UrlRole.LANDING_PAGE and entry_date is None:
            entry_date = parser.publication_metadata
        report_number, number_observed = _parse_report_number(identity_text)
        reference_period, period_observed = _parse_reference_period(identity_text)
        record_key = _stable_id(
            "discovery",
            normalized_page_url,
            str(scope.sequence),
            str(report_number),
            str(reference_period),
        )
        scoped_links = _scope_links(scope, base_url=normalized_page_url, scope_id=record_key)
        if page_role is UrlRole.LANDING_PAGE:
            scoped_links = [link for link in scoped_links if link.role is not UrlRole.LANDING_PAGE]
        for scoped_link in scoped_links:
            if scoped_link.url not in seen_page_links:
                seen_page_links.add(scoped_link.url)
                page_links.append(scoped_link)
        linked: list[DiscoveredLink] = []
        for link in scoped_links:
            if (
                page_role is UrlRole.LANDING_PAGE
                and link.role is UrlRole.DIRECT_DOWNLOAD
                and not _direct_link_visibly_matches(link, report_number)
            ):
                unresolved_downloads.append((record_key, link))
                continue
            linked.append(link)

        record_observations = [page_observation]
        relations: list[CandidateSourceRelation] = []
        for link_index, link in enumerate(linked):
            if link.url == normalized_page_url:
                continue
            link_observation_id = _stable_id("url", record_key, str(link_index), link.url)
            record_observations.append(
                UrlObservation(
                    observation_id=link_observation_id,
                    role=link.role,
                    url=link.url,
                    captured_at=captured_at,
                )
            )
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
                        "Official HTML entry visibly links this candidate URL; byte identity "
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
                    source_excerpt=identity_text,
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
                    source_excerpt=identity_text,
                )
            )
        uncertainty_notes: list[str] = []
        if report_number is None:
            uncertainty_notes.append("No report number was visible in this source entry.")
        if reference_period is None:
            uncertainty_notes.append("No reference month was visible in this source entry.")
        records.append(
            ProvisionalDiscoveryRecord(
                discovery_record_id=record_key,
                candidate_report_number=report_number,
                candidate_reference_period=reference_period,
                source_page_title_original=source_page_title,
                entry_title_original=entry_title,
                entry_publication_date_original=entry_date,
                entry_description_original=entry_description,
                identity_evidence=tuple(evidence),
                url_observations=tuple(record_observations),
                candidate_source_relations=tuple(relations),
                uncertainty_notes=tuple(uncertainty_notes),
            )
        )

    if page_role is UrlRole.LANDING_PAGE:
        seen_unresolved: set[str] = set()
        for source_record_key, link in unresolved_downloads:
            if link.url in seen_unresolved:
                continue
            seen_unresolved.add(link.url)
            unresolved_key = _stable_id("discovery-unresolved", normalized_page_url, link.url)
            unresolved_observation = UrlObservation(
                observation_id=_stable_id("url", unresolved_key, link.url),
                role=UrlRole.DIRECT_DOWNLOAD,
                url=link.url,
                captured_at=captured_at,
                uncertainty_note=(
                    "A direct-download URL was visible in the source entry, but its URL and "
                    "link text did not establish report identity."
                ),
            )
            records.append(
                ProvisionalDiscoveryRecord(
                    discovery_record_id=unresolved_key,
                    source_page_title_original=source_page_title,
                    url_observations=(page_observation, unresolved_observation),
                    candidate_source_relations=(
                        CandidateSourceRelation(
                            relation_id=_stable_id("relation", source_record_key, link.url),
                            source_observation_id=observation_id,
                            source_url=normalized_page_url,
                            related_observation_id=unresolved_observation.observation_id,
                            related_source_url=link.url,
                            relation_type=CandidateSourceRelationType.APPEARS_SAME_REPORT,
                            captured_at=captured_at,
                            rationale=(
                                "Official landing entry visibly exposes this download URL; "
                                "report identity and byte identity remain unverified."
                            ),
                        ),
                    ),
                    uncertainty_notes=(
                        "Direct-download URL preserved as an unresolved source candidate; "
                        "report identity was not inferred.",
                    ),
                )
            )

    return ParsedDiscoveryPage(
        observation=page_observation,
        records=tuple(records),
        links=tuple(page_links),
        next_url=_next_page_url(parser),
        source_page_title_original=source_page_title,
    )
