from __future__ import annotations

import io
import json
import logging

from peru_conflicts.json_logging import JsonLineFormatter, configure_json_logger


def test_json_line_formatter_emits_one_structured_object() -> None:
    stream = io.StringIO()
    logger = configure_json_logger("test-json-logger", stream=stream)

    logger.info("inventory started", extra={"event": "run_started", "run_id": "run_1"})

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "INFO"
    assert payload["message"] == "inventory started"
    assert payload["event"] == "run_started"
    assert payload["run_id"] == "run_1"
    assert payload["timestamp"].endswith("Z")


def test_json_line_formatter_escapes_embedded_newlines() -> None:
    formatter = JsonLineFormatter()
    record = logging.LogRecord(
        "test", logging.WARNING, __file__, 10, "line one\nline two", (), None
    )

    rendered = formatter.format(record)

    assert len(rendered.splitlines()) == 1
    assert json.loads(rendered)["message"] == "line one\nline two"


def test_json_line_formatter_never_emits_nonstandard_nan_literal() -> None:
    formatter = JsonLineFormatter()
    record = logging.LogRecord("test", logging.INFO, __file__, 10, "metric", (), None)
    record.metric = float("nan")

    rendered = formatter.format(record)

    assert "NaN" not in rendered or '"NaN"' in rendered
    assert json.loads(
        rendered, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
    )
