# Local AI/PI processing recipe and explicit aggregate consumer

This is a source-only internal processing candidate, not a scientific dataset,
new reader run, reference freeze, evaluation, source publication or release.
All examples below are invented. No real research input is needed to reproduce
the demonstrated seam.

## Project-source stages and boundaries

| Stage | Project source | Inputs and limits |
| --- | --- | --- |
| Envelope, packets, budget and raw-response freezing | `execution.ai_pi_batch` | Independently authorized source/tool/code identities and bounded source units. Exclusive publication retains raw bytes before normalization. A failure is retained, not source absence. |
| Native preparation and typed initial/follow-up normalization | `execution.ai_pi_batch_runtime` | Explicit caller-supplied envelope, original responses and retained references; no implicit reader/provider. Native preparation requires installed pinned PDF tools and separate source-processing authority. |
| Evidence binding | `execution.ai_pi_batch` and `execution.evidence_regions` | Ordinary full-page/span checks remain strict. `native_bbox_words_v1` is selected only by explicit original-anchor/response/layout bindings, never as a mismatch fallback. See [the region contract](ai_pi_region_evidence_method.md). |
| Same-report context | `ReportContextAssociation` in `execution.ai_pi_batch` | Only `report.report_number` and `report.reference_period`; it does not widen case boundaries or validate other fields. |
| Explicit aggregate consumption | `execution.aggregate_processing.parse_report_month_aggregate` | One JSON object with explicit supported base version; absence of a discriminator selects legacy, the exact supported discriminator selects the additive extension. |
| Internal staging and review | Existing domain models plus separately retained lineage/qualification records | Model validation is not evidence verification, canonical identity, human review, completeness or scientific acceptance. |

The generic processing is versioned; the explicit model-consumption seam is
included in this source candidate and must be bound by its commit or working-file
inventory. The
historical external adjudication/reporting helpers are not source entry points
for the demonstrated command. Their source-specific correspondence decisions,
period-label evidence, delegated origin, qualifications and output publication
remain separate retained application inputs. This command does **not** recreate
that historical adjudication packet, derive months from labels, fabricate missing
parents or freeze an empirical reference. A broader historical end-to-end replay
must supply those explicit application inputs; it is not established by this
synthetic demonstration.

## Aggregate input and output contract

`scripts/validate_report_month.py` reads one UTF-8 JSON object from standard input
and writes validated UTF-8 JSON plus LF to standard output. It opens no input or
output file, invokes no PDF/model/provider tool and does not mutate the input.
Failure is nonzero with no normalized output on stdout. Callers must retain raw
input bytes and provenance separately; serialization is a derivative, not an
exclusive raw-byte freeze or a scientific literal-byte match.

Every input must explicitly carry `schema_version="0.3.1"`. With no
`aggregate_contract`, it must satisfy `ReportMonthAggregate`; `observation_period`
is then forbidden. With `aggregate_contract="report_month_observation_v1"`, it
must satisfy `ReportMonthAggregateObservationV1`. Unknown/null discriminators or
unsupported/missing versions are rejected. The base version alone never infers
the extension; legacy registry consumers remain unchanged and reject new fields.

The source report's `ReportRecord.reference_period` stays separate. An omitted
or null observation month remains unspecified; no report date, file date or
timestamp is used to fill it. Supplied months retain month precision; equal
values in different months remain distinct records. The consumer performs no
deduplication, value calculation or source interpretation. IDs in the example
are technical invented identifiers, not canonical world identities.

Domain guards still require source-reported provenance or, for derived values,
calculation/version/upstream lineage. Missing values remain null, never zero.
Literal strings survive unchanged. Month syntax is not evidence support. A
record's source-value origin is not its judgment origin: AI-delegated assisted
rulings must keep their separate exposure/authorization sidecar, and are not
independent human source-first evidence. Full-page/region methods and scientific
acceptance gates are untouched.

## Synthetic reproduction without provisioning

From the intended checkout, choose an **already installed** Python 3.12–3.13
interpreter with the frozen project dependencies. The explicit source insertion
below prevents an editable installation from silently importing another checkout.
Do not use `uv run` in an unprovisioned checkout or install anything to run this
example. It uses only the versioned entry and installed dependencies, not a
private helper.

```powershell
$recipeRoot = (Get-Location).Path
$recipePython = Read-Host 'Absolute path to the existing project Python interpreter'
$synthetic = '{"schema_version":"0.3.1","aggregate_contract":"report_month_observation_v1","report_month_id":"invented:observation","report_id":"invented:later-report","metric_original":"Invented measure","indicator_basis":"source_reported","value":7,"provenance_ids":["invented:anchor"],"observation_period":"2030-12"}'
$synthetic | & $recipePython -I -B -c "import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); runpy.run_path(sys.argv[1], run_name='__main__')" "$recipeRoot/src" "$recipeRoot/scripts/validate_report_month.py"
if ($LASTEXITCODE -ne 0) { throw 'Synthetic aggregate validation failed' }
```

Expected output retains the invented value and `2030-12`, declares the explicit
extension, and adds only model defaults (including nulls). Remove only the
discriminator and observation month for a legacy example. Keep the month but
remove the discriminator for an intentionally rejected legacy input. No command
above writes a file; PowerShell's ASCII-only synthetic input avoids console
encoding ambiguity. Real callers must supply UTF-8 bytes without rewriting raw
scientific strings. Unicode byte-input/output is covered by the synthetic tests.

Focused checks using the same already installed interpreter and explicit checkout
source binding:

```powershell
& $recipePython -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); import pytest; raise SystemExit(pytest.main(sys.argv[1:]))' "$recipeRoot/src" tests/unit/test_aggregate_processing.py tests/unit/test_observation_period.py -q -p no:cacheprovider
& $recipePython -I -B -c "import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); sys.argv.pop(0); runpy.run_path(sys.argv[0], run_name='__main__')" "$recipeRoot/src" scripts/export_schemas.py --check
```

These are focused/direct invocations, not proof of configured pre-commit or full
suite execution. Exact commands, tool fingerprints, return codes, timings,
review applicability and candidate file hashes belong in the separate technical
receipt, not in Git with laptop-specific paths or real data.

## Validation and reproducibility limits

Unchanged legacy and additive schemas are checked for generated freshness.
`tests/unit/test_observation_schema_validation.py` uses the development-only,
pinned Draft 2020-12 validator against the exact exported schemas, with remote
reference retrieval refused. Month assertions use explicit schema constraints,
not an assumed `format` check. Execution evidence still belongs in the technical
receipt. Native Windows execution and Windows/Linux static targets differ.

Configured hooks, installed hooks, selected cached controls, direct checks,
full-suite execution and hosted CI are distinct control states. Missing required
controls must remain explicit; no bypass or disabled hook establishes readiness.
The old hook-override episode remains a historical qualification. A local commit
or later passing check cannot retroactively prove unobserved historical commands.

Deterministic processing of frozen inputs is reproducible within its pinned
code/tool/reference contract. Future stochastic reader responses, successful
normalization of every retained B record, complete discovery, accuracy and human
acceptance do not follow. No research artifact or database is produced here.
