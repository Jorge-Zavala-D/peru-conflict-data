"""Content hashes used for immutable sources and reproducible configuration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON-compatible data with stable ordering and type preservation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def hash_mapping(value: Mapping[str, object]) -> str:
    """Return a stable SHA-256 for a JSON-compatible mapping."""

    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()
