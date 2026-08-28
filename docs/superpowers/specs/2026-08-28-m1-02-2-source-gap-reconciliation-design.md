# M1-02.2 Source-Gap Reconciliation Design

## Objective

Correct five source-visible historical HTML misses without widening the corpus
definition, add a reviewed exact-URL landing-page verification path, and close the
credential-permission governance gap. PR #2 remains open and unmerged. M1-03 and
all binary retrieval remain prohibited.

## Evidence-backed parser boundary

The committed parser fails on five official structures:

- `Reporte Mensual de Conflcitos Sociales N° 122 – abril 2014`;
- `Reporte Mensual de Conflcitos Sociales N° 125 – julio 2014`;
- `Reporte mensual de conflictos N° 136 – junio 2015`;
- a bounded report-172 entry whose qualified title is
  `Reporte Mensual de Conflictos Sociales N° 172` and whose local secondary span
  is `Reporte Mensual N° 172 – junio 2018`;
- a report-175 landing entry whose qualified heading lacks a month while a local
  visible link label states `Conflictos Sociales N° 175 - Septiembre 2018`.

Recognition changes are literal and structural, never fuzzy:

1. Allow the observed `conflcitos` spelling only in the otherwise qualified
   social-conflict report phrase.
2. Allow the missing-`sociales` form only when `Reporte mensual de conflictos`
   is followed by an explicit `N`/ordinal marker and a one-to-four digit number.
3. An abbreviated local span cannot qualify an entry. After a bounded entry is
   independently qualified and its report number is known, a local heading,
   paragraph, or visible link label may supply month evidence only when it uses
   an explicitly allowed abbreviated structure, repeats the same report number,
   and contains a parseable month/year.
4. The exact local node text supplies the reference-period evidence excerpt.
   Page-global text and publication dates never supply a reference period.

Final traversal audit exposed one additional official bounded form: report 117
places `Reporte Nº 117` in the heading and
`Reporte mensual de conflictos sociales – noviembre 2013.` in a separate
description. A numberless local span may therefore supply a period only when the
entry already establishes a report number and the single period-bearing span
independently names the complete conflict-report series. A span with another
explicit number, an unqualified numberless month, or month/year tokens split
across nodes remains ineligible.

Negative fixtures cover generic institutional reports, environmental or special
conflict publications, standalone abbreviated labels, mismatched report numbers,
page-global month strings, and publication dates.

## Reviewed targeted landing-page mechanism

`config/official_sources.yaml` advances its source-policy configuration contract
from version 2 to version 3 and gains an exact reviewed targeted-landing registry.
The initial and only M1-02.2 entry is report 175's official HTTPS landing page.
Callers select it by reviewed identifier, not by arbitrary URL. Configuration
validation pins the exact host, URL, role, and single-page behavior.

The CLI may combine selected ordinary surfaces with selected reviewed targeted
landings. Targeted landings are traversed as single-page `LANDING_PAGE` surfaces,
so they do not increase or bypass the ordinary 24-page discovered-landing cap.
Explicit targeted starts are excluded from the ordinary discovered-landing queue
to prevent a duplicate request if the same URL is also discovered. They use the
existing serial `HtmlClient`, robots policy, two-second spacing,
retry cap, redirect validation, MIME-before-body gate, body cap, receipts, and
repository-cache output boundary. No discovery v0.3 record or receipt field must
change.

## Live-run sequence

1. Build source-faithful fixtures and demonstrate RED on the committed parser.
2. Implement the minimum changes and run the complete offline suite.
3. Run one targeted check consisting only of the one-page Paz Social thematic
   surface and the reviewed report-175 landing page, with general landing cap
   zero. Verify reports 122, 125, 136, and 172 from the thematic page and report
   175 from its landing page.
4. Obtain independent read-only review of source recognition, false positives,
   targeted authority, and credential policy.
5. If review passes, run one replacement bounded complete HTML-only
   reconnaissance using the four ordinary surfaces, the reviewed report-175
   landing, and the unchanged 24-page general landing cap.

The one complete traversal exposed the report-117 structure above. It was not
repeated. After fixture-based correction and independent review, a two-page
targeted supplement re-observed only the thematic page and report-175 landing
under the same HTML-only boundary. The complete traversal and supplement are
reported as an explicit evidence bundle with separate hashes.

Earlier M1-02.1 artifacts remain immutable evidence and are labeled superseded.
The replacement run gets a distinct directory, run identity, byte counts, and
SHA-256 values. The full JSONL inventory remains Git-ignored.

## Credential boundary

Repository policy must prohibit agents from querying credential helpers,
keychains, password managers, environment-held secrets, stored OAuth/API tokens,
or equivalent stores. Agents must not construct authorization headers from user
secrets to bypass a connector denial. Normal Git operations mediated by
preconfigured authentication remain allowed. If a connector denies an explicitly
authorized GitHub action, use the authenticated browser UI only after explicit
user confirmation when available; otherwise stop and ask. No credentials are
rotated or changed in this pass.

## Preservation requirements

- Scientific schema versions `v0.1.0` and `v0.2.0` remain byte-identical.
- Discovery schema versions `v0.1.0`, `v0.2.0`, and `v0.3.0` remain byte-identical.
- Dropbox receives zero writes; all eleven source hashes must match.
- `02_extracted` through `07_releases` remain empty.
- Reports 1-22 and 2004/2005 monthly structure remain unresolved.
- The reports-260-269 pilot v1 stays fingerprinted and `not_authorized`.
- No acquisition script, authorization override, PDF/ZIP request, OCR, parsing,
  M1-04, or M2 work is permitted.

## Acceptance evidence

- Fixture tests independently recover each of the five official spans and retain
  exact Spanish source text.
- Negative fixtures demonstrate that the tolerance does not admit unrelated
  institutional publications or publication-date inference.
- Targeted requests contain only approved HTTPS HTML and exact-host robots text.
- Replacement inventory coverage is reported as observed evidence, never as an
  encoded expected count or completeness claim.
- Full local quality and exact-head GitHub Actions pass on Python 3.12 and 3.13.
- PR #2 remains open and unmerged at the stop point.
