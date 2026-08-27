"""Safe resolution of the external research-data root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

EXPECTED_TOP_LEVEL = (
    "00_external",
    "01_raw",
    "02_extracted",
    "03_parsed",
    "04_linked",
    "05_database",
    "06_validation",
    "07_releases",
    "99_archive",
)
READ_ONLY_ZONES = frozenset({"00_external", "01_raw", "99_archive"})
WRITABLE_ZONES = frozenset(
    {"02_extracted", "03_parsed", "04_linked", "05_database", "06_validation", "07_releases"}
)


class DataPathError(ValueError):
    """Base error for an unsafe or incomplete external-data path."""


class MissingDataRootError(DataPathError):
    """Raised when no external data root was supplied."""


class ReadOnlyZoneError(DataPathError):
    """Raised when routine code attempts to target a protected zone."""


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Resolved, validated paths for the external storage hierarchy."""

    root: Path
    external: Path
    raw: Path
    extracted: Path
    parsed: Path
    linked: Path
    database: Path
    validation: Path
    releases: Path
    archive: Path

    @classmethod
    def resolve(cls, *, repo_root: Path, data_root: Path | None = None) -> DataPaths:
        raw_value = data_root or _root_from_environment()
        root = raw_value.expanduser().resolve()
        repository = repo_root.expanduser().resolve()

        if root == repository or root.is_relative_to(repository) or repository.is_relative_to(root):
            raise DataPathError(
                f"The Git repository and external data root must not overlap: {repository}, {root}"
            )
        if not root.is_dir():
            raise DataPathError(f"Data root does not exist or is not a directory: {root}")

        missing = [name for name in EXPECTED_TOP_LEVEL if not (root / name).is_dir()]
        if missing:
            raise DataPathError(f"Data root is missing expected directories: {', '.join(missing)}")

        return cls(
            root=root,
            external=root / "00_external",
            raw=root / "01_raw",
            extracted=root / "02_extracted",
            parsed=root / "03_parsed",
            linked=root / "04_linked",
            database=root / "05_database",
            validation=root / "06_validation",
            releases=root / "07_releases",
            archive=root / "99_archive",
        )

    def require_writable(self, candidate: Path) -> Path:
        """Return a safe derived target or raise before any filesystem mutation."""

        logical = Path(os.path.abspath(candidate.expanduser()))
        if not logical.is_relative_to(self.root):
            raise DataPathError(f"Write target is outside the external data root: {logical}")

        logical_relative = logical.relative_to(self.root)
        if not logical_relative.parts:
            raise ReadOnlyZoneError(f"The data-root directory is not a writable target: {logical}")
        logical_zone = logical_relative.parts[0]
        if logical_zone in READ_ONLY_ZONES or logical_zone not in WRITABLE_ZONES:
            raise ReadOnlyZoneError(f"Routine writes are forbidden in {logical_zone}: {logical}")

        resolved = logical.resolve()
        if not resolved.is_relative_to(self.root):
            raise DataPathError(f"Write target is outside the external data root: {resolved}")

        relative = resolved.relative_to(self.root)
        if not relative.parts:
            raise ReadOnlyZoneError(f"The data-root directory is not a writable target: {resolved}")
        zone = relative.parts[0]
        if zone in READ_ONLY_ZONES or zone not in WRITABLE_ZONES:
            raise ReadOnlyZoneError(f"Routine writes are forbidden in {zone}: {resolved}")
        return resolved


def _root_from_environment() -> Path:
    value = os.environ.get("CONFLICT_DATA_ROOT", "").strip()
    if not value:
        raise MissingDataRootError("CONFLICT_DATA_ROOT is required when data_root is not supplied")
    return Path(value)
