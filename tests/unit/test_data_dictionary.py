from __future__ import annotations

from pathlib import Path

from peru_conflicts.models import MODEL_REGISTRY


def test_data_dictionary_mentions_every_registered_model_and_field() -> None:
    repo_root = Path(__file__).parents[2]
    dictionary = (repo_root / "docs" / "08_data_dictionary.md").read_text(encoding="utf-8")

    for name, model in MODEL_REGISTRY.items():
        assert f"`{name}`" in dictionary
        for field_name in model.model_fields:
            assert f"`{field_name}`" in dictionary, f"missing dictionary field: {name}.{field_name}"
