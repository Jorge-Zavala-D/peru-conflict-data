# Tooling and dependencies

M0 core is Python 3.12-3.13, uv, Ruff, Pyright, pytest, Pydantic, and PyYAML. Canonical Parquet/DuckDB dependencies are deferred until a milestone writes those formats. Candidate PDF tools include Poppler, PyMuPDF, pdfplumber, and qpdf; OCR candidates include OCRmyPDF and Tesseract Spanish; table, linkage, and geospatial stacks are installed only after benchmark evidence justifies them. `uv.lock` is the reproducible Python resolution; system binaries and versions belong in run metadata and capability inventories.
