"""Local human-operability helpers for non-launched readiness packages."""

from __future__ import annotations

import argparse
import csv
import io
import sys
from contextlib import ExitStack
from pathlib import Path

from peru_conflicts.acquisition.fs_safety import DirectoryLease, DirectoryLeaseError
from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES, PartitionRole
from peru_conflicts.hashing import canonical_json_bytes

from .annotation import empty_slots, validate_forms
from .coordination import PackageIssuanceReceipt, verify_trusted_package
from .packages import FORM_HEADERS, require_readiness_root, verify_package
from .references import reference_text, select_position, sha256


def load_package(
    root: Path, expected_issuance: PackageIssuanceReceipt | None = None
) -> dict[str, bytes]:
    if expected_issuance is None:
        raise ValueError("trusted coordinator issuance identity is required")
    require_readiness_root(root)
    files: dict[str, bytes] = {}
    with DirectoryLease.acquire(root) as lease:
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or path.absolute() != path.resolve():
                raise ValueError("package cannot contain aliased entries")
            if path.is_dir():
                continue
            relative = path.relative_to(root)
            with ExitStack() as stack:
                parent = lease
                for part in relative.parts[:-1]:
                    parent = stack.enter_context(parent.acquire_child(part))
                with parent.open_child_read(relative.name) as stream:
                    files[relative.as_posix()] = stream.read()
        lease.require_bound()
    verify_trusted_package(files, expected_issuance, allow_drafts=True)
    return files


def csv_bytes(name: str, values: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FORM_HEADERS[name].split(","), lineterminator="\n")
    writer.writeheader()
    writer.writerows(values)
    return output.getvalue().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("page", "position", "slots", "inspection-template", "validate"):
        command = commands.add_parser(name)
        command.add_argument("package", type=Path)
        command.add_argument("--issuance", type=Path, required=True)
        command.add_argument("--issuance-sha256", required=True)
        if name in {"page", "position"}:
            command.add_argument("--report", required=True, type=int)
            command.add_argument("--page", required=True, type=int)
        if name == "position":
            command.add_argument("--line", required=True, type=int)
            command.add_argument("--column", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        receipt_bytes = args.issuance.read_bytes()
        if sha256(receipt_bytes) != args.issuance_sha256:
            raise ValueError("issuance receipt differs from trusted coordinator pin")
        receipt = PackageIssuanceReceipt.model_validate_json(receipt_bytes)
        files = load_package(args.package, receipt)
        manifest = verify_package(files, allow_drafts=True)
        if args.command in {"page", "position"}:
            key = f"references/{args.report}/{args.page:04d}.txt"
            if key not in files:
                raise ValueError("report/page is outside this package")
            text = reference_text(files[key])
            if args.command == "page":
                for number, line in enumerate(text.split("\n"), start=1):
                    print(f"{number:5d} | {line}")
            else:
                offset = select_position(files[key], line=args.line, column=args.column)
                print(
                    canonical_json_bytes(
                        {
                            "report": args.report,
                            "page": args.page,
                            "offset": offset,
                            "reference_sha256": sha256(files[key]),
                            "context": text[max(0, offset - 30) : offset + 50],
                            "notice": (
                                "Verify this human selection; not a scientific start recommendation"
                            ),
                        }
                    ).decode()
                )
        elif args.command == "slots":
            print(csv_bytes("annotations.csv", empty_slots(files)).decode(), end="")
        elif args.command == "inspection-template":
            print(
                csv_bytes(
                    "inspection.csv",
                    [
                        {
                            "report_number": str(m.report_number),
                            "object_family": family,
                            "inspection_complete": "",
                            "zero_discoveries_confirmed": "",
                            "comment": "",
                        }
                        for m in manifest.references
                        for family in sorted(BENCHMARK_OBJECT_TYPES)
                    ],
                ).decode(),
                end="",
            )
        else:
            # Validation-only placeholder for frozen submission structure. No routed
            # record is exported here; only the private coordinator importer assigns
            # the actual approved partitions. Humans never supply or see that field.
            validated = validate_forms(
                files,
                {m.report_number: PartitionRole.PROTOCOL_PILOT for m in manifest.references},
                expected_package=manifest,
            )
            print(
                canonical_json_bytes(
                    {
                        "kind": "DRAFT_VALIDATION_ONLY",
                        "complete": validated.complete,
                        "resolved_declarations": len(validated.discoveries),
                        "unresolved_declarations": len(validated.unresolved),
                        "annotation_authorized": False,
                    }
                ).decode()
            )
        return 0
    except (ValueError, OSError, DirectoryLeaseError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
