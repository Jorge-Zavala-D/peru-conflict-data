# M1-02.1 historical-discovery hardening design

## Status and authorization boundary

Jorge approved M1-01 and authorized a corrective M1-02.1 pass on
`codex/m1-01-02-corpus-discovery`. M1-03, M1-04, and M2 remain prohibited. This
pass may retrieve only approved official HTML/XHTML and each approved host's
plain-text `robots.txt`. It may not request PDF or other binary bodies, write to
Dropbox, create an operational manifest, parse report content, or materialize
canonical data.

Scientific schemas `v0.1.0` and `v0.2.0` remain byte-identical. Discovery schema
directories `v0.1.0` and `v0.2.0` remain historical receipts. The corrected
machine contract is a forward version, `discovery/v0.3.0`.

## Source-entry metadata contract

One multi-entry HTML page is not one report observation. Discovery `v0.3.0`
separates the containing page's visible title from each entry's title,
publication date, and source description. Candidate identity evidence is drawn
only from the candidate entry's bounded source block. A page-wide first date is
never copied to every entry.

The parser recognizes source entry headings from `h1` through `h6`, while using
heading level, article/card/list-item containment, and source order to keep
adjacent entries independent. The observed thematic structure is one `.card`
whose `h4` title may be generic (for example, `Conflictos Sociales`), whose `h6`
contains the publication date, whose entry-local paragraph contains the report
number/reference month, and whose links are labelled only `Descargar`. Official
search results use independent `<li>` blocks with their own Spanish date, landing
link, and description. These strings are represented without collapsing them.
Multiple links remain associated only with their source entry. Unrelated conflict
publications remain visible links but do not become monthly-report candidates
merely because the page contains the word `conflicto`.

The 2004 and 2005 entries are observed historical source leads with null candidate
months unless the entry itself visibly states one. Their official card links are
ZIP URLs, which are retained as unrequested direct-file observations. Numbered
2006 reports begin with observed number 23; discovery does not infer reports 1-22
or manufacture a monthly series from annual/bundled labels.

## Pagination and coverage semantics

Pagination extraction supports the site's observed WordPress navigation signals,
including `rel=next`, next-page classes/accessibility labels, and numeric page
links inside `.pagination`. The observed search page has a current-page `<span>`,
page-2 and page-9 anchors, a nested `<strong>-›</strong>` forward link, and an
`Último »` link. The parser selects page 2, never the last-page shortcut. Fixtures
preserve the Spanish source labels and the real query/path shapes.

Machine output distinguishes:

- local traversal termination: this bounded process stopped for a recorded reason;
- pagination exhaustion: no later page was exposed under a separately verified
  surface-specific pagination contract;
- corpus completeness: not assessed by M1-02.1.

`NO_NEXT_LINK` and `REPEATED_URL` are local termination reasons, not corpus
completeness claims. A repeated URL is never pagination exhaustion.

## Enforced live-safety envelope

The ordinary M1 command accepts only settings at least as conservative as the
reviewed configuration:

- concurrency exactly `1`;
- delay at least `2.0` seconds;
- at most `2` retries after an initial attempt;
- at most `120` pages per starting surface;
- at most `24` landing pages;
- approved hosts exactly `defensoria.gob.pe` and `www.defensoria.gob.pe`.

A caller may lower page/landing/retry limits or increase the delay. It may not
weaken these bounds through CLI flags. A future exception requires a separately
reviewed configuration/code change; M1-02.1 implements no generic bypass flag.

## Request-attempt evidence and body gate

Each actual HTTP attempt has its own UTC start/completion timestamps, URL,
attempt/hop number, outcome, status when observed, and a strict allowlisted set of
response headers: `Content-Type`, `Content-Length`, `ETag`, `Last-Modified`,
`Retry-After`, and recognized rate-limit headers. Cookies, authorization headers,
and arbitrary headers are never retained.

For an approved HTML/XHTML or scoped robots body, the receipt records whether the
body was read, its exact byte count, and SHA-256. Redirects, transient failures,
and rejected content types remain separate attempts. The standard-library
transport inspects status and MIME headers before calling `read()`. Only
`text/html` and `application/xhtml+xml` may be read for page discovery; only
`text/plain` may be read for the exact `/robots.txt` request. An absent or unlisted
MIME type is rejected without reading or interpreting its body.

## Durable versus temporary evidence

The complete provisional inventory remains in ignored `.cache/`. Git records a
small durable receipt containing the final `records.jsonl`, `requests.jsonl`, and
`summary.json` byte counts and SHA-256 values, plus reviewed aggregate findings.
This does not turn Git into the mutable operational ledger.

The M1-03 handoff uses a small reviewed YAML pilot plan for reports 260-269 rather
than an ignored cache file. It contains public official landing/direct URLs,
candidate number/month, uncertainty, logical existing raw path, and the already
reviewed local baseline SHA-256. The local hash is not relabelled as an expected
remote hash: `expected_remote_sha256` remains null until authorized bytes are
actually observed. It is an immutable acquisition recipe, not an acquisition
ledger or authorization.

For the eventual pilot, official bytes differing from an expected benchmark hash
must stop before promotion. Identical bytes produce no duplicate raw object.
Multiple URLs may point to one content hash while retaining distinct URL
observations. Host, robots, HTTP status, MIME, bounded size, `%PDF-` signature, and
SHA-256 checks all precede any future promotion.

## Execution and acceptance sequence

Implementation is fixture-first and offline. After unit/integration tests pass, a
small targeted live HTML-only check may verify the observed thematic and search
patterns. An independent reviewer then audits the integrated diff. Only after all
important findings are fixed may one final bounded reconnaissance run execute.

Acceptance requires the final inventory to represent at least the visible 2004 and
2005 leads and numbered reports 23 onward in 2006, while preserving early-period
ambiguity. The complete local quality gate, all eleven source hashes, and zero file
counts in Dropbox layers `02_extracted` through `07_releases` must be reverified.
The branch is then pushed, a pull request to protected `main` is opened, and both
required GitHub checks are awaited on the exact head. The task stops with the PR
open and unmerged.
