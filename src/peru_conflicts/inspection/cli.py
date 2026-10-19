"""Explicit build/validate/query/export commands for supplied documentary evidence."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .builder import build_snapshot
from .exports import export
from .queries import QUERIES, query
from .validation import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    build = commands.add_parser("build")
    build.add_argument("manifest", type=Path)
    build.add_argument("output", type=Path)
    check = commands.add_parser("validate")
    check.add_argument("database", type=Path)
    check.add_argument("manifest", type=Path)
    get = commands.add_parser("query")
    get.add_argument("database", type=Path)
    get.add_argument("kind", choices=QUERIES)
    get.add_argument("--cell")
    out = commands.add_parser("export")
    out.add_argument("database", type=Path)
    out.add_argument("output", type=Path)
    for command in [build, check, get, out]:
        command.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.receipt is not None and args.receipt.exists():
            raise FileExistsError(args.receipt)
        result: Any
        if args.operation == "build":
            result = build_snapshot(args.manifest, args.output)
        elif args.operation == "validate":
            result = validate(args.database, args.manifest)
        elif args.operation == "query":
            result = query(args.database, args.kind, args.cell)
        else:
            args.output.mkdir(exist_ok=False)
            result = export(args.database, args.output)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.receipt is not None:
            with args.receipt.open("x", encoding="utf-8") as handle:
                handle.write(serialized)
        print(serialized, end="")
        return 0
    except (
        ValueError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        AssertionError,
        KeyError,
        TypeError,
    ) as exc:
        actual_output = getattr(args, "output", None)
        files: list[str] = []
        if isinstance(actual_output, Path) and actual_output.exists():
            files = (
                [str(p) for p in actual_output.iterdir()]
                if actual_output.is_dir()
                else [str(actual_output)]
            )
        print(
            json.dumps(
                {
                    "success": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "actual_output_files": files,
                    "limitation": (
                        "Existing files are not overwritten; multi-file/folder atomicity "
                        "is not promised."
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 1
