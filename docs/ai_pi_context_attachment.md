# Source-bound context attachment

`scripts/attach_source_context.py` creates an inspection view from explicitly supplied,
byte-pinned native words, inherited documentary cells/grouping, and attributed context
assertions. It discovers no captions or rows and performs no extraction, semantic
adjudication, normalization, scoring, acquisition or operational dispatch.

The public library function is
`peru_conflicts.execution.context_attachment.attach_context(request, documents)`.
`documents` maps the request's exact aliases to original UTF-8 bytes. The same bytes
are hashed and parsed; request and document objects are not rewritten. The contract
remains `SOURCE_BOUND_CONTEXT_ATTACHMENT_V002`; profile version remains
`SOURCE_BOUND_CONTEXT_ROLE_PROFILE_V001`.

## Two bounded profiles

Each supported profile has exactly three declared columns; this is not arbitrary-column
or arbitrary-ontology support. Column IDs and original column indices are explicit.

| Profile | Documentary roles | Permitted qualifiers and target scope |
| --- | --- | --- |
| `regional_quantitative` | category, count, percentage | subject/reporting period: table; geographic breakdown: reported organization; count unit: count column only; percentage sign: percentage column only |
| `priority_documentary` | place text, case description, published situation | introductory scope and documentary scope: table only |

A role label is not evidence of applicability. A permitted attachment additionally needs
an attributed assertion matching qualifier kind, target and exact source-word segments.
This establishes machine-readable support under the contract, **not semantic truth** or
independent source review. Unsupported qualifiers and missing semantic support remain
unresolved with no edge, while valid literal cells remain inspectable. Missing source
bindings, conflicting ownership and changed grouping are failures, not abstention.

Original strings, own-text spans, geometry, layout pointers, cell/row record hashes and
ordered memberships remain source-addressed. Root JSON pointers and escaped property
names are supported; array indices must be canonical nonnegative integers. Duplicate
JSON keys and nonfinite values are rejected. Captions and introductory paragraphs are
distinct non-cell context kinds; header/ordinal metadata stays separate from substantive
cells. A lossless receiving descriptor is derivative metadata, not invented original IDs.

`unknown`, `confirmed_none`, `reported_empty`, `absent_field` and
`unreviewed_interpretation` remain distinct evidence-backed states. Literal fragments,
reconstructed display values (including inserted joining syntax) and AI applicability
are separate. An owner-authorized execution does not make AI evidence human-reviewed.
Every view forces inspection true and normalization, automatic dispatch, scientific
acceptance and benchmark scoring false, regardless of supplied permission fields.

## Explicit CLI and file locations

```text
python -I scripts/attach_source_context.py --request request.json --locations locations.json --output-json new-view.json --output-markdown new-view.md
```

Run from a checkout using an already installed supported Python interpreter and project
dependencies. The thin script binds imports to its own checkout, not a different editable
installation. No environment, private folder, DATA_ROOT or sibling packet is discovered.
The library is also usable from an ordinary installed package.

`locations.json` is operational configuration, separate from semantic input:

```json
{"documents": {"native": "invented-native.json", "proposal": "invented-proposal.json", "descriptor": "invented-descriptor.json", "profile": "invented-profile.json", "assertions": "invented-assertions.json"}}
```

Aliases must exactly match the request's document registry. Paths are resolved relative
to the location file; absolute supplied paths are also accepted. The registry in the
request supplies each document's SHA-256. Locations never renumber pointers, rewrite
assertions or enter the resulting semantic payload. The committed invented tests show
complete populated requests for both profiles and both inherited record formats.

Both outputs must be absent and distinct, cannot overwrite inputs, and cannot target
protected external/raw/archive storage. Serialization precedes exclusive creation.
The two output files are **not transactionally atomic**: if the second write fails,
the first output is retained and stderr reports which paths exist. Failures return 2;
success returns 0. Do not overwrite or silently retry a real first result.

## Verification and limits

Focused invented tests cover library/CLI behavior without private fixtures or research
inputs. Ordinary W10I commit controls remain required; full canonical validation is a
separate merge/release obligation. Runtime coverage, exact implementation identities and
any separately authorized real replay belong in external execution receipts, not this
source-neutral contract or the semantic view.

This component is not automatically wired into the native pipeline or extraction engine.
It does not change production ownership/admission/no-dispatch decisions, scientific
schema or metrics, canonical identities, milestones or readiness flags. Attaching supplied
context does not establish complete boundaries, alternative-universe completeness,
semantic correctness, unseen-report performance, scientific accuracy or M2R-05/M2R-06
completion. Different-source execution needs its own source-content and generation scope.
