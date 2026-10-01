"""Internal admitted-context seam; a model or digest is not an admission.

Only reviewed admission sources construct this object. Python interpreter control
is outside the trusted-operator threat model; the seal is not a sandbox or PKI.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from .setup_authority import ActorBinding, SetupGrantV2
from .setup_dropbox import RealWorkOrder


class AdmissionSource(Protocol):
    def check(self, root: Path, checkpoint: Path) -> SetupGrantV2: ...
    def now(self) -> datetime: ...
    def actor(self, binding: ActorBinding) -> tuple[str, str]: ...
    def validate_store(self, root: Path, checkpoint: Path) -> None: ...
    def witness(self, order: RealWorkOrder) -> str: ...
    def concealment(self) -> bool: ...
    def link_coverage(self) -> Literal["not_established", "offline_complete"]: ...
    def component_store(self) -> Path: ...


_SEAL = object()


class AdmittedContext:
    def __init__(self, source: AdmissionSource, *, seal: object) -> None:
        if seal is not _SEAL:
            raise ValueError("independent source admission required")
        self._source = source
        self._seal = seal
        self._consumer: Callable[[RealWorkOrder], None] | None = None

    def check(self, root: Path, checkpoint: Path) -> SetupGrantV2:
        if self._seal is not _SEAL:
            raise ValueError("invalid admission")
        return self._source.check(root, checkpoint)

    def validate_store(self, root: Path, checkpoint: Path) -> None:
        self._source.validate_store(root, checkpoint)

    def now(self) -> datetime:
        return self._source.now()

    def actor(self, binding: ActorBinding) -> tuple[str, str]:
        return self._source.actor(binding)

    def witness(self, order: RealWorkOrder) -> str:
        return self._source.witness(order)

    def concealment(self) -> bool:
        return self._source.concealment()

    def link_coverage(self) -> Literal["not_established", "offline_complete"]:
        return self._source.link_coverage()

    def component_store(self) -> Path:
        return self._source.component_store()

    def attach(self, consumer: Callable[[RealWorkOrder], None]) -> None:
        if self._consumer is not None:
            raise ValueError("admission already has an active writer")
        self._consumer = consumer

    def detach(self) -> None:
        self._consumer = None

    def consume(self, order: RealWorkOrder) -> None:
        if self._consumer is None:
            raise ValueError("request not released by an active writer")
        self._consumer(order)


def _issue_context(source: AdmissionSource) -> AdmittedContext:  # pyright: ignore[reportUnusedFunction]
    """Internal loader seam, never selected by CLI/input/environment."""
    return AdmittedContext(source, seal=_SEAL)


def require_context(value: object) -> AdmittedContext:
    if type(value) is not AdmittedContext or value._seal is not _SEAL:  # pyright: ignore[reportPrivateUsage]
        raise ValueError("independent source admission required before sink access")
    return value
