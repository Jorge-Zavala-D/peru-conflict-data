# Representation-qualified native region evidence, version 1

This is a mechanical development-batch evidence method, not scientific acceptance,
PI adjudication, discovery completeness, or a change to scientific schema 0.3.1 or
benchmark/metric contract 0.1.1. Original replies, quotes, candidates, normalization
failures, comparisons and source-first PI packets remain immutable.

## Explicit method selection and provenance

`native_bbox_words_v1` is selected only by a coordinator-supplied
`RegionEvidenceMethod` binding an unchanged typed anchor fingerprint, original
response SHA-256, source unit and original submitted bounding box. It is not
selected because full-page matching failed. Machine replies cannot self-select it
in the finalization path. Unused or duplicate declarations are incomplete/errors.

The declaration binds the PDF SHA-256, report, physical page and unit, exact native
reference hash, retained layout JSON and native bbox XML hashes, extraction binary
identity/version, options and page geometry. The native options are `-bbox-layout
-enc UTF-8 -eol unix`, with the declared physical page supplied using `-f`/`-l`.
The retained XML is reconverted using the existing `parse_layout_xml` helper; its
page, dimensions, words, order, spans and lines must equal the pinned JSON.

The supported coordinate policy is
`top_left_pdf_points_unrotated_media_crop_zero_v1`: origin at the upper-left,
x increasing right, y increasing down, units PDF points (1/72 inch). It admits
only rotation zero, zero-origin MediaBox equal to CropBox, with exact matching
retained layout dimensions. No crop offset, rotation transform, scaling or box
tolerance is applied. Other coordinate regimes remain unresolved rather than
being guessed. Geometry/tool pins are verified coordinator provenance, not an OS
trust authority. Hashes identify bytes; they do not establish semantic truth.

## Region selection and text identities

`fully_contained_words_retained_order_v1` selects words fully contained in the
original box, without expanding, moving or choosing a box against the quotation.
It joins the retained word strings with one SPACE in their retained XML order.
This is a declared region representation, not a claim that its serialized bytes
are the visual PDF or the complete page reference. The raw joined region text,
its digest and the unchanged quote digest are retained in `RegionMatch`.

Exact region matching is preferred. A quote must have a coherent token boundary
and a unique occurrence; partial matches inside words/numeric tokens do not count.
Multiple exact or admissible whitespace-equivalent occurrences remain incomplete.
No arbitrary neighboring box/page is searched or adopted. Missing native text is
incomplete, never an inspected zero/empty source inventory.

`ascii_space_lf_v1` is the only qualified whitespace policy: runs consisting of
ASCII SPACE and LF become one SPACE, with outer SPACE/LF removed. No other
whitespace class, punctuation, accent, case, hyphenation, word ordering or semantic
similarity is normalized. Changed digit-to-digit separators are refused because
they may encode numeric grouping. The transformed comparison and its digest are
derivatives, not replacement quote/reference bytes or scientific values. Results
distinguish `raw_exact` from `qualified_whitespace`; comparison offsets are never
represented as a full-page `source_span`.

## Dispatch, persistence and limitations

The existing full-page/span validator remains unchanged for undeclared inputs.
The new route supports explicitly declared bbox anchors in partial fields,
objects, relationships and the already restricted same-report association.
The latter still supports only `report.report_number` and
`report.reference_period`, with the same source/target unit checks. No new
external-anchor or case-boundary exception is introduced. Unsupported declarations
(including ordinary full-schema annotation declarations) remain incomplete.

`finalize_initial_pass` uses the same typed normalization/validation path for a
separately versioned follow-up. New methods/resources require a fresh
`normalization_followups/b-region-v1-<run-id>/` destination. Writes are no-replace;
existing follow-up directories are refused. Original payloads and new tracebacks
are retained for rejected responses. Coverage describes admitted normalization,
not reader completeness: rejected entries are noncomparable, not source absence,
proof another pass is correct, or a zero comparison denominator.

No A answer or PI judgment chooses declarations or resolves ambiguity. No model
vote, accuracy score, comparison rebuild or canonical promotion follows. Any
normalized follow-up is a derivative under its own code/method identities and
cannot retroactively become the original machine stage.
