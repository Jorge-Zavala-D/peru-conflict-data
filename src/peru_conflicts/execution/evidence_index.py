"""Closed metadata-only audit index. Not a scientific/benchmark schema or payload."""

from typing import Annotated, Literal

import yaml
from pydantic import Field, StringConstraints

from peru_conflicts.models.common import Sha256, StrictModel

GitSha = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Count = Annotated[int, Field(ge=0)]


class AuditArtifact(StrictModel):
    bytes: Count
    sha256: Sha256


class AuditSource(StrictModel):
    report_number: Annotated[int, Field(ge=260, le=269)]
    expected_sha256: Sha256
    observed_sha256: Sha256
    expected_pages: Count
    observed_pages: Count
    association_status: Literal["explicit_report_identity", "unresolved_opaque_filename"]


class AuditPackage(StrictModel):
    role: Literal["annotator-a", "annotator-b"]
    manifest_sha256: Sha256
    reports: Count
    pages: Count
    files: Count
    blank_forms: Count
    answers: Literal[0]
    machine_suggestions: Literal[0]
    partition_labels: Literal[0]
    parser_outputs: Literal[0]
    gold: Literal[0]


class AuditExtractor(StrictModel):
    executable: Literal["pdftotext.exe", "pdfinfo.exe"]
    version: Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
    sha256: Sha256


class ReadinessEvidenceIndex(StrictModel):
    kind: Literal["SOURCE_NEUTRAL_READINESS_EVIDENCE_NOT_AUTHORITY"]
    provenance_scope: Literal["reviewed_parent_plus_precommit_content_pins_no_circular_head"]
    base_sha: GitSha
    base_tree: GitSha
    reviewed_implementation_sha: GitSha
    reviewed_implementation_tree: GitSha
    benchmark_digest: Sha256
    scientific_digest: Sha256
    m2_01_approval_sha256: Sha256
    m2_02_approval_sha256: Sha256
    evaluator_sha256: Sha256
    m3_gate_sha256: Sha256
    m3_policy_status: Literal["owner_review_draft"]
    m3_owner_approved: Literal[False]
    owner_readiness_approved: Literal[False]
    source_custody: list[AuditSource]
    extractors: list[AuditExtractor]
    extraction_flags: Literal["-f N -l N -raw|-layout -enc UTF-8 -eol unix -nopgbrk snapshot.pdf -"]
    comparison_method: Literal[
        "per_page_bytes_codepoints_lines_max_line_repeated_lines_multispace_no_semantics"
    ]
    recommendation: Literal["raw_pending_owner_review"]
    comparison: dict[
        Literal["raw", "layout"],
        dict[
            Literal[
                "bytes",
                "lines",
                "max_line_codepoints",
                "duplicate_nonempty_lines",
                "multi_space_lines",
            ],
            Count,
        ],
    ]
    pages: Count
    reference_bytes: Count
    first_manifest_sha256: Sha256
    second_manifest_sha256: Sha256
    repeat_identical: Literal[True]
    ocr: Literal[False]
    packages: list[AuditPackage]
    artifacts: dict[
        Literal[
            "original_packet",
            "original_matrix",
            "original_principal_review",
            "original_synthetic",
            "hardening_packet",
            "hardening_matrix",
            "hardening_synthetic",
            "hardening_principal_precommit",
        ],
        AuditArtifact,
    ]
    synthetic_scenarios: list[
        Literal[
            "eligibility_role_person_binding",
            "attestation_mutation",
            "trusted_replacement_rejection",
            "manifest_reference_role_mutations",
            "resolved_unresolved_compatibility",
            "subordinate_inventory_compatibility",
            "literal_strings",
            "launch_disabled",
        ]
    ]
    synthetic_exact_matches: Count
    synthetic_boundary_disagreements: Count
    synthetic_a_only: Count
    synthetic_b_only: Count
    supersession_preserved: Literal[True]
    adjudication: Literal[False]
    human_gold: Literal[False]
    dropbox_directories: Count
    dropbox_files: Count
    dropbox_bytes: Count
    m1_files: Count
    m1_bytes: Count
    m2_external_root_exists: Literal[False]
    dropbox_writes: Literal[0]


def evidence_index_bytes(index: ReadinessEvidenceIndex) -> bytes:
    return yaml.safe_dump(
        index.model_dump(mode="json"), sort_keys=False, allow_unicode=False
    ).encode("utf-8")


def validate_evidence_index(data: bytes) -> ReadinessEvidenceIndex:
    try:
        index = ReadinessEvidenceIndex.model_validate(yaml.safe_load(data))
    except yaml.YAMLError as error:
        raise ValueError("invalid evidence metadata encoding") from error
    if evidence_index_bytes(index) != data:
        raise ValueError("evidence index must be canonical metadata only, without comments/payload")
    return index
