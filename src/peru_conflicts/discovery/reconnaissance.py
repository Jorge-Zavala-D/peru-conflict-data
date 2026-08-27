"""Read-only reconnaissance runner and safe temporary-output boundary."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from peru_conflicts.discovery.client import DiscoveryClientError, FetchedHtml, HtmlClient
from peru_conflicts.discovery.html import ParsedDiscoveryPage, parse_discovery_page
from peru_conflicts.discovery.models import ProvisionalDiscoveryRecord, UrlRole
from peru_conflicts.discovery.policy import PaginationTracker, normalize_url


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
        cache = repository / ".cache"
        if target.is_relative_to(repository) and not target.is_relative_to(cache):
            raise OutputPathError(
                "Reconnaissance output inside the Git repository must be under ignored .cache"
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


def run_reconnaissance(
    start_urls: tuple[str, ...],
    *,
    output_dir: Path,
    client: HtmlClient,
    surface_roles: Mapping[str, UrlRole] | None = None,
    page_cap: int = 120,
    max_landing_pages: int = 0,
    captured_at: datetime | None = None,
    repo_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, object]:
    """Traverse approved HTML surfaces and write only ignored provisional receipts."""

    if max_landing_pages < 0:
        raise ValueError("max_landing_pages must be non-negative")
    capture_time = captured_at or datetime.now(UTC)
    safe_output = validate_output_dir(output_dir, data_root=data_root, repo_root=repo_root)
    safe_output.mkdir(parents=True, exist_ok=True)
    role_by_url = surface_roles or {}
    records: list[ProvisionalDiscoveryRecord] = []
    discovered_landing_urls: list[str] = []
    seen_landing_urls: set[str] = set()
    stop_receipts: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    visited_pages = 0

    for start_url in start_urls:
        normalized_start = normalize_url(start_url)
        role = role_by_url.get(start_url, role_by_url.get(normalized_start, UrlRole.CATALOGUE_PAGE))
        tracker = PaginationTracker(normalized_start, client.approved_hosts, page_cap=page_cap)
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
                errors.append({"url": current_url, "error": str(error)})
                break
            records.extend(parsed.records)
            for link in parsed.links:
                if link.role is UrlRole.LANDING_PAGE and link.url not in seen_landing_urls:
                    seen_landing_urls.add(link.url)
                    discovered_landing_urls.append(link.url)
            next_url = tracker.propose_next(parsed.next_url, base_url=fetched.observation.url)
            current_url = next_url
        stop_receipts.append(
            {
                "start_url": normalized_start,
                "pages_visited": surface_pages,
                "seen_urls": tracker.seen_urls,
                "stop_reason": tracker.stop_reason.value if tracker.stop_reason else "error",
                "complete": tracker.complete,
            }
        )

    for landing_url in discovered_landing_urls[:max_landing_pages]:
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
        except (DiscoveryClientError, ValueError) as error:
            errors.append({"url": landing_url, "error": str(error)})

    records_text = "".join(f"{_record_json(record)}\n" for record in records)
    requests_text = "".join(
        f"{json.dumps(asdict(receipt), ensure_ascii=False, sort_keys=True, default=str)}\n"
        for receipt in client.request_receipts
    )
    summary: dict[str, object] = {
        "captured_at": capture_time.isoformat(),
        "start_urls": [normalize_url(url) for url in start_urls],
        "pages_visited": visited_pages,
        "records_written": len(records),
        "request_count": len(client.request_receipts),
        "stop_receipts": stop_receipts,
        "stop_reasons": [item["stop_reason"] for item in stop_receipts],
        "errors": errors,
        "complete": bool(stop_receipts) and all(bool(item["complete"]) for item in stop_receipts),
        "boundary": "HTML/robots only; no PDF or binary body retrieval; no raw writes",
    }
    _atomic_write(safe_output / "records.jsonl", records_text)
    _atomic_write(safe_output / "requests.jsonl", requests_text)
    _atomic_write(
        safe_output / "summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return summary
