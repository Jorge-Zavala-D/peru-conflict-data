# M1-01 robots, rate-limit, and terms receipt

Observed 2026-08-27 (UTC). This is a read-only evidence receipt, not a legal
opinion and not permission for aggressive crawling or redistribution.

## `www.defensoria.gob.pe`

- `https://www.defensoria.gob.pe/robots.txt` returned HTTP 200,
  `text/plain; charset=UTF-8`, 4,498 bytes, with `Last-Modified: Wed, 01 Apr
  2026 22:25:21 GMT` in the header observation.
- `User-agent: *` contains specific `Disallow` paths. The audited catalogue,
  search, thematic, `/documentos/`, and general upload-prefix paths were not
  blanket-disallowed. No `Crawl-delay` directive was observed.
- The final9 M1-02 run used one serial client, a stable user agent, 2.0-second
  minimum spacing, and retry cap 2. Its 148 receipts were HTTP 200. No
  `Retry-After`, `X-RateLimit-*`, or other rate-limit signal was observed in the
  sample headers. Absence of a header is not permission to increase request rate.

## Bare host

- `https://defensoria.gob.pe/robots.txt` returned HTTP 200 with a 25-byte
  permissive `User-agent: * / Allow: /` response from nginx.
- The bare-host root served a Zimbra login page rather than the public WordPress
  site. No report discovery was performed there. This host behavior is preserved
  as a discrepancy; it is not silently treated as the `www` site.

## Terms and rights observation

The public homepage/footer and audited HTML links were searched for terms-of-use,
privacy/legal, license, copyright, Creative Commons, and open-data indicators. No
clear site-wide reuse or open-data license for the PDFs was located in this pass.
That negative search result is not a legal conclusion. Internal research
acquisition may be proposed into the private Dropbox corpus; public redistribution
of source PDFs, `Base15-26.xlsx`, or source-derived releases remains unresolved and
requires a separate institutional/legal decision.

## Responsible protocol

Use only the approved `www` public surfaces unless a host review adds evidence.
Honor robots per URL, keep concurrency at one, wait at least two seconds, honor
`Retry-After`, stop/back off on repeated 429/503 responses, record final URLs and
redirect chains, and never fetch a discovered PDF merely because an HTML page links
to it. The exact unexecuted acquisition bounds are in
`docs/m1_acquisition_checkpoint.md`.
