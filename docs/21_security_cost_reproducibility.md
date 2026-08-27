# Security, cost, and reproducibility

Use responsible official-source retrieval with a declared user agent, rate limits, retries, and cache. OCR only selected pages. Model calls, when approved, use minimal segments, content-addressed caching, and cost tracking. Every run records Git commit/dirty state, configuration/schema/parser versions, Python/lockfile/environment identity, input hashes, and model/prompt versions where applicable. Use stable ordering and explicit seeds for stochastic work. CI has no Dropbox, corpus, or credentials.
