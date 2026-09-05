# M2-02 source-neutral discovery execution policy

Status: **OWNER REVIEW DRAFT** — no annotation launch or final metric amendment is approved.

## Compatibility finding, before implementation

M2-01 remains complete. This proposal does not reopen its ontology, annotation states, independent
A/B requirements, critical fields, partition, or schemas. M2-02 annotation has not started.
M2-02A implementation is paused pending Jorge's discovery-policy decision and separate readiness.
The M3 gate remains unapproved under Object Threshold Policy A.

The approved handbook defines a `case_observation` unit as **one published case block**. The frozen
`AnnotatorSubmission` contains one `unit_id`; every inventory item and field uses that same ID.
`validate_independent_submissions()` requires two distinct, current, locked submissions for that
same unit and partition. It cannot reconcile independently discovered, differently bounded units.
The normative evaluator obtains case detection from the case-observation object metric, whose
implemented signature is `unit_id`. The metric specification permits an *approved* deterministic
report/page/block key after segmentation, but has not defined that key. No source-neutral discovery
window existed in the frozen contract. Assigning one pre-bounded unit per case would reveal part of
the discovery answer; using one report-wide case ID would instead measure counts, not identities.

These are execution and correspondence gaps, not evidence that the frozen model cannot represent
human-discovered blocks. The existing constructors and A/B validator pass the synthetic proof when
applied at the proper stage. `AnnotationDisagreement` requires annotation IDs from both sides and
cannot honestly represent an entirely missing submission: discovery disagreements need sidecars.

## Recommended Option A: two layers, neither a new ontology nor a gold dataset

1. Give each human the same **whole-report DiscoveryWindow**. Its only fields are policy version,
   report number, exact PDF SHA, partition role, and PDF page count. All pages are included. Its
   generated ID identifies the assignment, never an object. This deliberately conservative first
   version has no editable label, section, page subset, object count, or substantive value.
2. Each human independently inspects the complete source. No object list, machine reading, pilot
   answer, other annotator's work, or suggested anchor accompanies the assignment.
3. After discovery, the human records the source start and end, object family, appropriate existing
   unit type, and source section. A source-bounded AnnotationUnit can then be constructed. Case
   observations remain single published blocks; no longitudinal case identity is inferred.
4. Compare independently locked discovery records before same-unit field comparison. Match only
   exact source-start keys. Preserve both original declarations without rewriting either unit ID.
5. Exact full units may enter the existing independent-submission validator. Same start but different
   end, page extent, section, or unit type remains a boundary/interpretation disagreement. Different
   starts remain A-only/B-only evidence, including alternative interpretations of the same block.
   M2-03 owns adjudication, not this helper and not an automatic fuzzy matcher.

The helper is a **synthetic representability proof**, not full execution infrastructure. Its models
cannot authenticate human authorship, verify a claimed PDF page count, prove that a page snapshot
came from its claimed PDF, or certify locked discovery completeness. Later M2-02A must enforce
reference custody, independent access, lock/history, and reviewed completeness before launch.
Neither a well-formed sidecar nor a successful comparison is human gold or permission to annotate.

### Window boundaries and operational burden

Whole-report windows do not disclose case or annex-row boundaries. Their burden is long inspection
sessions; future execution may save a human's private progress without presegmenting objects.
Fixed page chunks or source-authored sections could be proposed in a later policy revision with
source-neutrality review and explicit continuation/coverage rules. They are **not implemented here**.
Never use “Case 1 pages 14–16”, case headings in IDs, a window per detected case/protest row, parser
boundaries, or machine counts. Even a source-authored heading must not encode a scored answer.
Whole-report assignment avoids cross-window duplication and arbitrary page-cut ownership for now.

## Proposed start position: what is keyed and what is not

`case_detection_anchor_key_v1` is a proposed source-position key, **not a scoring implementation**.
Its canonical payload contains report number, PDF SHA, object family, coordinate-policy version,
start PDF page (one-based), full-page native-text reference SHA, and zero-based Unicode code-point
offset. SHA-256 of canonical JSON gives the opaque key. No case name, code, semantic string,
annotator ID, local ordinal, block end, or complete page tuple participates.

**Reference contract:** both humans use identical frozen, unsegmented full-page native text alongside
the PDF. UTF-8, LF only, no BOM, no Unicode normalization or whitespace repair; page separators are
not part of page text. Pin source PDF, engine/version/options, each page snapshot's bytes/hash, and
page order in later execution custody. Do not regenerate per annotator/platform. A UI must translate
selections to Unicode code-point offsets, not UTF-8 bytes or JavaScript UTF-16 code units, and show
the selected location in the original PDF for confirmation. This task builds no such UI or snapshot
distribution package. Hash mismatch is a custody failure, never permission to guess a replacement.

**Human selection rule proposed for approval:** for a case, select the first non-whitespace source
character of the human-identified block's own heading/start, excluding repeated page headers and
continuation headers. For a table row/event, select the first non-whitespace character of that
human-identified row's first populated source cell. Record the exclusive end separately. A repeated
heading with the same words at a different position remains distinct. Missing code or identical case
names are irrelevant to location. A continuation on another page retains the original start page.

Agreement on the physical start and identical reference bytes yields the same key; different source
positions yield different payloads (subject to ordinary SHA-256 collision assumptions). This is not
a claim that two humans always agree on starts. If layout order, shared cells, missing headings,
two events within one row, or indistinguishable starts prevent a unique defensible location, retain
the original evidence and an unresolved discovery issue. Do not fabricate an ordinal suffix, merge
objects, silently quantize coordinates, or fall back to a name. The helper rejects duplicate keys;
future execution must retain the attempted declarations and issue, not discard them on rejection.
Unanchorable discoveries require an issue sidecar outside these anchored proof records and block
completeness certification until M2-03 review. No unresolved record is silently omitted from gold.

### Coordinate alternatives and limitations

| Representation | Assessment |
|---|---|
| Hash-pinned native-page code-point position (recommended draft) | Exact deterministic comparison on the **same reference**; preserves duplicate text locations; human selects in source. Needs reference custody and a usable PDF/text selection interface. Native ordering can be awkward in tables. |
| Viewer click/bounding box alone | Existing evidence supports boxes, but clicks, zoom, rotation, coordinate conventions, and rounding can differ. No arbitrary tolerance is approved; boxes remain corroborating evidence, not automatic identity here. |
| Unpinned text offset/search string | Rejected: extractor settings/order, normalization, and duplicate strings can change identity. |
| Case name/code/local index | Rejected as sole matching key: substantive, absent/nonunique, or shifts when earlier objects are missed. |

Existing `EvidenceAnchor` supports `SourceSpan(start, end)` and bounding boxes; typed evidence still
requires report/hash/page/section and the appropriate locator. The new execution sidecar supplies
the reference hash/coordinate convention the frozen span model does not carry. It does not replace
SPAN, TABLE_CELL, BOUNDING_BOX, or justified PAGE_ONLY evidence and does not weaken field coverage.
Changed official PDF bytes or layout are different source versions, not silently aligned identities.

## Detection, extent, and local cardinality

A start key intentionally excludes the end and full page tuple. Two humans may find the same block
but disagree about its last page; preserve that separately. A different start **page** still changes
identity: the proposal separates end/extent errors, not all conceivable page/start errors.
Existing AnnotationUnit IDs still bind pages and a locator that includes both start and end/section.
Different ends on the *same page* also produce different units. Never manufacture a common ID to
make A/B validation succeed. No final metric is calculated by the correspondence helper.

`cardinality_index` remains local technical bookkeeping. If A misses an earlier case, B's index 1
may match A's index 0 by source position. Equal indexes can describe different physical objects.
Within matched units, repeated subobject alignment disagreements likewise remain for reviewed
adjudication; this proposal does not claim that ordinal-based field keys solve that problem.

## Repeated populations and empty discovery

| Source structure | Existing semantic representation after human discovery |
|---|---|
| Case block | `case_observation`; one block, possibly several pages. |
| Protest/violence/action/alert/agreement event row(s) | `report_annex_event` only when an actual report-level event; source-only object when linkage is unsupported. No automatic annex-to-case relation. |
| Mediation observation | Source-only object unless explicit source relationship supports another approved unit; never automatic process continuity. |
| Actors/demands/other subobjects | Humans inventory repeated instances within their independently identified source parent; explicit case attachment is not inferred from proximity. The helper does not construct case-subobject links. |
| Aggregate cell | Existing `report_month_aggregate` only for a source aggregate; not a substitute for discovering individual events. |
| Report title/reference period | A genuinely fixed `report` metadata unit may be appropriate; not a report-wide case inventory unit. |

Different families need not have identical physical boundaries. A row may encode several events,
and several rows may continue one event: preserve the human interpretation and evidence, not a
machine row inventory. All registered populations remain mandatory/reportable under M2-01.
An independently completed window with no discoveries needs a reviewed execution completion record;
it is not an empty locked AnnotatorSubmission (the frozen validator rightly rejects that).
An empty synthetic comparison proves only that no declared anchors match, not that inspection occurred.

## Read-only structural stress check (not annotation answers)

Existing immutable PDFs only; no download, OCR, annotation, persisted native text, or new machine aid.
Poppler `pdftotext` 24.04.0, `-layout -enc UTF-8 -eol unix`, stdout only. Two independent runs on the
same Windows host yielded identical full native streams for all four inspected reports:

| Report/role | PDF pages | Structural inspection | Native stream SHA-256 |
|---|---:|---|---|
| 264 / pilot | 104 | Mediation material pp. 5–7: columnar observations; select only after human identifies the block, retain continuation/boundary uncertainty. | `83a251f98c63ef4cfc76f0b655e37a7ae1c12568bc0afe84d4cfd4758fbb21e3` |
| 269 / pilot | 117 | Protest section pp. 95 onward, violence pp. 110–111, actions p. 111 onward; repeated rows and multi-line cells require human event boundaries. | `b21b4ac32aca0d01aee2380ed371af3f50d92cb29bd23e4067b5c719218c31e0` |
| 260 / development | 121 | Case material pp. 33–35: blocks and continuation text are natively inspectable; no case inventory derived. | `4277627a70196b9742e931bfd682db24486e4a42d7014635a23936e2af3d208f` |
| 261 / held out | 132 | Case material pp. 32–34: structural inspection only; no source values or object inventory enter developer fixtures. | `2f345d7f2ed2b221bf3fb216498de7e0085337b25eefde0893166e9d746c1e1d` |

On **every** inspected report, `-raw` differed from `-layout`. Offsets are therefore not
extractor-independent. These stream hashes are diagnostic, not the proposed per-page reference
manifest. This is a local repeatability check, not cross-platform native-extraction certification
or a human-usability trial. Synthetic CI proves coordinate arithmetic on identical bytes across OSs.
Later M2-02A readiness must test human selection/visual correspondence on approved synthetic material
and verify unsegmented reference custody before distribution; unresolved source-position issues must
remain visible. No full annotation package is produced here.

## Options for Jorge

| Option | Validity / independence / leakage | Schema impact | Metric impact / M3 implications | Human burden / recommendation |
|---|---|---|---|---|
| A: window + human units + separate start sidecar | Independent full-source discovery; no supplied case boundaries/counts; disputes retained. | No benchmark/scientific change; execution sidecars separate. | A later versioned, owner-approved metric amendment is required before start-key scoring. Raw discoveries can be collected after policy approval without choosing parser results. | Additional coordinate/reference custody and issue handling; recommended pending owner decision and readiness. |
| B: human exact unit IDs as detection keys | Still independently discovered, but complete boundary disagreement becomes detection FP/FN as well as page error. | None. | Existing evaluator unchanged; disclose coupled metric interpretation for owner approval. | Simpler keys, stricter segmentation sensitivity; valid alternative, not silently selected. |
| C: formal benchmark revision | Can formalize all discovery records but does not itself ensure neutral assignments or independence. | New owner-reviewed schema/version required; never mutate frozen v0.1.0. | Versioned metric alignment still needed. | Larger review/migration burden; not shown necessary for this proof. |

Option A does **not** modify `OBJECT_MATCH_FIELDS`, `evaluate_benchmark()`, thresholds, or final gate
approval. The draft config authorizes none of them. Future key scoring must amend the normative
metric contract explicitly before use; never insert the start key into `unit_id` as a workaround.
Human discovery metadata may precede that amendment because both original extents/units and start
coordinates survive, leaving the reviewed scientific evidence intact. If later execution cannot
preserve unresolved discoveries or reproducible coordinates, stop rather than launch with exclusions.

## Pending owner decisions and verification

All nine are **PENDING**; allowed responses APPROVE / CORRECT / REJECT / DEFER:

- `DISCOVERY-WINDOW`: whole-report neutral envelope, no pre-created case units.
- `POST-DISCOVERY-UNITIZATION`: construct existing semantic units only after human discovery.
- `CASE-DETECTION-ANCHOR`: proposed pinned-reference start rule and unresolved-position handling.
- `DETECTION-VS-PAGE-ATTRIBUTION`: preserve start versus end/page errors separately, with start-page coupling disclosed.
- `AB-DISCOVERY-DISAGREEMENT`: retain originals, unmatched and boundary disagreements until M2-03.
- `CARDINALITY-NONIDENTITY`: never use local index as cross-annotator identity.
- `REPEATED-OBJECT-DISCOVERY`: independently inventory rows/events and case subobjects; no automatic links.
- `FUTURE-METRIC-AMENDMENT`: separate owner-approved amendment before start-key scoring.
- `BENCHMARK-SCHEMA-NO-CHANGE`: use execution sidecars, preserve the frozen registries.

`tests/unit/test_m2_discovery_execution.py` uses synthetic report 999 only. It exercises permitted and
forbidden windows, positional matching, duplicate headings, cardinality shifts, unmatched records,
same-page/multi-page end disagreements, frozen-unit construction, actual A/B validation, Unicode
code points, reference drift, and immutable authority digests. No schema is registered for the draft
execution helpers. The ignored owner packet binds exact draft bytes and commit tree; decisions null.
