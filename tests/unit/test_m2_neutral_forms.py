"""Shared neutral validation against invented, independently certified forms."""

import importlib
import importlib.util
import json
from collections.abc import Callable
from hashlib import sha256
from typing import Any, cast

import pytest
from test_m2_annotation import blank, complete, discovered, form, populated, validate

from peru_conflicts.benchmark.models import PartitionRole
from peru_conflicts.execution import annotation
from peru_conflicts.execution.packages import verify_package
from peru_conflicts.hashing import canonical_json_bytes


def neutral_validator() -> Callable[..., Any]:
    name = "peru_conflicts.execution.neutral_forms"
    assert importlib.util.find_spec(name) is not None, "neutral validation entry point is missing"
    module = importlib.import_module(name)
    assert callable(getattr(module, "validate_neutral_forms", None))
    return module.validate_neutral_forms


def neutral(package: dict[str, bytes], **kwargs: Any) -> Any:
    return neutral_validator()(
        package, expected_package=verify_package(package, allow_drafts=True), **kwargs
    )


def assert_neutral_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in cast(dict[str, object], value).items():
            assert "partition" not in key and "submission" not in key
            assert_neutral_keys(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            assert_neutral_keys(item)


def test_blank_neutral_draft_has_no_routing_or_submissions() -> None:
    draft = neutral(blank())
    assert draft.complete is False
    assert draft.discoveries == ()
    assert draft.records == ()
    assert_neutral_keys(json.loads(draft.model_dump_json()))


def test_complete_zero_discovery_inspection_is_accepted() -> None:
    package = blank()
    complete(package)
    draft = neutral(package, require_complete=True)
    assert draft.complete is True
    assert draft.records == ()
    assert len(draft.inspections) == 11


def test_discovered_case_retains_explicit_unresolved_source_values() -> None:
    package = populated()
    slots = annotation.rows(package, "annotations.csv")
    slots[0].update(state="source_ambiguous", comment="Invented source contradiction")
    package["annotations.csv"] = form("annotations.csv", slots)
    draft = neutral(package, require_complete=True)
    assert draft.complete is True
    assert len(draft.records) == 1
    record = draft.records[0]
    assert record.discovery_id == "local-1"
    assert len(record.object_inventory) == 2
    assert record.annotations[0].state.value == "source_ambiguous"
    assert record.annotations[0].raw_value_json is None
    assert record.annotations[0].uncertainty_comment == "Invented source contradiction"
    assert_neutral_keys(json.loads(draft.model_dump_json()))


@pytest.mark.parametrize("fault", ["columns", "evidence", "inspection", "state", "slot"])
def test_neutral_and_coordinator_reject_same_invalid_forms(fault: str) -> None:
    package = populated()
    if fault == "columns":
        package["annotations.csv"] = b"unknown\nvalue\n"
    elif fault == "evidence":
        package["evidence.csv"] = form("evidence.csv", [])
    elif fault == "inspection":
        package["inspection.csv"] = form("inspection.csv", [])
    else:
        slots = annotation.rows(package, "annotations.csv")
        if fault == "state":
            slots[0].update(state="", comment="Content without an explicit state")
        else:
            slots.append(dict(slots[0]))
        package["annotations.csv"] = form("annotations.csv", slots)
    validator = neutral_validator()
    expected = verify_package(populated(), allow_drafts=True)
    with pytest.raises(ValueError) as coordinator_error:
        annotation.validate_forms(
            package,
            {260: PartitionRole.PROTOCOL_PILOT},
            expected_package=expected,
            require_complete=True,
        )
    with pytest.raises(ValueError) as neutral_error:
        validator(package, expected_package=expected, require_complete=True)
    assert str(neutral_error.value) == str(coordinator_error.value)


def test_unresolved_discovery_is_retained_without_inventing_an_object() -> None:
    package = discovered()
    rows = annotation.rows(package, "discoveries.csv")
    rows[0].update(unresolved="true", note="Invented ambiguous boundary")
    package["discoveries.csv"] = form("discoveries.csv", rows)
    complete(package, 1)
    draft = neutral(package, require_complete=True)
    assert draft.complete is True
    assert draft.discoveries == ()
    assert draft.records == ()
    assert draft.unresolved[0]["note"] == "Invented ambiguous boundary"


@pytest.mark.parametrize(
    "kind,expected_digest",
    [
        ("blank", "5d00867af91037d87925cfb340bd5d09b07e39f107ea85921081c6ac77a2055f"),
        ("zero", "50529db672cee4c562eb8c86e3cd4150de79b23f333c66611281394d40b19373"),
        ("populated", "1c80b8660c99eefdcd271a475ab42b74381dae375549494595e22aeaa482c24a"),
    ],
)
def test_coordinator_payload_matches_pre_refactor_baseline(kind: str, expected_digest: str) -> None:
    package = populated() if kind == "populated" else blank()
    if kind == "zero":
        complete(package)
    draft = validate(package, {260: PartitionRole.PROTOCOL_PILOT}, require_complete=kind != "blank")
    assert (
        sha256(canonical_json_bytes(draft.model_dump(mode="json"))).hexdigest() == expected_digest
    )


def test_pinned_field_registry_supplies_neutral_slots() -> None:
    package = populated()
    registry = {
        family: annotation.required_fields(family) for family in ("case_observation", "case_name")
    }
    draft = neutral(package, require_complete=True, required_field_registry=registry)
    assert draft.complete is True
    assert {item.domain_object_type for item in draft.records[0].object_inventory} == {
        "case_observation",
        "case_name",
    }
    with pytest.raises(ValueError, match="registry"):
        neutral(package, required_field_registry={})
