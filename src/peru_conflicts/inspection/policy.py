"""Fixed declarative restrictions shared by two independent projection boundaries."""

VERSION = "DOCUMENTARY_SQLITE_PROJECTION_V001"
SCOPE = (
    "Only selected frozen documentary records; no full-report completeness "
    "certification; rows are not canonical cases/events."
)
PERMISSIONS = {
    "inspection": True,
    "normalization": False,
    "automatic_dispatch": False,
    "scientific_acceptance": False,
    "benchmark_scoring": False,
}
PROFILE_ROLES = {
    "SOURCE_BOUND_CONTEXT_ATTACHMENT_V001": {"category", "count", "percentage"},
    "SOURCE_BOUND_CONTEXT_ATTACHMENT_V002": {
        "place_text",
        "case_description",
        "published_situation",
    },
}
QUALIFIER_TARGETS: dict[str, dict[str, tuple[str, str | None]]] = {
    "SOURCE_BOUND_CONTEXT_ATTACHMENT_V001": {
        "subject": ("table_proposal", None),
        "reporting_period": ("table_proposal", None),
        "geographic_breakdown": ("reported_organization", None),
        "count_unit": ("column", "count"),
        "percentage_sign": ("column", "percentage"),
    },
    "SOURCE_BOUND_CONTEXT_ATTACHMENT_V002": {
        "introductory_scope": ("table_proposal", None),
        "documentary_scope": ("table_proposal", None),
    },
}
