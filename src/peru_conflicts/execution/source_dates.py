"""Owner-authorized source-date form validation; never date parsing or inference."""

import json

from peru_conflicts.benchmark.models import AnnotationState, FieldAnnotation


def validate_date_pair(values: dict[str, FieldAnnotation], family: str) -> None:
    prefix = {"dp_action": "action", "alert": "alert"}.get(family)
    if prefix is None:
        return
    date_slot = values.get(f"{family}.{prefix}_date_original")
    precision_slot = values.get(f"{family}.{prefix}_date_precision_original")
    for item in (date_slot, precision_slot):
        if item is not None and item.state is AnnotationState.EXPLICIT_ZERO:
            raise ValueError("no approved explicit-zero date construct")
        if item is not None and item.state is AnnotationState.OBSERVED:
            value = json.loads(item.raw_value_json or "null")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("source date/precision must be a nonempty exact string")
    if (
        date_slot is not None
        and precision_slot is not None
        and precision_slot.state is AnnotationState.OBSERVED
        and date_slot.state is not AnnotationState.OBSERVED
    ):
        raise ValueError("observed precision requires an observed source date")
