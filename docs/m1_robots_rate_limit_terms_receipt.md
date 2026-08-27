# M1-01/M1-02.1 robots, rate-limit, and terms receipt

Observed 2026-08-27 (UTC). This is read-only technical evidence, not a legal
opinion, a completeness claim, or permission for acquisition or redistribution.

## `www.defensoria.gob.pe`

The definitive run requested
`https://www.defensoria.gob.pe/robots.txt` once. It returned HTTP 200,
`text/plain; charset=UTF-8`, 4,498 bytes, body SHA-256
`e3b1c1216583a7e9986736aee879875b60c400efa5e140ccb6294c0d0412cc0e`,
declared `Content-Length: 4498`, and
`Last-Modified: Wed, 01 Apr 2026 22:25:21 GMT`.

`User-agent: *` contains specific disallowed paths. The audited catalogue,
search, thematic, `/documentos/`, and general upload-prefix paths were not
blanket-disallowed. No `Crawl-delay` directive was observed. The client evaluated
robots for every page request and did not retrieve linked files.

The definitive run used one serial client, a 2.0-second minimum delay, and retry
cap 2. Its 165 attempts all returned HTTP 200: 164 HTML pages and one robots
response. No retry occurred, and no `Retry-After`, `ETag`, `Location`, or
recognized rate-limit header was observed. Only robots supplied Content-Length
and Last-Modified. Absence of rate-limit headers is not permission to increase
request frequency.

## Bare host observation

An earlier read-only M1 observation found that the bare-host root served a Zimbra
login rather than the public WordPress site, while its robots response differed
from the `www` response. The definitive run therefore used only the reviewed
`www` starting surfaces. The bare host remains on the initial authority allowlist
so an observed URL can be retained and reviewed; it is never silently rewritten
to or from `www`.

## Terms and rights observation

The public homepage/footer and audited HTML links were checked for terms-of-use,
privacy/legal, license, copyright, Creative Commons, and open-data indicators. No
clear site-wide license authorizing redistribution of the PDFs was located. This
negative observation is not a legal conclusion.

Public accessibility is distinct from redistribution permission. A later
explicitly authorized M1-03 may acquire publicly accessible official reports for
internal research into the private Dropbox corpus. Public redistribution of the
Defensoría PDFs, `Base15-26.xlsx`, or source-derived releases remains unresolved
and separately gated for institutional/legal review.

## Responsible protocol retained for any future authorization

- use only the two explicitly reviewed hosts and review every new redirect host;
- keep concurrency at one and delay at least 2.0 seconds;
- honor `Retry-After`, stop/back off on repeated 429/503 responses, and keep both
  per-request and global attempt caps;
- record every request attempt, safe response headers, redirect edge, body byte
  count, and body hash without cookies or credentials;
- reject unapproved MIME types before body interpretation; and
- never fetch a discovered PDF merely because an HTML page links to it.

The exact still-unexecuted pilot bounds are in
`docs/m1_acquisition_checkpoint.md`.
