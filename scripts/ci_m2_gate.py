"""Whole-test CI partitions and fail-closed, source-bound execution receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, TextIO, cast

SHARDS = ("operator", "cleanup-0", "cleanup-1", "cleanup-2", "remainder")
OPERATOR = "tests/unit/test_m2_setup_operator.py::test_complete_operator_route_and_terminal_state"
CLEANUP = "tests/unit/test_m2_setup_native_cleanup.py::test_installed_"
DEPENDENCIES = {"windows-preflight", "windows-tests"}
AUXILIARY = {
    "native-gate": [
        "tests/unit/test_m2_setup_bootstrap.py",
        "tests/unit/test_m2_setup_deployment.py",
        "tests/unit/test_m2_setup_store_witness.py",
        "tests/unit/test_ci_m2_gate.py",
    ],
    "smoke": ["tests/unit/test_acquisition_windows_native.py"],
    "acquisition": [
        f"tests/unit/test_acquisition_{name}.py"
        for name in (
            "engine",
            "ledger",
            "plan",
            "policy",
            "preflight",
            "schema_export",
            "storage",
            "attempt_transport_v2",
            "authorization_v2",
            "compare_runner_v2",
            "landing_v2",
            "live_compare_v2",
            "persistent_ledger_v2",
            "temp_recovery_v2",
            "transport_v2",
            "v2_models",
        )
    ]
    + [
        f"tests/integration/test_acquisition_{name}.py"
        for name in ("dry_run", "live_bootstrap", "live_compare_blocked")
    ],
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def partition(nodeids: list[str]) -> dict[str, list[str]]:
    require(
        bool(nodeids) and all(type(n) is str and "::" in n for n in nodeids),
        "empty or malformed canonical selection",
    )
    require(len(nodeids) == len(set(nodeids)), "duplicate canonical node ID")
    shards: dict[str, list[str]] = {name: [] for name in SHARDS}
    cleanup_index = 0
    for nodeid in sorted(nodeids):
        shard = "remainder"
        if nodeid == OPERATOR:
            shard = "operator"
        elif nodeid.startswith(CLEANUP):
            shard = f"cleanup-{cleanup_index % 3}"
            cleanup_index += 1
        shards[shard].append(nodeid)
    return shards


def command(shard: str) -> list[str]:
    return [
        "pytest",
        *AUXILIARY.get(shard, []),
        f"--junitxml=ci-evidence/{shard}/result.xml",
        "--durations=30",
        "-vv",
    ]


def validate(
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    expected: dict[str, str],
    needs: dict[str, str],
    *,
    whole: bool = False,
) -> None:
    required = {"quality"} if whole else DEPENDENCIES
    require(
        set(needs) == required and all(v == "success" for v in needs.values()),
        "required dependency missing, unexpected, failed, cancelled or skipped",
    )
    require(
        type(manifest.get("schema")) is int
        and manifest["schema"] == 1
        and manifest.get("binding") == expected,
        "manifest source, run or runtime mismatch",
    )
    require(set(manifest) == {"schema", "binding", "canonical"}, "unexpected manifest fields")
    canonical: Any = manifest.get("canonical")
    require(isinstance(canonical, list), "malformed canonical selection")
    assignment = partition(canonical)
    require(canonical == sorted(canonical), "noncanonical collection order")
    if whole:
        assignment = {"all": canonical}
    require(len(results) == len(assignment), "missing or duplicate shard result")
    seen: set[str] = set()
    for result in results:
        shard: Any = result.get("shard")
        require(
            isinstance(shard, str) and shard in assignment and shard not in seen,
            "unexpected or duplicate shard",
        )
        seen.add(shard)
        require(
            type(result.get("schema")) is int
            and result["schema"] == 1
            and result.get("binding") == expected,
            "result source, run or runtime mismatch",
        )
        require(result.get("canonical") == canonical, "collection differs between jobs")
        selected: Any = result.get("selected")
        require(
            type(selected) is list
            and sorted(selected) == assignment[shard]
            and bool(assignment[shard]),
            "missing, unexpected or duplicate selected case",
        )
        require(result.get("command") == command(shard), "unexpected pytest command")
        require(
            type(result.get("exit")) is int and result["exit"] == 0,
            "pytest failed or did not terminate",
        )
        events: Any = result.get("events")
        require(isinstance(events, list), "missing phase events")
        position = 0
        for nodeid in selected:
            require(
                position < len(events)
                and events[position]
                == {
                    "event": "start",
                    "nodeid": nodeid,
                },
                "missing, duplicate or out-of-order testcase start",
            )
            position += 1
            phases: list[dict[str, Any]] = []
            while position < len(events) and events[position].get("event") == "phase":
                event: Any = events[position]
                require(event.get("nodeid") == nodeid, "phase belongs to another case")
                require(event.get("outcome") in {"passed", "skipped"}, "failed phase")
                duration: Any = event.get("duration")
                require(
                    type(duration) in {int, float} and math.isfinite(duration) and duration >= 0,
                    "invalid phase duration",
                )
                require(
                    isinstance(event.get("reason"), str)
                    and isinstance(event.get("xfail"), str)
                    and isinstance(event.get("properties"), list),
                    "malformed phase evidence",
                )
                require(not event["xfail"], "unapproved xfail or XPASS phase")
                require(
                    event["outcome"] != "skipped" or bool(event["reason"]), "skip has no reason"
                )
                phases.append(event)
                position += 1
            names = [phase.get("phase") for phase in phases]
            require(
                names in (["setup", "call", "teardown"], ["setup", "teardown"]),
                "interrupted, duplicate or missing phase",
            )
            require(phases[-1]["outcome"] == "passed", "teardown did not pass")
            require(
                (len(phases) == 2 and phases[0]["outcome"] == "skipped")
                or (len(phases) == 3 and phases[0]["outcome"] == "passed"),
                "invalid setup/call sequence",
            )
        require(position == len(events), "unexpected testcase or phase")
    require(seen == set(assignment), "missing required shard")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def read_object(path: Path) -> dict[str, Any]:
    result = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=invalid_constant,
    )
    require(isinstance(result, dict), "receipt is not a JSON object")
    return result


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def binding() -> dict[str, str]:
    git("diff", "--quiet", "HEAD", "--")
    commit = git("rev-parse", "HEAD")
    require(commit == os.environ["GITHUB_SHA"], "checkout differs from workflow SHA")
    require(
        platform.python_version().startswith(os.environ["EXPECTED_PYTHON"] + "."),
        "unexpected active Python",
    )
    return {
        "commit": commit,
        "tree": git("rev-parse", "HEAD^{tree}"),
        "run": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "platform": sys.platform,
        "python": platform.python_version(),
        "lock": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
    }


def metadata() -> dict[str, Any]:
    return {
        "command": [sys.executable, *sys.argv],
        "cwd": str(Path.cwd()),
        "executable": sys.executable,
        "os": platform.platform(),
        "image": os.environ.get("ImageVersion", "unknown"),  # noqa: SIM112 (GitHub name)
        "uv": subprocess.check_output(["uv", "--version"], text=True).strip(),
        "dependencies": subprocess.check_output(["uv", "pip", "freeze"], text=True).splitlines(),
    }


class Receipts:
    """Observe ordinary pytest phases; select only whole canonical cases."""

    def __init__(self, shard: str, stream: TextIO, identity: dict[str, str], output: Path):
        self.shard = shard
        self.stream = stream
        self.identity = identity
        self.output = output
        self.canonical: list[str] = []
        self.selected: list[str] = []
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.stream.write(json.dumps(event, allow_nan=False) + "\n")
        self.stream.flush()
        # Decoded job logs provide an independent read route when ZIP retrieval is unavailable.
        logged = dict(event)
        if "properties" in logged:
            logged["properties"] = [p for p in logged["properties"] if p[0] != "ci_nodeid"]
        print("M2_CI_EVENT " + json.dumps(logged, allow_nan=False), flush=True)

    def pytest_collection_finish(self, session: Any) -> None:
        # Collection finish follows normal marker/configuration deselection.
        self.canonical = sorted(item.nodeid for item in session.items)
        assignment = partition(self.canonical)
        self.selected = (
            self.canonical if self.shard in {"all", "plan", *AUXILIARY} else assignment[self.shard]
        )
        selected_set = set(self.selected)
        session.items[:] = [item for item in session.items if item.nodeid in selected_set]
        self.selected = [item.nodeid for item in session.items]
        session.testscollected = len(session.items)
        for item in session.items:
            item.user_properties.append(("ci_nodeid", item.nodeid))
        write_object(
            self.output / "manifest.json",
            {
                "schema": 1,
                "binding": self.identity,
                "canonical": self.canonical,
            },
        )

        print(
            "M2_CI_COLLECTION "
            + json.dumps(
                {
                    "binding": self.identity,
                    "shard": self.shard,
                    "canonical_count": len(self.canonical),
                    "canonical_sha256": selection_digest(self.canonical),
                    "selected_count": len(self.selected),
                    "selected_sha256": selection_digest(self.selected),
                }
            ),
            flush=True,
        )

    def pytest_runtest_logstart(self, nodeid: str) -> None:
        self.emit({"event": "start", "nodeid": nodeid})

    def pytest_runtest_logreport(self, report: Any) -> None:
        reason = str(report.longrepr) if report.longrepr else ""
        # Only synthetic CI diagnostics are uploaded; bound failure text and
        # redact disposable runner roots, retaining the exception classification.
        for root in (str(Path.cwd()), os.environ.get("RUNNER_TEMP", "")):
            if root:
                reason = reason.replace(root, "<runner>")
        self.emit(
            {
                "event": "phase",
                "nodeid": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "duration": report.duration,
                "reason": reason[-8000:],
                "xfail": str(getattr(report, "wasxfail", "")),
                "properties": [(name, str(value)) for name, value in report.user_properties],
            }
        )


def execute(shard: str) -> int:
    import pytest

    output = Path("ci-evidence") / shard
    output.mkdir(parents=True, exist_ok=False)
    identity = binding()
    write_object(output / "metadata.json", {"binding": identity, **metadata()})
    with (output / "events.jsonl").open("x", encoding="utf-8") as stream:
        plugin = Receipts(shard, stream, identity, output)
        args = ["--collect-only", "-q"] if shard == "plan" else command(shard)[1:]
        started = time.monotonic()
        code = int(pytest.main(args, plugins=[plugin]))
        stream.write(json.dumps({"event": "finish", "exit": code}) + "\n")
        stream.flush()
    require(binding() == identity, "source identity changed during execution")
    result = {
        "schema": 1,
        "binding": identity,
        "canonical": plugin.canonical,
        "shard": shard,
        "selected": plugin.selected,
        "command": command(shard),
        "exit": code,
        "events": plugin.events,
        "seconds": time.monotonic() - started,
    }
    print(
        "M2_CI_SUMMARY "
        + json.dumps(
            {
                "binding": identity,
                "shard": shard,
                "exit": code,
                "selected_count": len(plugin.selected),
                "canonical_count": len(plugin.canonical),
                "canonical_sha256": selection_digest(plugin.canonical),
                "selected_sha256": selection_digest(plugin.selected),
                "seconds": result["seconds"],
                "phases": dict(
                    Counter(
                        f"{e['phase']}:{e['outcome']}"
                        for e in plugin.events
                        if e["event"] == "phase"
                    )
                ),
            }
        ),
        flush=True,
    )
    if shard != "plan":
        junit = output / "result.xml"
        result["junit_sha256"] = hashlib.sha256(junit.read_bytes()).hexdigest()
        write_object(output / "result.json", result)
        validate_junit(junit, plugin.selected, plugin.events)
        if shard == "native-gate":
            validate_native_control(plugin.events)
        if shard == "all":
            validate(
                read_object(output / "manifest.json"),
                [result],
                identity,
                {"quality": "success"},
                whole=True,
            )
    return code


def selection_digest(nodeids: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(nodeids), separators=(",", ":")).encode()).hexdigest()


def validate_native_control(events: list[dict[str, Any]]) -> None:
    control = (
        "tests/unit/test_m2_setup_bootstrap.py::test_verified_startup_reaches_existing_context"
    )
    phases = [
        (event["phase"], event["outcome"])
        for event in events
        if event["event"] == "phase" and event["nodeid"] == control
    ]
    require(
        phases == [("setup", "passed"), ("call", "passed"), ("teardown", "passed")],
        "actual admitted startup control did not pass all phases",
    )


def property_map(properties: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in properties:
        require(type(pair) in {list, tuple} and len(pair) == 2, "malformed testcase property")
        name, value = pair
        require(
            isinstance(name, str) and name not in result, "duplicate or invalid testcase property"
        )
        result[name] = str(value)
    return result


def validate_junit(path: Path, selected: list[str], events: list[dict[str, Any]]) -> None:
    by_node: dict[str, list[dict[str, Any]]] = {nodeid: [] for nodeid in selected}
    for event in events:
        if event["event"] == "phase":
            require(event["nodeid"] in by_node, "phase outside JUnit selection")
            by_node[event["nodeid"]].append(event)
    cases = ET.parse(path).getroot().findall(".//testcase")
    nodeids: list[str] = []
    for case in cases:
        properties = property_map(
            [
                (prop.get("name"), prop.get("value"))
                for prop in case.findall("./properties/property")
            ]
        )
        nodeid = properties.get("ci_nodeid")
        require(nodeid is not None, "missing JUnit node ID value")
        nodeids.append(cast(str, nodeid))
        require(case.find("failure") is None and case.find("error") is None, "failed JUnit case")
        require(nodeid in by_node, "JUnit case outside phase selection")
        phases = by_node[cast(str, nodeid)]
        require(bool(phases) and phases[-1]["phase"] == "teardown", "missing final testcase phase")
        skipped = case.findall("skipped")
        require(
            len(skipped) <= 1
            and bool(skipped) == any(phase["outcome"] == "skipped" for phase in phases),
            "JUnit and phase skip/pass outcomes disagree",
        )
        require(
            properties == property_map(phases[-1]["properties"]),
            "JUnit and final phase properties disagree",
        )
    require(nodeids == selected, "JUnit cases missing, duplicated or out of order")


def read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        require(isinstance(event, dict), "malformed incremental event")
        events.append(event)
    return events


def validate_metadata(path: Path, expected: dict[str, str], shard: str) -> None:
    document = read_object(path)
    require(
        set(document)
        == {
            "binding",
            "command",
            "cwd",
            "executable",
            "os",
            "image",
            "uv",
            "dependencies",
        },
        "missing or unexpected execution metadata",
    )
    require(document["binding"] == expected, "metadata source, run or runtime mismatch")
    for key in ("cwd", "executable", "os", "image", "uv"):
        require(
            isinstance(document[key], str) and bool(document[key]), "invalid execution metadata"
        )
    expected_command = [document["executable"], "scripts/ci_m2_gate.py"]
    expected_command += ["collect"] if shard == "plan" else ["run", shard]
    require(document["command"] == expected_command, "unexpected execution command")
    dependencies: Any = document["dependencies"]
    require(
        type(dependencies) is list
        and bool(dependencies)
        and all(isinstance(item, str) for item in dependencies),
        "invalid dependency metadata",
    )


def aggregate(root: Path) -> None:
    expected = binding()
    needs_document: Any = json.loads(
        os.environ["CI_NEEDS"], object_pairs_hook=unique_object, parse_constant=invalid_constant
    )
    require(isinstance(needs_document, dict), "malformed needs")
    needs = {name: value.get("result") for name, value in needs_document.items()}
    require(
        {p.name for p in root.iterdir()} == {f"m2-win-{s}" for s in ("plan", *SHARDS)},
        "missing or unexpected artifact directory",
    )
    plan = root / "m2-win-plan"
    require(
        {p.name for p in plan.iterdir()} == {"manifest.json", "metadata.json", "events.jsonl"},
        "missing or unexpected plan artifact",
    )
    validate_metadata(plan / "metadata.json", expected, "plan")
    require(
        read_events(plan / "events.jsonl") == [{"event": "finish", "exit": 0}],
        "canonical collection did not complete",
    )
    results: list[dict[str, Any]] = []
    for shard in SHARDS:
        output = root / f"m2-win-{shard}"
        require(
            {p.name for p in output.iterdir()}
            == {
                "manifest.json",
                "metadata.json",
                "events.jsonl",
                "result.json",
                "result.xml",
            },
            "missing or unexpected result artifact",
        )
        result = read_object(output / "result.json")
        validate_metadata(output / "metadata.json", expected, shard)
        require(result.get("shard") == shard, "wrong artifact shard")
        require(
            result.get("junit_sha256")
            == hashlib.sha256((output / "result.xml").read_bytes()).hexdigest(),
            "JUnit mismatch",
        )
        validate_junit(output / "result.xml", result["selected"], result["events"])
        events = read_events(output / "events.jsonl")
        require(
            events == [*result["events"], {"event": "finish", "exit": 0}],
            "incremental events differ or are incomplete",
        )
        require(
            read_object(output / "manifest.json")
            == read_object(root / "m2-win-plan/manifest.json"),
            "shard manifest differs from canonical plan",
        )
        results.append(result)
    validate(read_object(plan / "manifest.json"), results, expected, needs)
    print(
        "M2_CI_RECONCILED "
        + json.dumps(
            {
                "binding": expected,
                "dependencies": needs,
                "canonical_count": len(results[0]["canonical"]),
                "canonical_sha256": selection_digest(results[0]["canonical"]),
                "shards": {r["shard"]: len(r["selected"]) for r in results},
                "phases": dict(
                    Counter(
                        f"{e['phase']}:{e['outcome']}"
                        for r in results
                        for e in r["events"]
                        if e["event"] == "phase"
                    )
                ),
            }
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "collect", "aggregate"))
    parser.add_argument("target", nargs="?", default="ci-evidence")
    args = parser.parse_args()
    if args.mode == "aggregate":
        aggregate(Path(args.target))
        return 0
    shard = "plan" if args.mode == "collect" else args.target
    require(shard in {*SHARDS, "all", "plan", *AUXILIARY}, "unknown shard")
    return execute(shard)


if __name__ == "__main__":
    raise SystemExit(main())
