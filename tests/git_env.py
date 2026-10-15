"""Isolate explicitly foreign synthetic Git operations from their caller."""

from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager

import pytest

_LOCAL_GIT_NAMES = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_INTERNAL_SUPER_PREFIX",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_TEMPLATE_DIR",
        "GIT_WORK_TREE",
    }
)
_SYNTHETIC_CONFIG = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_COUNT": "0",
}


def _local_git_name(name: str) -> bool:
    upper = name.upper()
    return upper in _LOCAL_GIT_NAMES or upper.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))


def foreign_git_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy OS/runtime settings, then apply only controlled foreign Git configuration."""
    environment = {name: value for name, value in os.environ.items() if not _local_git_name(name)}
    environment.update(_SYNTHETIC_CONFIG)
    if overrides is not None:
        environment.update(overrides)
    return environment


@contextmanager
def foreign_git_context() -> Generator[None, None, None]:
    """Scope existing in-process readers to their synthetic repository, not the real caller."""
    with pytest.MonkeyPatch.context() as patch:
        for name in tuple(os.environ):
            if _local_git_name(name):
                patch.delenv(name, raising=False)
        for name, value in _SYNTHETIC_CONFIG.items():
            patch.setenv(name, value)
        yield
