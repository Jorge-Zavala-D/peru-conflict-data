.PHONY: sync format lint typecheck test schemas schema-check guard quality

sync:
	uv sync --frozen --group dev

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

schemas:
	uv run python scripts/export_schemas.py

schema-check:
	uv run python scripts/export_schemas.py --check

guard:
	uv run python scripts/check_git_data_policy.py

quality: schema-check guard
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run pytest
