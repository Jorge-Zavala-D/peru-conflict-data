from __future__ import annotations

from pathlib import Path

import pytest

from peru_conflicts.paths import (
    EXPECTED_TOP_LEVEL,
    DataPathError,
    DataPaths,
    MissingDataRootError,
    ReadOnlyZoneError,
)


def make_data_root(parent: Path) -> Path:
    root = parent / "external-data"
    for name in EXPECTED_TOP_LEVEL:
        (root / name).mkdir(parents=True)
    return root


def test_resolve_requires_explicit_root_when_environment_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CONFLICT_DATA_ROOT", raising=False)

    with pytest.raises(MissingDataRootError, match="CONFLICT_DATA_ROOT"):
        DataPaths.resolve(repo_root=tmp_path / "repo")


@pytest.mark.parametrize("relative", [Path("."), Path("data")])
def test_resolve_refuses_repository_or_child_as_data_root(tmp_path: Path, relative: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate = repo / relative
    candidate.mkdir(exist_ok=True)

    with pytest.raises(DataPathError, match="Git repository"):
        DataPaths.resolve(repo_root=repo, data_root=candidate)


def test_resolve_refuses_data_root_that_contains_repository(tmp_path: Path) -> None:
    data_root = make_data_root(tmp_path)
    repository = data_root / "02_extracted" / "accidental-repository"
    repository.mkdir()

    with pytest.raises(DataPathError, match="overlap"):
        DataPaths.resolve(repo_root=repository, data_root=data_root)


def test_resolve_reports_all_missing_expected_directories(tmp_path: Path) -> None:
    root = tmp_path / "external-data"
    root.mkdir()

    with pytest.raises(DataPathError) as error:
        DataPaths.resolve(repo_root=tmp_path / "repo", data_root=root)

    assert "00_external" in str(error.value)
    assert "07_releases" in str(error.value)


def test_synthetic_root_exposes_named_zones(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)

    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=root)

    assert paths.external == root / "00_external"
    assert paths.raw == root / "01_raw"
    assert paths.validation == root / "06_validation"


@pytest.mark.parametrize("zone", ["00_external", "01_raw"])
def test_routine_writes_are_refused_in_source_zones(tmp_path: Path, zone: str) -> None:
    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=make_data_root(tmp_path))

    with pytest.raises(ReadOnlyZoneError, match=zone):
        paths.require_writable(paths.root / zone / "candidate.txt")


@pytest.mark.parametrize("zone", ["02_extracted", "03_parsed", "06_validation"])
def test_derived_zones_are_writable_targets(tmp_path: Path, zone: str) -> None:
    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=make_data_root(tmp_path))
    candidate = paths.root / zone / "run" / "artifact.json"

    assert paths.require_writable(candidate) == candidate.resolve()


def test_writable_target_rejects_path_traversal(tmp_path: Path) -> None:
    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=make_data_root(tmp_path))

    with pytest.raises(DataPathError, match="outside"):
        paths.require_writable(paths.root / "02_extracted" / ".." / ".." / "escape.txt")


def test_archive_is_not_a_routine_writable_zone(tmp_path: Path) -> None:
    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=make_data_root(tmp_path))

    with pytest.raises(ReadOnlyZoneError, match="99_archive"):
        paths.require_writable(paths.archive / "replacement.pdf")


def test_read_only_alias_to_writable_zone_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = DataPaths.resolve(repo_root=tmp_path / "repo", data_root=make_data_root(tmp_path))
    candidate = paths.external / "derived-alias" / "artifact.json"
    resolved_alias = paths.extracted / "artifact.json"
    original_resolve = Path.resolve

    def simulate_alias(path: Path, strict: bool = False) -> Path:
        if path == candidate:
            return resolved_alias
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", simulate_alias)

    with pytest.raises(ReadOnlyZoneError, match="00_external"):
        paths.require_writable(candidate)
