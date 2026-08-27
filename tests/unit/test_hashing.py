from __future__ import annotations

from pathlib import Path

from peru_conflicts.hashing import hash_mapping, sha256_file


def test_sha256_file_matches_empty_file_vector(tmp_path: Path) -> None:
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")

    assert sha256_file(source) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_file_matches_known_bytes_vector(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abc")

    assert sha256_file(source) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_hash_mapping_is_independent_of_key_order() -> None:
    first = {"report": 260, "status": None, "values": [1, 2]}
    second = {"values": [1, 2], "status": None, "report": 260}

    assert hash_mapping(first) == hash_mapping(second)


def test_hash_mapping_preserves_missingness_distinctions() -> None:
    assert hash_mapping({"value": None}) != hash_mapping({"value": 0})
    assert hash_mapping({"value": None}) != hash_mapping({"value": ""})
