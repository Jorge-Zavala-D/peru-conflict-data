"""Deterministic identifiers for source-derived records."""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, UUID, uuid5

from peru_conflicts.hashing import canonical_json_bytes

PROJECT_NAMESPACE: UUID = uuid5(
    NAMESPACE_URL, "https://github.com/Jorge-Zavala-D/peru-conflict-data"
)
ID_SCHEME_VERSION = "1"
_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def stable_id(kind: str, *parts: object) -> str:
    """Build a repeatable UUID5 identifier while preserving JSON value types."""

    normalized_kind = kind.strip()
    if not _KIND_PATTERN.fullmatch(normalized_kind):
        raise ValueError("kind must be a nonblank lower-case identifier")
    if not parts:
        raise ValueError("at least one identity part is required")

    identity = canonical_json_bytes({"kind": normalized_kind, "parts": parts}).decode("utf-8")
    return f"{normalized_kind}_{uuid5(PROJECT_NAMESPACE, identity)}"
