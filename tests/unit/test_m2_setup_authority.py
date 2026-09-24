"""Synthetic-only real-v2 admission regression tests."""

import pytest

from peru_conflicts.execution.setup_authority import admit, registry_bytes


@pytest.mark.parametrize("raw", [b"{}", b"null", b'{"approved":true}', b"fixture"])
def test_production_rejects_before_resolver(raw: bytes) -> None:
    def forbidden() -> None:
        raise AssertionError("private or network lookup before admission")

    with pytest.raises(ValueError, match="no registered real grant"):
        admit(raw, forbidden)
    assert registry_bytes() == b'{"grants":[],"version":"m2-real-registry-v2"}\n'
