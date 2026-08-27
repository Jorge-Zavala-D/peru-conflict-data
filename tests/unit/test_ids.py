from __future__ import annotations

from uuid import UUID

import pytest

from peru_conflicts.ids import ID_SCHEME_VERSION, stable_id


def test_stable_id_is_repeatable_and_namespaced() -> None:
    first = stable_id("report", 260, "89c066")
    second = stable_id("report", 260, "89c066")
    other_kind = stable_id("case", 260, "89c066")

    assert first == second
    assert first != other_kind
    assert first.startswith("report_")
    assert UUID(first.removeprefix("report_")).version == 5


def test_stable_id_preserves_null_empty_and_zero() -> None:
    identifiers = {
        stable_id("field", None),
        stable_id("field", ""),
        stable_id("field", 0),
    }

    assert len(identifiers) == 3


@pytest.mark.parametrize("kind", ["", "  "])
def test_stable_id_rejects_blank_kind(kind: str) -> None:
    with pytest.raises(ValueError, match="kind"):
        stable_id(kind, "value")


def test_stable_id_requires_identity_parts() -> None:
    with pytest.raises(ValueError, match="part"):
        stable_id("case")


def test_stable_id_v1_golden_vector() -> None:
    assert ID_SCHEME_VERSION == "1"
    assert stable_id("report", 260, "89c066") == ("report_4c1ae8fc-a14d-5caa-8ab4-2f57c810e9b4")
