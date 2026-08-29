"""Bounded, source-preserving landing-page association evidence."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from peru_conflicts.acquisition.transport import (
    CanonicalAcquisitionUrl,
    UnapprovedCanonicalUrl,
    canonicalize_acquisition_url,
)

LANDING_ASSOCIATION_PARSER_VERSION = "landing-association-v4"
_BOUNDED_TAGS = frozenset(("article", "li", "section", "div"))
_SEMANTIC_CARD_TAGS = frozenset(("article", "li", "section"))
_DIV_CARD_TOKENS = frozenset(("card", "documento", "entry", "post", "result-item"))


class LandingAssociationError(RuntimeError):
    """Landing evidence cannot safely support the reviewed direct URL."""

    def __init__(self, message: str, *, rejected_href_sha256s: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.rejected_href_sha256s = rejected_href_sha256s


class LandingAssociationMissing(LandingAssociationError):
    """The reviewed direct URL is absent from the bounded landing evidence."""


class LandingAssociationAmbiguous(LandingAssociationError):
    """A qualified entry exposes a distinct competing PDF candidate."""


@dataclass(slots=True)
class _Container:
    tag: str
    is_card: bool
    text_parts: list[str] = field(default_factory=lambda: list[str]())

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


@dataclass(slots=True)
class _AnchorDraft:
    start: int
    href: str | None
    containers: tuple[_Container, ...]
    text_parts: list[str] = field(default_factory=lambda: list[str]())


@dataclass(frozen=True, slots=True)
class _Anchor:
    start: int
    end: int
    href: str | None
    text: str
    containers: tuple[_Container, ...]
    source_span: str

    @property
    def container_text(self) -> str:
        for container in reversed(self.containers):
            if container.is_card:
                return container.text
        return ""


class _BoundedAnchorParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._line_starts = [0]
        self._line_starts.extend(match.end() for match in re.finditer(r"\n", source))
        self._containers: list[_Container] = []
        self._active_anchor: _AnchorDraft | None = None
        self.anchors: list[_Anchor] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in _BOUNDED_TAGS:
            card_attribute_text = " ".join(
                value or "" for name, value in attrs if name.casefold() in {"class", "id"}
            )
            tokens = frozenset(re.findall(r"[a-z0-9_-]+", card_attribute_text.casefold()))
            self._containers.append(
                _Container(
                    tag=lowered,
                    is_card=(
                        lowered in _SEMANTIC_CARD_TAGS
                        or (lowered == "div" and bool(tokens & _DIV_CARD_TOKENS))
                    ),
                )
            )
        if lowered == "a" and self._active_anchor is None:
            href = next((value for name, value in attrs if name.casefold() == "href"), None)
            self._active_anchor = _AnchorDraft(
                start=self._offset(),
                href=href,
                containers=tuple(self._containers),
            )

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if not normalized:
            return
        for container in self._containers:
            container.text_parts.append(normalized)
        if self._active_anchor is not None:
            self._active_anchor.text_parts.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "a" and self._active_anchor is not None:
            closing_start = self._offset()
            closing_end = self._source.find(">", closing_start)
            if closing_end == -1:
                closing_end = closing_start
            else:
                closing_end += 1
            draft = self._active_anchor
            self.anchors.append(
                _Anchor(
                    start=draft.start,
                    end=closing_end,
                    href=draft.href,
                    text=" ".join(draft.text_parts),
                    containers=draft.containers,
                    source_span=self._source[draft.start : closing_end],
                )
            )
            self._active_anchor = None
        if lowered in _BOUNDED_TAGS:
            for index in range(len(self._containers) - 1, -1, -1):
                if self._containers[index].tag == lowered:
                    del self._containers[index:]
                    break


@dataclass(frozen=True, slots=True)
class LandingAssociationEvidence:
    """Exact source evidence supporting one reviewed landing-to-PDF relationship."""

    landing_body_sha256: str
    landing_body_bytes: int
    excerpt_sha256: str
    source_span_text: str
    character_start: int
    character_end: int
    byte_start: int
    byte_end: int
    parser_version: str
    reviewed_href_original: str
    reviewed_url_normalized: str
    reviewed_wire_target: str
    candidate_url_sha256s: tuple[str, ...]
    rejected_href_sha256s: tuple[str, ...]
    identity_association_status: str


def _fold_source_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(ascii_text.casefold().split())


def _qualified_competing_candidate(
    *,
    canonical: CanonicalAcquisitionUrl,
    anchor: _Anchor,
    report_number: int,
) -> bool:
    if not canonical.wire_target.casefold().endswith((".pdf", ".pdf.pdf")):
        return False
    context = _fold_source_text(f"{anchor.container_text} {anchor.text}")
    report_pattern = re.compile(rf"(?<!\d){report_number}(?!\d)")
    return "conflictos sociales" in context and report_pattern.search(context) is not None


def _safe_anchor_url(
    anchor: _Anchor,
    *,
    landing_url: str,
    approved_hosts: frozenset[str],
) -> CanonicalAcquisitionUrl | None:
    if anchor.href is None:
        return None
    absolute = urljoin(landing_url, anchor.href)
    return canonicalize_acquisition_url(absolute, approved_hosts)


def verify_landing_association(
    body: bytes,
    *,
    landing_url: str,
    reviewed_direct_url: str,
    approved_hosts: frozenset[str],
    report_number: int,
    association_status: str,
) -> LandingAssociationEvidence:
    """Require exact reviewed support and reject deterministic competing candidates."""

    if len(body) < 1 or len(body) > 2_000_000:
        raise LandingAssociationMissing("landing body size is outside the reviewed bound")
    try:
        source = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise LandingAssociationMissing("landing body is not valid UTF-8") from error
    canonicalize_acquisition_url(landing_url, approved_hosts)
    reviewed = canonicalize_acquisition_url(reviewed_direct_url, approved_hosts)
    parser = _BoundedAnchorParser(source)
    parser.feed(source)
    parser.close()

    supports: list[tuple[_Anchor, CanonicalAcquisitionUrl]] = []
    candidates: dict[str, str] = {}
    rejected_hashes: set[str] = set()
    competing: set[str] = set()
    for anchor in parser.anchors:
        if anchor.href is None:
            continue
        try:
            canonical = _safe_anchor_url(
                anchor,
                landing_url=landing_url,
                approved_hosts=approved_hosts,
            )
        except UnapprovedCanonicalUrl:
            rejected_hashes.add(hashlib.sha256(anchor.href.encode("utf-8")).hexdigest())
            continue
        if canonical is None:
            continue
        canonical_hash = hashlib.sha256(canonical.normalized_url.encode("utf-8")).hexdigest()
        if canonical.normalized_url == reviewed.normalized_url:
            supports.append((anchor, canonical))
            candidates[canonical.normalized_url] = canonical_hash
        elif _qualified_competing_candidate(
            canonical=canonical,
            anchor=anchor,
            report_number=report_number,
        ):
            candidates[canonical.normalized_url] = canonical_hash
            competing.add(canonical_hash)

    rejected = tuple(sorted(rejected_hashes))
    if not supports:
        raise LandingAssociationMissing(
            "reviewed direct link is absent from landing evidence",
            rejected_href_sha256s=rejected,
        )
    if competing:
        raise LandingAssociationAmbiguous(
            "landing evidence contains a distinct qualified PDF candidate",
            rejected_href_sha256s=rejected,
        )
    anchor, canonical = min(supports, key=lambda item: item[0].start)
    byte_start = len(source[: anchor.start].encode("utf-8"))
    byte_end = len(source[: anchor.end].encode("utf-8"))
    return LandingAssociationEvidence(
        landing_body_sha256=hashlib.sha256(body).hexdigest(),
        landing_body_bytes=len(body),
        excerpt_sha256=hashlib.sha256(anchor.source_span.encode("utf-8")).hexdigest(),
        source_span_text=anchor.source_span,
        character_start=anchor.start,
        character_end=anchor.end,
        byte_start=byte_start,
        byte_end=byte_end,
        parser_version=LANDING_ASSOCIATION_PARSER_VERSION,
        reviewed_href_original=anchor.href or "",
        reviewed_url_normalized=canonical.normalized_url,
        reviewed_wire_target=canonical.wire_target,
        candidate_url_sha256s=tuple(sorted(candidates.values())),
        rejected_href_sha256s=rejected,
        identity_association_status=association_status,
    )
