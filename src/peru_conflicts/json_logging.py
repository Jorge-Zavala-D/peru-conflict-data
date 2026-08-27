"""Structured JSON Lines logging for auditable pipeline runs."""

from __future__ import annotations

import json
import logging
import math
import sys
from datetime import UTC, datetime
from typing import TextIO, cast

_STANDARD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonLineFormatter(logging.Formatter):
    """Render one valid JSON object for each log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            default=str,
            allow_nan=False,
            separators=(",", ":"),
        )


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return {str(key): _json_safe(item) for key, item in mapping.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in cast(tuple[object, ...], value)]
    return value


def configure_json_logger(
    name: str,
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Create an isolated JSON logger for a caller-owned stream."""

    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    return logger
