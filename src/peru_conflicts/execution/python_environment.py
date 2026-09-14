"""Strict rehearsal environment manifest; independent provisioning is not implemented."""

from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from peru_conflicts.models.common import Sha256, StrictModel

from .python_environment_policy import capture_document, validate_document


class PythonEnvironmentTrustManifest(StrictModel):
    policy: Literal["m2-python-environment-rehearsal-v1"]
    production_approved: Literal[False]
    external_trust_boundary: str
    exclusions: tuple[str, ...]
    identity: dict[str, str]
    stdlib_path: str
    interpreter_path: str
    interpreter_sha256: Sha256
    dependency_sha256: Sha256
    file_hashes: dict[str, Sha256]
    symlinks: dict[str, str]
    python_environment_sha256: Sha256

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        validate_document(self.model_dump(mode="json"))
        return self


def capture_rehearsal_environment(
    dependency_sha256: str,
    *,
    root: Path | None = None,
    stdlib: Path | None = None,
    executable: Path | None = None,
    system: str | None = None,
) -> PythonEnvironmentTrustManifest:
    """Rehearsal evidence only; never independently authenticates the running Python."""
    from .python_environment_policy import json_bytes

    return PythonEnvironmentTrustManifest.model_validate_json(
        json_bytes(
            capture_document(
                dependency_sha256,
                root=root,
                stdlib=stdlib,
                executable=executable,
                system=system,
            )
        )
    )
