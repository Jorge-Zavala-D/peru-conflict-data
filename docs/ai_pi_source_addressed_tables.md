# Source-addressed table engine

`SOURCE_ADDRESSED_TABLE_ENGINE_V001` copies explicitly configured cells from retained
table JSON into documentary candidates. It checks source addresses, byte identities,
typed headers and declared evidence. It does not read PDFs, discover tables or cases,
infer scientific fields, normalize dates, score reference agreement or qualify accuracy.
Use remains bounded by the separately authorized source and output scope.

The public implementation is `src/peru_conflicts/execution/source_addressed_tables.py`.
The thin entry point is:

```text
python scripts/extract_source_addressed_tables.py --config <private-config.json> --output <new-output.json>
```

Use an existing prepared interpreter. This command does not install dependencies,
acquire sources, call providers or write canonical data. The output must be absent;
an existing result is preserved. Private source profiles, paths, pins, table values,
annotations and regression receipts do not belong in Git. The public tests generate
invented table and evidence files in temporary directories.

## Configuration boundary

The strict configuration version is `SOURCE_ADDRESSED_TABLE_CONFIG_V001`. Its root
contains `profile_id`, `source`, `inputs` and ordered `layouts`; `artifacts` and
`frames` are optional. Unknown or incorrectly typed configuration is rejected.

- `source` supplies a PDF SHA-256 identity and report number. These identify the
  source represented by the inputs; this engine does not open or independently
  authenticate the PDF.
- Each input declares an `input_id`, physical page, path, SHA-256, byte length and
  expected table count. Its JSON metadata must bind the configured source and page.
  The representation includes `source_sha256`, `physical_page`, nonempty `status`
  and `authority`, `empty_table_result_certifies_absence: false`, and `tables`.
  A table contains its serialized native `bbox` and `cells` arrays.
- Each layout names one input and table, expected row count and array width,
  complete header rows and mask, columns, selected rows, and a role of `primary`,
  `context` or `published_aggregate`. Addresses and identifiers must be unique and
  within the declared bounds. A row's `sequence` is document-local order.
- The complete header mask distinguishes `named_string`, `empty_string` and
  `null`; every declared header position occurs exactly once. Ordered
  `header_fragments` and the explicit joiner must reconstruct the configured
  column label. Header equality does not map that label to a scientific field.
- Data rows select configured column indices. Unselected substantive cells must
  remain null, apart from an explicitly configured source ordinal. Optional
  `ordinal_column` and `expected_ordinal` preserve and check the raw printed
  ordinal; they do not establish canonical identity or enter the field population.
- A separately declared fragment selects one continuation cell. Other cells in
  that row are preserved as `unselected_context_cells`. Fragment rows do not become
  documentary rows or published measurements. Header, data and fragment addresses
  form an explicit partition rather than a content-based discovery rule.

All selection follows addresses; equal labels, names, ordinals or values do not
authorize remapping. The profile is a source-specific engineering plan, not a
scientific annotation or independent source review.

## Evidence and coordinate frames

Pinned artifacts declare an ID, kind (`image` or `json`), path, hash and size.
JSON assertions bind declared pointer values. Image artifacts are PNG-only: the
reader checks the PNG signature and IHDR dimensions; JPEG and other encodings are
unsupported. An image frame names its pinned
image, physical page, dimensions and exact conventions:
`image_top_left_pixels_v1`, top-left origin, pixel units, x increasing right and
y increasing down. Image dimensions and each referenced frame must agree.

Each field can retain multiple anchors in declared order. An `image_box` anchor
names its frame and pixel box; a `json_pointer` anchor retains all declared grid
pointers and assertions. Identity, page, pointer and bounds checks precede use.
`image_cell_box` is a convenience projection of the first image anchor; it does
not replace the complete `evidence_anchors` list.

The native table box remains serialized native evidence without a newly qualified
coordinate frame. Image boxes remain image pixels. The engine supplies no native
to image transform, page rotation correction or historical coordinate conversion.
Valid coordinates and pointers establish mechanical correspondence, not semantic
support for a scientific claim.

## Output and processing states

The output separates `documentary_rows`, `published_measurements` and
`continuation_fragments`. Documentary rows retain primary/context roles and exact
input, layout, page, table and row addresses. Published measurements preserve
source-reported aggregate strings; they are not inferred row counts. Fragments
carry `context_only: true` and `creates_observation: false`.

Every planned selected cell retains a processing result, including cells in failed
components. A processed field preserves the decoded `original_value`, exact
`source_lexical_json_token`, compact Unicode `typed_value_json`, type, source JSON
pointer and evidence. The source lexical token and typed derivative are distinct:
an authored Unicode escape can remain escaped in the former and decoded in the
latter. Newlines, repeated spaces and literal invalid date strings remain intact.

| Input condition | Processing status | Type | Semantic state |
|---|---|---|---|
| String, including empty string | `processed` | `string` | `observed` |
| Explicit null cell | `unavailable_null_cell` | `null` | null |
| Selected cell absent from a short row | `unavailable_missing_cell` | `missing` | null |
| Boolean, number, array or object cell | `invalid_cell_type` | Preserved JSON type | null |
| Component not processed | Explicit unprocessed status | null | null |

False, numeric zero, null, empty string and absence remain distinct. An unavailable
or invalid cell does not acquire a source-level annotation state. The engine does
not instantiate complete scientific domain models or assign canonical aliases.

Input/configuration JSON parsing rejects duplicate properties, nonfinite numbers,
invalid UTF-8 and invalid Unicode. Header, filler, identity and frame failures are
reported with configuration, input, artifact or layout scope. An affected component
retains planned coverage while unaffected components can still be processed.

`candidate_status` is `processed` on complete processing, `partial` when processing
and failures coexist, and `input_rejected` when nothing can be processed. Exit 0
means complete processing; exit 2 means a partial/rejected receipt was written.
Argument or persistence failures return a nonzero status and may prevent a receipt.
Output creation is exclusive. `runtime` records execution metadata and is excluded
from deterministic engineering-payload equivalence comparisons.

The focused public CLI tests establish these engineering behaviors on invented
fixtures. They do not measure discovery completeness, source interpretation,
reference accuracy, regime transfer, PI review or readiness for data release.
