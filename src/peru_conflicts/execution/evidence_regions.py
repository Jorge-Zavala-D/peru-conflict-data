"""Explicit native-region evidence method; never a failed-quote fallback.

Pins are coordinator-supplied provenance, not an OS trust or scientific approval claim.
The only admitted geometry is unrotated, zero-origin MediaBox == CropBox. Text is
the retained layout words fully inside the ORIGINAL box, in retained order.
"""

import math
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from peru_conflicts.benchmark.models import EvidenceAnchor, EvidenceGranularity
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Identifier, Sha256, SourceBBox, StrictModel

from .ai_pi import SourceUnit
from .references import ExecutableIdentity, sha256


class RegionLayoutPin(StrictModel):
    report_id: Identifier
    report_number: int
    source_sha256: Sha256
    physical_page: int = Field(ge=1)
    unit_id: Identifier
    reference_sha256: Sha256
    layout_sha256: Sha256
    bbox_xml_sha256: Sha256
    engine: ExecutableIdentity
    extraction_options: tuple[str, ...]
    coordinate_policy: Literal["top_left_pdf_points_unrotated_media_crop_zero_v1"]
    media_box: SourceBBox
    crop_box: SourceBBox
    rotation: Literal[0]
    region_policy: Literal["fully_contained_words_retained_order_v1"]

    @model_validator(mode="after")
    def supported_geometry(self) -> "RegionLayoutPin":
        if self.extraction_options != ("-bbox-layout", "-enc", "UTF-8", "-eol", "unix"):
            raise ValueError("unsupported region extraction options")
        if self.media_box != self.crop_box or self.media_box.x0 != 0 or self.media_box.y0 != 0:
            raise ValueError("unsupported crop/media transform")
        values = tuple(self.media_box.model_dump().values())
        if (
            not all(math.isfinite(v) for v in values)
            or min(self.media_box.x1, self.media_box.y1) <= 0
        ):
            raise ValueError("invalid page geometry")
        return self


class RegionEvidenceMethod(StrictModel):
    method_id: Literal["native_bbox_words_v1"]
    unit_id: Identifier
    anchor_sha256: Sha256
    raw_response_sha256: Sha256
    original_bbox: SourceBBox
    layout: RegionLayoutPin
    whitespace_policy: Literal["ascii_space_lf_v1"]


class NativeWord(StrictModel):
    text: str = Field(min_length=1)
    bbox: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    span: tuple[int, int]


class NativeLine(StrictModel):
    words: tuple[NativeWord, ...]


class NativeLayout(StrictModel):
    physical_page: int
    width: FiniteFloat = Field(gt=0)
    height: FiniteFloat = Field(gt=0)
    text: str
    words: tuple[NativeWord, ...]
    layout_lines: tuple[NativeLine, ...]
    representation_status: Literal["native_text_present", "native_text_empty_unverified"]
    table_structure: str
    reference_sha256: Sha256
    span_reference: str


@dataclass(frozen=True)
class RegionResource:
    layout_json: bytes
    bbox_xml: bytes


class RegionMatch(StrictModel):
    method: RegionEvidenceMethod
    match_kind: Literal["raw_exact", "qualified_whitespace"]
    original_quote_sha256: Sha256
    raw_region_text: str
    raw_region_sha256: Sha256
    comparison_text_sha256: Sha256
    comparison_start: int
    comparison_end: int
    # These are offsets into the declared region comparison, NEVER source_span.


def qualified_whitespace(text: str) -> str:
    """Only observed SPACE/LF runs; preserve all substantive characters.

    Refuse altered digit-to-digit separators; they may represent numeric groups.
    Other Unicode whitespace, CR/TAB, punctuation, accents and case are untouched.
    """
    if any(char.isspace() and char not in {" ", "\n"} for char in text):
        raise ValueError("unsupported region whitespace")
    if any(m.group() != " " for m in re.finditer(r"(?<=\d)[ \n]+(?=\d)", text)):
        raise ValueError("numeric separator whitespace is unresolved")
    return re.sub(r"[ \n]+", " ", text).strip(" ")


def _occurrences(text: str, quote: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while quote and (position := text.find(quote, start)) >= 0:
        end = position + len(quote)
        if not (
            (position > 0 and quote[0].isalnum() and text[position - 1].isalnum())
            or (end < len(text) and quote[-1].isalnum() and text[end].isalnum())
            or (
                position > 1
                and quote[0].isdigit()
                and text[position - 1] in ".,"
                and text[position - 2].isdigit()
            )
            or (
                end + 1 < len(text)
                and quote[-1].isdigit()
                and text[end] in ".,"
                and text[end + 1].isdigit()
            )
        ):
            positions.append(position)
        start = position + 1
    return positions


def match_region(
    anchor: EvidenceAnchor,
    unit: SourceUnit,
    reference: bytes,
    response_sha256: str,
    method: RegionEvidenceMethod,
    resource: RegionResource,
) -> RegionMatch:
    pin = method.layout
    if anchor.granularity is not EvidenceGranularity.BOUNDING_BOX or anchor.source_span is not None:
        raise ValueError("region method requires original bbox-only evidence")
    if not anchor.source_text or anchor.source_bbox is None:
        raise ValueError("region quote or original box missing")
    if (
        method.unit_id != unit.unit_id
        or pin.unit_id != unit.unit_id
        or method.raw_response_sha256 != response_sha256
        or method.anchor_sha256 != sha256(canonical_json_bytes(anchor.model_dump(mode="json")))
        or method.original_bbox != anchor.source_bbox
    ):
        raise ValueError("region declaration/original anchor identity mismatch")
    if (
        (anchor.report_id, anchor.report_number, anchor.source_sha256)
        != (unit.report_id, unit.report_number, unit.source_sha256)
        or (pin.report_id, pin.report_number, pin.source_sha256)
        != (unit.report_id, unit.report_number, unit.source_sha256)
        or anchor.page != pin.physical_page
        or anchor.page not in unit.pages
        or anchor.section not in unit.sections
    ):
        raise ValueError("region evidence outside source boundary")
    if (
        sha256(reference) != pin.reference_sha256
        or sha256(resource.layout_json) != pin.layout_sha256
        or sha256(resource.bbox_xml) != pin.bbox_xml_sha256
    ):
        raise ValueError("region reference/layout identity mismatch")
    layout = NativeLayout.model_validate_json(resource.layout_json)
    # Reuse the retained converter; deferred import avoids the runtime/batch/model cycle.
    from .ai_pi_batch_runtime import parse_layout_xml

    converted = parse_layout_xml(resource.bbox_xml.decode("utf-8"), physical_page=anchor.page)
    serialized = layout.model_dump(mode="json")
    for key in ("physical_page", "width", "height", "text", "words", "layout_lines"):
        if converted[key] != serialized[key]:
            raise ValueError("native XML/layout conversion identity mismatch")
    if (
        layout.physical_page != anchor.page
        or layout.reference_sha256 != pin.reference_sha256
        or layout.width != pin.media_box.x1
        or layout.height != pin.media_box.y1
        or layout.text != " ".join(word.text for word in layout.words)
    ):
        raise ValueError("region page/order identity mismatch")
    box = anchor.source_bbox
    if not all(math.isfinite(v) for v in box.model_dump().values()) or not (
        0 <= box.x0 < box.x1 <= layout.width and 0 <= box.y0 < box.y1 <= layout.height
    ):
        raise ValueError("original region box outside page")
    selected: list[str] = []
    offset = 0
    for index, word in enumerate(layout.words):
        x0, y0, x1, y1 = word.bbox
        if not (0 <= x0 <= x1 <= layout.width and 0 <= y0 <= y1 <= layout.height):
            raise ValueError("layout word geometry outside page")
        if index:
            offset += 1
        if word.span != (offset, offset + len(word.text)):
            raise ValueError("retained word-order/span mismatch")
        offset += len(word.text)
        if x0 >= box.x0 and y0 >= box.y0 and x1 <= box.x1 and y1 <= box.y1:
            selected.append(word.text)
    raw_region = " ".join(selected)
    if not raw_region:
        raise ValueError("region has no inspected native text; incomplete")
    quote = anchor.source_text
    positions = _occurrences(raw_region, quote)
    mode: Literal["raw_exact", "qualified_whitespace"] = "raw_exact"
    comparison = raw_region
    if not positions:
        comparison = qualified_whitespace(raw_region)
        quote = qualified_whitespace(quote)
        positions = _occurrences(comparison, quote)
        mode = "qualified_whitespace"
    elif len(positions) == 1:
        try:
            equivalent_positions = _occurrences(
                qualified_whitespace(raw_region), qualified_whitespace(quote)
            )
        except ValueError:
            # Unsupported transforms cannot add a plausible match under this method.
            equivalent_positions = positions
        if len(equivalent_positions) != 1:
            raise ValueError("region quote has multiple qualified occurrences; incomplete")
    if len(positions) != 1:
        raise ValueError("region quote unsupported or ambiguous; incomplete")
    return RegionMatch(
        method=method,
        match_kind=mode,
        original_quote_sha256=sha256(anchor.source_text.encode("utf-8")),
        raw_region_text=raw_region,
        raw_region_sha256=sha256(raw_region.encode("utf-8")),
        comparison_text_sha256=sha256(comparison.encode("utf-8")),
        comparison_start=positions[0],
        comparison_end=positions[0] + len(quote),
    )
