"""Read-only reconnaissance runner and safe temporary-output boundary."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from peru_conflicts.discovery.client import DiscoveryClientError, FetchedHtml, HtmlClient
from peru_conflicts.discovery.html import ParsedDiscoveryPage, parse_discovery_page
from peru_conflicts.discovery.models import ProvisionalDiscoveryRecord, UrlRole
from peru_conflicts.discovery.policy import PaginationStopReason, PaginationTracker, normalize_url
from peru_conflicts.discovery.receipts import (
    CorpusCompletenessStatus,
    LandingTraversalCounts,
    ReconnaissanceError,
    ReconnaissanceSummary,
    StopClass,
    SurfaceStopReason,
    SurfaceTraversalReceipt,
)


class OutputPathError(ValueError):
    """Raised before reconnaissance output could overlap protected storage."""


def validate_output_dir(
    output_dir: Path,
    *,
    data_root: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Validate a temporary output path before creating any directory or file."""

    target = output_dir.expanduser().resolve()
    configured_root = data_root
    if configured_root is None:
        value = os.environ.get("CONFLICT_DATA_ROOT", "").strip()
        configured_root = Path(value) if value else None
    if configured_root is not None:
        root = configured_root.expanduser().resolve()
        if target == root or target.is_relative_to(root):
            raise OutputPathError(f"Reconnaissance output overlaps CONFLICT_DATA_ROOT: {target}")
    if repo_root is not None:
        repository = repo_root.expanduser().resolve()
        cache = (repository / ".cache").resolve()
        if not target.is_relative_to(cache):
            raise OutputPathError(
                "Reconnaissance output must be under the repository's ignored .cache"
            )
    return target


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _record_json(record: ProvisionalDiscoveryRecord) -> str:
    return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _parse_page(
    fetched: FetchedHtml,
    *,
    role: UrlRole,
    captured_at: datetime,
) -> ParsedDiscoveryPage:
    return parse_discovery_page(
        fetched.body,
        page_url=fetched.observation.url,
        page_role=role,
        observation_id=fetched.observation.observation_id,
        captured_at=captured_at,
        observation=fetched.observation,
    )


def _stop_class(reason: PaginationStopReason, *, local_terminal: bool) -> StopClass:
    if reason is PaginationStopReason.ERROR:
        return StopClass.ERROR
    if local_terminal:
        return StopClass.LOCAL_TERMINAL
    return StopClass.SAFETY_STOP


def _default_utc_now() -> datetime:
    return datetime.now(UTC)


def run_reconnaissance(
    start_urls: tuple[str, ...],
    *,
    output_dir: Path,
    client: HtmlClient,
    surface_roles: Mapping[str, UrlRole] | None = None,
    pagination_contract_verified: Mapping[str, bool] | None = None,
    surface_pagination_modes: Mapping[str, str] | None = None,
    page_cap: int = 120,
    max_landing_pages: int = 0,
    captured_at: datetime | None = None,
    utc_clock: Callable[[], datetime] = _default_utc_now,
    repo_root: Path | None = None,
    data_root: Path | None = None,
) -> ReconnaissanceSummary:
    """Traverse approved HTML surfaces and write only ignored provisional receipts."""

    if repo_root is None:
        raise OutputPathError("run_reconnaissance requires an explicit repo_root cache boundary")
    if max_landing_pages < 0:
        raise ValueError("max_landing_pages must be non-negative")
    started_at = captured_at or utc_clock()
    capture_time = started_at
    safe_output = validate_output_dir(output_dir, data_root=data_root, repo_root=repo_root)
    safe_output.mkdir(parents=True, exist_ok=True)
    role_by_url = surface_roles or {}
    verified_by_url = pagination_contract_verified or {}
    pagination_mode_by_url = surface_pagination_modes or {}
    records: list[ProvisionalDiscoveryRecord] = []
    discovered_landing_urls: list[str] = []
    seen_landing_urls: set[str] = set()
    traversal_receipts: list[SurfaceTraversalReceipt] = []
    errors: list[ReconnaissanceError] = []
    visited_pages = 0

    for start_url in start_urls:
        normalized_start = normalize_url(start_url)
        role = role_by_url.get(start_url, role_by_url.get(normalized_start, UrlRole.CATALOGUE_PAGE))
        contract_verified = verified_by_url.get(
            start_url, verified_by_url.get(normalized_start, False)
        )
        pagination_mode = pagination_mode_by_url.get(
            start_url, pagination_mode_by_url.get(normalized_start, "numeric_or_rel_next")
        )
        if pagination_mode not in {"numeric_or_rel_next", "single_page"}:
            raise ValueError(f"unsupported pagination mode: {pagination_mode}")
        tracker = PaginationTracker(
            normalized_start,
            client.approved_hosts,
            page_cap=page_cap,
            pagination_contract_verified=contract_verified,
        )
        current_url: str | None = normalized_start
        surface_pages = 0
        while current_url is not None and tracker.stop_reason is None:
            if not tracker.visit(current_url):
                break
            surface_pages += 1
            visited_pages += 1
            observation_id = _stable_id("observation", current_url, capture_time.isoformat())
            try:
                fetched = client.fetch_html(
                    current_url,
                    role=role,
                    observation_id=observation_id,
                    captured_at=capture_time,
                )
                parsed = _parse_page(fetched, role=role, captured_at=capture_time)
            except (DiscoveryClientError, ValueError) as error:
                tracker.stop_error()
                errors.append(
                    ReconnaissanceError(
                        url=current_url,
                        error_type=type(error).__name__,
                        message=str(error) or repr(error),
                    )
                )
                break
            records.extend(parsed.records)
            for link in parsed.links:
                if link.role is UrlRole.LANDING_PAGE and link.url not in seen_landing_urls:
                    seen_landing_urls.add(link.url)
                    discovered_landing_urls.append(link.url)
            if pagination_mode == "single_page":
                tracker.stop_single_page()
                current_url = None
            else:
                current_url = tracker.propose_next(
                    parsed.next_url, base_url=fetched.observation.url
                )

        reason = tracker.stop_reason or PaginationStopReason.ERROR
        traversal_receipts.append(
            SurfaceTraversalReceipt(
                start_url=normalized_start,
                pages_visited=surface_pages,
                seen_urls=tracker.seen_urls,
                stop_reason=SurfaceStopReason(reason.value),
                stop_class=_stop_class(reason, local_terminal=tracker.reached_local_terminal),
                reached_local_terminal=tracker.reached_local_terminal,
                pagination_contract_verified=contract_verified,
                pagination_exhausted=tracker.pagination_exhausted,
            )
        )

    selected_landing_urls = discovered_landing_urls[:max_landing_pages]
    landing_fetched = 0
    landing_failed = 0
    for landing_url in selected_landing_urls:
        observation_id = _stable_id("observation", landing_url, capture_time.isoformat())
        try:
            fetched = client.fetch_html(
                landing_url,
                role=UrlRole.LANDING_PAGE,
                observation_id=observation_id,
                captured_at=capture_time,
            )
            parsed = _parse_page(fetched, role=UrlRole.LANDING_PAGE, captured_at=capture_time)
            records.extend(parsed.records)
            landing_fetched += 1
        except (DiscoveryClientError, ValueError) as error:
            landing_failed += 1
            errors.append(
                ReconnaissanceError(
                    url=landing_url,
                    error_type=type(error).__name__,
                    message=str(error) or repr(error),
                )
            )

    records_text = "".join(f"{_record_json(record)}\n" for record in records)
    requests_text = "".join(f"{receipt.model_dump_json()}\n" for receipt in client.request_receipts)
    completed_at = utc_clock()
    landing_skipped = len(discovered_landing_urls) - len(selected_landing_urls)
    summary = ReconnaissanceSummary(
        schema_version="0.3.0",
        run_id=_stable_id("reconnaissance", capture_time.isoformat(), *start_urls),
        started_at=started_at,
        completed_at=completed_at,
        start_urls=tuple(normalize_url(url) for url in start_urls),
        pages_visited=visited_pages,
        records_written=len(records),
        request_attempt_count=len(client.request_receipts),
        surface_traversals=tuple(traversal_receipts),
        errors=tuple(errors),
        landing_pages=LandingTraversalCounts(
            discovered=len(discovered_landing_urls),
            selected=len(selected_landing_urls),
            fetched=landing_fetched,
            failed=landing_failed,
            skipped=landing_skipped,
            cap_reached=landing_skipped > 0,
        ),
        all_surfaces_reached_local_terminal=bool(traversal_receipts)
        and all(item.reached_local_terminal for item in traversal_receipts),
        corpus_completeness_status=CorpusCompletenessStatus.NOT_ASSESSED,
        boundary="HTML/robots only; no PDF or binary body retrieval; no raw writes",
    )
    _atomic_write(safe_output / "records.jsonl", records_text)
    _atomic_write(safe_output / "requests.jsonl", requests_text)
    _atomic_write(
        safe_output / "summary.json",
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    return summary
