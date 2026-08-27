"""Reviewed, non-executable acquisition recipe for the future 260-269 pilot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal, Self, cast
from urllib.parse import urlsplit

import yaml
from pydantic import Field, field_validator, model_validator

from peru_conflicts.discovery.policy import classify_host
from peru_conflicts.discovery.settings import AUTHORITATIVE_HOSTS
from peru_conflicts.models.common import Identifier, ReferencePeriod, Sha256, StrictModel

REVIEWED_TARGET_SET_SHA256 = "721cf0e307c122facad5fdd64228b5a9c3789cc159b8a77e3b0e1536677594e1"
REVIEWED_PLAN_FILE_SHA256 = "59480d3845ba3fb2ce14f0d1fce01b93472ca1c86e189a4a67d6fa9d9599a6b7"


class PilotLimits(StrictModel):
    """Hard future-acquisition envelope; every transport attempt consumes the budget."""

    max_reports: Literal[10]
    max_urls: Literal[20]
    concurrency: Literal[1]
    delay_seconds: float = Field(ge=2.0, le=2.0)
    retry_cap: Literal[2]
    timeout_seconds: Literal[30]
    max_redirects_per_url: Literal[5]
    max_total_attempts: Literal[60]
    attempts_include: tuple[Literal["robots", "initial_requests", "redirect_hops", "retries"], ...]
    global_budget_behavior: Literal["stop_before_request_when_budget_exhausted"]
    per_file_min_bytes: Literal[1024]
    per_file_max_bytes: Literal[50_000_000]
    total_download_max_bytes: Literal[500_000_000]

    @field_validator("attempts_include", mode="before")
    @classmethod
    def freeze_attempt_categories(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def close_attempt_bound(self) -> Self:
        expected = ("robots", "initial_requests", "redirect_hops", "retries")
        if self.attempts_include != expected:
            raise ValueError("attempt budget must include robots, requests, redirects, and retries")
        return self


class PilotDryRun(StrictModel):
    """The only currently authorized use of the future-acquisition recipe."""

    network_requests: Literal[0]
    dropbox_writes: Literal[0]
    behavior: Literal["validate_and_print_plan_only"]


class PilotPromotionPolicy(StrictModel):
    """Fail-closed validation and future same-filesystem promotion semantics."""

    temporary_location: Literal["system_temp/peru-conflict-data/m1-03-pilot-260-269"]
    same_filesystem_staging_location: Literal[
        "conflict_data_root/01_raw/.staging/m1-03-pilot-260-269"
    ]
    staging_behavior: Literal["copy_stream_rehash_then_atomic_rename"]
    pre_network_validation_order: tuple[Identifier, ...]
    response_validation_order: tuple[Identifier, ...]
    disposition_order: tuple[Identifier, ...]
    different_from_existing_action: Literal["stop_for_review_before_raw_promotion"]
    identical_to_existing_action: Literal["record_observation_no_duplicate_raw_file"]
    identical_bytes_multiple_urls_action: Literal["preserve_all_url_observations_one_byte_object"]
    failure_action: Literal["abandon_promotion_preserve_receipt_then_remove_temp"]
    atomic_promotion_required: Literal[True]

    @field_validator(
        "pre_network_validation_order",
        "response_validation_order",
        "disposition_order",
        mode="before",
    )
    @classmethod
    def freeze_validation_orders(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_complete_orders(self) -> Self:
        if self.pre_network_validation_order != (
            "authorization_status",
            "plan_schema_and_digest",
            "approved_hosts",
            "existing_path_size_sha256",
        ):
            raise ValueError("pilot pre-network validation order must remain complete and ordered")
        if self.response_validation_order != (
            "approved_host",
            "robots_allowed",
            "http_status_2xx",
            "content_type_pdf",
            "reasonable_size",
            "pdf_magic_signature",
            "sha256",
        ):
            raise ValueError("pilot response validation order must remain complete and ordered")
        if self.disposition_order != (
            "compare_to_existing_sha256",
            "stop_or_deduplicate",
            "same_filesystem_rehash",
            "atomic_rename",
        ):
            raise ValueError("pilot disposition order must remain complete and ordered")
        return self


class PilotTarget(StrictModel):
    """One pinned public URL pair and its existing local benchmark receipt."""

    report_number: int = Field(ge=260, le=269)
    candidate_reference_period: ReferencePeriod
    publication_date_original: Identifier
    landing_page_url: Identifier
    direct_download_url: Identifier
    association_status: Literal["visibly_associated", "unresolved_association"]
    uncertainty_codes: tuple[Literal["opaque_filename", "unresolved_association"], ...] = ()
    uncertainty_note: str | None = None
    existing_local_relative_path: Identifier
    existing_local_byte_count: int = Field(ge=1)
    existing_local_sha256: Sha256
    remote_hash_status: Literal["unknown_until_authorized_fetch"]
    expected_remote_sha256: None = None

    @field_validator("uncertainty_codes", mode="before")
    @classmethod
    def freeze_uncertainty_codes(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @field_validator("expected_remote_sha256", mode="before")
    @classmethod
    def prohibit_remote_hash_assumption(cls, value: object) -> object:
        if value is not None:
            raise ValueError(
                "expected remote SHA-256 must remain unknown before authorized retrieval"
            )
        return value

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        for url in (self.landing_page_url, self.direct_download_url):
            if urlsplit(url).scheme != "https":
                raise ValueError("every pilot URL must use HTTPS")
        if not urlsplit(self.landing_page_url).path.startswith("/documentos/"):
            raise ValueError("landing-page URL must use the reviewed /documentos/ path family")
        if not urlsplit(self.direct_download_url).path.lower().endswith(".pdf"):
            raise ValueError("direct-download URL must visibly identify a PDF path")

        required_uncertainty = {
            "opaque_filename",
            "unresolved_association",
        }
        observed_uncertainty = set(self.uncertainty_codes)
        if self.association_status == "unresolved_association":
            if observed_uncertainty != required_uncertainty or not self.uncertainty_note:
                raise ValueError(
                    "an unresolved opaque association requires both uncertainty codes and a note"
                )
        elif observed_uncertainty or self.uncertainty_note is not None:
            raise ValueError("a visibly associated target cannot claim unresolved uncertainty")

        path = PurePosixPath(self.existing_local_relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parts[:2]
            != (
                "01_raw",
                "reports",
            )
        ):
            raise ValueError("existing local path must be a safe 01_raw/reports relative path")
        return self


class PilotAcquisitionPlan(StrictModel):
    """Pinned recipe that describes, but cannot authorize, the future pilot."""

    schema_version: Literal["0.3.0"]
    plan_id: Literal["m1-03-reports-260-269-v1"]
    authorization_status: Literal["not_authorized"]
    purpose: Identifier
    approved_hosts: tuple[Identifier, ...]
    limits: PilotLimits
    dry_run: PilotDryRun
    baseline_receipt_path: Literal["docs/source_integrity_receipt_m1_02.md"]
    baseline_receipt_git_commit: Literal["85a91ebba407610931e7e37b21b0ddddc15edbd1"]
    baseline_receipt_sha256: Literal[
        "cfab73b44aded55a803e8bda000fd2e67ae4b7eca904769f73e96b317e615837"
    ]
    promotion_policy: PilotPromotionPolicy
    targets: tuple[PilotTarget, ...]

    @field_validator("approved_hosts", "targets", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_reviewed_scope(self) -> Self:
        if self.approved_hosts != AUTHORITATIVE_HOSTS:
            raise ValueError("approved_hosts must be the exact reviewed authoritative hosts")
        if [target.report_number for target in self.targets] != list(range(260, 270)):
            raise ValueError("pilot must contain exactly reports 260 through 269 in order")

        approved = frozenset(AUTHORITATIVE_HOSTS)
        landing_urls: set[str] = set()
        download_urls: set[str] = set()
        for target in self.targets:
            for url in (target.landing_page_url, target.direct_download_url):
                if classify_host(url, approved) != "authoritative":
                    raise ValueError("every pilot URL must use an approved authoritative host")
            if (
                target.landing_page_url in landing_urls
                or target.direct_download_url in download_urls
            ):
                raise ValueError("pilot landing and direct-download URLs must be unique by role")
            landing_urls.add(target.landing_page_url)
            download_urls.add(target.direct_download_url)

        rendered_targets = json.dumps(
            [target.model_dump(mode="json") for target in self.targets],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        fingerprint = hashlib.sha256(rendered_targets).hexdigest()
        if fingerprint != REVIEWED_TARGET_SET_SHA256:
            raise ValueError("pilot records do not match the reviewed target-set fingerprint")
        return self


def load_pilot_acquisition_plan(path: Path) -> PilotAcquisitionPlan:
    """Load the reviewed Git-safe recipe without network I/O or authorization side effects."""

    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REVIEWED_PLAN_FILE_SHA256:
        raise ValueError("pilot file does not match the reviewed plan-file fingerprint")
    payload = yaml.safe_load(raw.decode("utf-8"))
    return PilotAcquisitionPlan.model_validate(payload)
