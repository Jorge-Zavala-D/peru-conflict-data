---
name: pdf-forensics
description: Diagnose native text, layout, tables, and page-level OCR need for an explicitly scoped Defensoria report; use before selecting a parser or OCR strategy.
---

# PDF forensics

Work read-only from immutable PDFs. Record source hash and engine versions. Check native-text coverage, ordering, headings, coordinates, and table structure before considering OCR. OCR only selected pages after evidence shows the native layer is unusable, and write derived outputs outside raw storage. Return page-specific findings, disagreements, and uncertainty; do not build a universal parser.
