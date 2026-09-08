"""Source-neutral structural compatibility; never infer a source relationship."""

from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES, AnnotationUnitType

ANNEX_FAMILIES = frozenset(
    {"protest_event", "violence_event", "dp_action", "alert", "agreement", "dialogue_event"}
)
# Report-local original fields only. Their presence must be independently declared
# and evidenced within this unit; no domain IDs or links are created by this policy.
# CaseDemand has no original fields; CaseProtestLink/CaseRelationship and
# MediationProcess require identity/link authority outside this execution contract.
CASE_SUBORDINATES = frozenset(
    {
        "case_name",
        "case_month",
        "location",
        "case_location",
        "actor",
        "case_actor",
        "demand",
        "case_reported_indicator",
        "protest_event",
        "violence_event",
        "dialogue_event",
        "mediation_observation",
        "agreement",
        "dp_action",
        "alert",
    }
)


def require_compatible(
    family: str, unit_type: AnnotationUnitType, *, subordinate: str | None = None
) -> None:
    """Shared resolved/unresolved/inventory gate, not evidence of actual source support."""
    if family not in BENCHMARK_OBJECT_TYPES:
        raise ValueError("unregistered object family")
    if family == "case_observation":
        if unit_type is not AnnotationUnitType.CASE_OBSERVATION:
            raise ValueError("a discovered case must retain case-observation semantics")
    elif unit_type not in {
        AnnotationUnitType.REPORT_ANNEX_EVENT,
        AnnotationUnitType.SOURCE_ONLY_OBJECT,
    }:
        raise ValueError("this proof supports only independent annex or source-only objects")
    if unit_type is AnnotationUnitType.REPORT_ANNEX_EVENT and family not in ANNEX_FAMILIES:
        raise ValueError("non-event objects cannot be represented as annex events")
    if subordinate is not None and (
        subordinate == family
        or family != "case_observation"
        or subordinate not in CASE_SUBORDINATES
    ):
        raise ValueError("incompatible subordinate family or duplicated base object")
