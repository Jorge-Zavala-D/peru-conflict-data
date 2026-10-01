"""The required CI context must not accept partial or unrelated execution."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_m2_gate.py"
OPERATOR = "tests/unit/test_m2_setup_operator.py::test_complete_operator_route_and_terminal_state"
CLEANUP = "tests/unit/test_m2_setup_native_cleanup.py::test_installed_native_cleanup"
IDS = [OPERATOR, *(f"{CLEANUP}[{i}]" for i in range(3)), "tests/unit/test_small.py::test_ok"]
BINDING = {
    "commit": "a" * 40,
    "tree": "b" * 40,
    "run": "123",
    "attempt": "1",
    "platform": "win32",
    "python": "3.12.10",
    "lock": "c" * 64,
}


def gate() -> Any:
    assert SCRIPT.is_file(), "complete-coverage CI gate is not implemented"
    spec = importlib.util.spec_from_file_location("ci_m2_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assignments = {
        "operator": [OPERATOR],
        "cleanup-0": [f"{CLEANUP}[0]"],
        "cleanup-1": [f"{CLEANUP}[1]"],
        "cleanup-2": [f"{CLEANUP}[2]"],
        "remainder": ["tests/unit/test_small.py::test_ok"],
    }
    manifest = {"schema": 1, "binding": BINDING, "canonical": sorted(IDS)}
    results: list[dict[str, Any]] = []
    for shard, selected in assignments.items():
        events: list[dict[str, Any]] = []
        for nodeid in selected:
            events.append({"event": "start", "nodeid": nodeid})
            for phase in ("setup", "call", "teardown"):
                events.append(
                    {
                        "event": "phase",
                        "nodeid": nodeid,
                        "phase": phase,
                        "outcome": "passed",
                        "duration": 0.1,
                        "reason": "",
                        "xfail": "",
                        "properties": [["ci_nodeid", nodeid]],
                    }
                )
        results.append(
            {
                "schema": 1,
                "binding": BINDING.copy(),
                "canonical": sorted(IDS),
                "shard": shard,
                "selected": selected,
                "command": [
                    "pytest",
                    f"--junitxml=ci-evidence/{shard}/result.xml",
                    "--durations=30",
                    "-vv",
                ],
                "exit": 0,
                "events": events,
            }
        )
    return manifest, results


def test_partition_is_complete_deterministic_and_keeps_tests_whole() -> None:
    module = gate()
    expected = {
        "operator": [OPERATOR],
        "cleanup-0": [f"{CLEANUP}[0]"],
        "cleanup-1": [f"{CLEANUP}[1]"],
        "cleanup-2": [f"{CLEANUP}[2]"],
        "remainder": ["tests/unit/test_small.py::test_ok"],
    }
    assert module.partition(IDS) == expected
    assert module.partition(list(reversed(IDS))) == expected
    with pytest.raises(ValueError):
        module.partition([*IDS, IDS[0]])


def test_complete_result_and_legitimate_setup_skip_succeed() -> None:
    module = gate()
    manifest, results = evidence()
    needs = {"windows-preflight": "success", "windows-tests": "success"}
    module.validate(manifest, results, BINDING, needs)
    phases = results[-1]["events"]
    phases[1]["outcome"] = "skipped"
    phases[1]["reason"] = "native POSIX control"
    del phases[2]
    module.validate(manifest, results, BINDING, needs)


def test_linux_whole_selection_reconciles_independently_of_execution_order() -> None:
    module = gate()
    manifest, results = evidence()
    combined = copy.deepcopy(results[0])
    combined.update(
        shard="all",
        selected=[nodeid for result in reversed(results) for nodeid in result["selected"]],
        events=[event for result in reversed(results) for event in result["events"]],
        command=["pytest", "--junitxml=ci-evidence/all/result.xml", "--durations=30", "-vv"],
    )
    module.validate(manifest, [combined], BINDING, {"quality": "success"}, whole=True)
    combined["events"].pop()
    with pytest.raises(ValueError):
        module.validate(manifest, [combined], BINDING, {"quality": "success"}, whole=True)


@pytest.mark.parametrize(
    "fault",
    [
        "omission",
        "duplicate",
        "absent",
        "interrupted",
        "failed_phase",
        "wrong_commit",
        "wrong_tree",
        "wrong_runtime",
        "wrong_platform",
        "stale_run",
        "stale_attempt",
        "wrong_command",
        "wrong_selection",
        "unexpected_shard",
        "nonterminal",
        "empty",
        "cancelled",
        "skipped",
        "failed",
        "missing_dependency",
        "unexpected_dependency",
        "canonical_duplicate",
        "canonical_omission",
        "phase_duplicate",
        "no_start",
        "boolean_manifest_schema",
        "boolean_result_schema",
        "xfail_skipped",
        "xpass_passed",
    ],
)
def test_incomplete_or_unrelated_evidence_cannot_pass(fault: str) -> None:
    module = gate()
    manifest, results = copy.deepcopy(evidence())
    needs = {"windows-preflight": "success", "windows-tests": "success"}
    if fault == "omission":
        results[-1]["selected"] = []
    elif fault == "duplicate":
        results.append(copy.deepcopy(results[0]))
    elif fault == "absent":
        results.pop()
    elif fault == "interrupted":
        results[-1]["exit"] = 2
    elif fault == "failed_phase":
        results[-1]["events"][2]["outcome"] = "failed"
    elif fault.startswith("wrong_") or fault.startswith("stale_"):
        key = fault.split("_", 1)[1]
        key = {"runtime": "python", "selection": "selected"}.get(key, key)
        if key in {"command", "selected"}:
            results[-1][key] = []
        else:
            results[-1]["binding"][key] = "wrong"
    elif fault == "unexpected_shard":
        results[-1]["shard"] = "bonus"
    elif fault == "nonterminal":
        results[-1]["events"].pop()
    elif fault == "empty":
        results.clear()
    elif fault in {"cancelled", "skipped", "failed"}:
        needs["windows-tests"] = fault
    elif fault == "missing_dependency":
        needs.pop("windows-tests")
    elif fault == "unexpected_dependency":
        needs["bonus"] = "success"
    elif fault == "canonical_duplicate":
        manifest["canonical"].append(IDS[0])
    elif fault == "canonical_omission":
        manifest["canonical"].pop()
    elif fault == "phase_duplicate":
        results[-1]["events"].append(results[-1]["events"][-1])
    elif fault == "no_start":
        results[-1]["events"].pop(0)
    elif fault == "boolean_manifest_schema":
        manifest["schema"] = True
    elif fault == "boolean_result_schema":
        results[0]["schema"] = True
    elif fault in {"xfail_skipped", "xpass_passed"}:
        results[-1]["events"][2].update(
            outcome="skipped" if fault == "xfail_skipped" else "passed",
            reason="unapproved synthetic expected failure",
            xfail="unapproved synthetic expected failure",
        )
    with pytest.raises(ValueError):
        module.validate(manifest, results, BINDING, needs)


def test_json_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path: Path) -> None:
    module = gate()
    receipt = tmp_path / "bad.json"
    for text in ('{"schema": 1, "schema": 1}', '{"duration": NaN}', "[]"):
        receipt.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            module.read_object(receipt)


@pytest.mark.parametrize("change", ["unchanged", "working", "staged", "command_error"])
def test_binding_requires_unchanged_tracked_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    """HEAD alone cannot expose a tracked source change made during a test."""
    module = gate()
    hooks = tmp_path / "empty-hooks"
    hooks.mkdir()
    git = [
        "git",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=Synthetic CI",
        "-c",
        "user.email=ci@example.invalid",
    ]

    def run(*args: str) -> str:
        return subprocess.check_output([*git, *args], cwd=tmp_path, text=True).strip()

    run("init", "-q")
    (tmp_path / "uv.lock").write_text("synthetic frozen lock\n", encoding="utf-8")
    source = tmp_path / "tracked.py"
    source.write_text("value = 1\n", encoding="utf-8")
    run("add", "uv.lock", "tracked.py")
    run("commit", "-qm", "synthetic source fixture")
    head = run("rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "GITHUB_SHA": head,
        "EXPECTED_PYTHON": ".".join(platform.python_version_tuple()[:2]),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv(name, value)
    before = module.binding()
    (tmp_path / "untracked-synthetic-result.json").write_text("{}", encoding="utf-8")
    if change in {"working", "staged"}:
        source.write_text("value = 2\n", encoding="utf-8")
        if change == "staged":
            run("add", "tracked.py")
    elif change == "command_error":
        (tmp_path / ".git/index").write_bytes(b"invalid synthetic index")
    if change == "unchanged":
        assert module.binding() == before
    else:
        with pytest.raises(subprocess.CalledProcessError):
            module.binding()


@pytest.mark.parametrize("fault", [None, "skipped", "missing_call"])
def test_native_prerequisite_requires_the_actual_admitted_control(fault: str | None) -> None:
    module = gate()
    assert hasattr(module, "validate_native_control"), "native control can be skipped"
    events = [
        {
            "event": "phase",
            "nodeid": (
                "tests/unit/test_m2_setup_bootstrap.py::test_verified_startup_reaches_existing_context"
            ),
            "phase": phase,
            "outcome": "passed",
        }
        for phase in ("setup", "call", "teardown")
    ]
    if fault == "skipped":
        events[1]["outcome"] = "skipped"
    elif fault == "missing_call":
        events.pop(1)
    if fault is None:
        module.validate_native_control(events)
    else:
        with pytest.raises(ValueError):
            module.validate_native_control(events)


def test_real_pytest_selection_phases_and_junit_reconcile(tmp_path: Path) -> None:
    """Selection must retain the default marker filter and real terminal phases."""
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = --strict-markers -m 'not external'\nmarkers = external: network\n",
        encoding="utf-8",
    )
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n"
        "def test_z_pass(record_property):\n    record_property('synthetic', 'preserved')\n"
        "    record_property('integer', 108)\n"
        "@pytest.mark.skip(reason='native platform')\ndef test_a_skip():\n    pass\n"
        "@pytest.mark.external\ndef test_excluded():\n    assert False\n",
        encoding="utf-8",
    )
    output = tmp_path / "ci-evidence/remainder"
    output.mkdir(parents=True)
    code = (
        "import sys, importlib.util, json; from pathlib import Path; "
        f"sys.path.append({str(Path(pytest.__file__).parents[1])!r}); import pytest; "
        f"spec=importlib.util.spec_from_file_location('ci_gate', {str(SCRIPT)!r}); "
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        f"stream=Path({str(output / 'events.jsonl')!r}).open('w'); "
        f"plugin=module.Receipts('remainder',stream,{BINDING!r},Path({str(output)!r})); "
        "rc=pytest.main(module.command('remainder')[1:],plugins=[plugin]); stream.close(); "
        f"Path({str(output / 'observed.json')!r}).write_text(json.dumps("
        "{'canonical':plugin.canonical,'selected':plugin.selected,'events':plugin.events})); "
        f"module.validate_junit(Path({str(output / 'result.xml')!r}),"
        "plugin.selected,plugin.events); "
        "raise SystemExit(rc)"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    logged = [
        json.loads(line.split("M2_CI_EVENT ", 1)[1])
        for line in completed.stdout.splitlines()
        if "M2_CI_EVENT " in line
    ]
    assert len(logged) == 7  # Two starts; three passing and two skipped-case phases.
    assert ["synthetic", "preserved"] in logged[2]["properties"]
    assert ["integer", "108"] in logged[2]["properties"]
    assert "M2_CI_COLLECTION " in completed.stdout
    observed = json.loads((output / "observed.json").read_text())
    assert observed["canonical"] == ["test_sample.py::test_a_skip", "test_sample.py::test_z_pass"]
    assert observed["selected"] == ["test_sample.py::test_z_pass", "test_sample.py::test_a_skip"]
    assert [
        (event["phase"], event["outcome"])
        for event in observed["events"]
        if event["event"] == "phase"
    ] == [
        ("setup", "passed"),
        ("call", "passed"),
        ("teardown", "passed"),
        ("setup", "skipped"),
        ("teardown", "passed"),
    ]
    junit = output / "result.xml"
    assert 'name="synthetic" value="preserved"' in junit.read_text()
    module = gate()
    with pytest.raises(ValueError):
        module.validate_junit(junit, ["test_sample.py::test_z_pass"], observed["events"])


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "metadata",
        "extra_plan",
        "plan_interrupted",
        "needs_nan",
        "junit_skip",
        "phase_skip_junit_pass",
        "property_missing",
        "property_changed",
        "property_duplicate",
        "phase_property_duplicate",
    ],
)
def test_downloaded_artifact_set_is_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    module = gate()
    manifest, results = evidence()
    results[0]["events"][-1]["properties"].append(["operator_evidence", '{"checks":108}'])
    if fault == "phase_skip_junit_pass":
        results[0]["events"][2].update(outcome="skipped", reason="synthetic skip")
    for result in [None, *results]:
        shard = result["shard"] if result else "plan"
        directory = tmp_path / f"m2-win-{shard}"
        directory.mkdir()
        module.write_object(directory / "manifest.json", manifest)
        module.write_object(
            directory / "metadata.json",
            {
                "binding": BINDING,
                "command": [
                    "python",
                    "scripts/ci_m2_gate.py",
                    *(["collect"] if shard == "plan" else ["run", shard]),
                ],
                "cwd": "synthetic-checkout",
                "executable": "python",
                "os": "Windows",
                "image": "synthetic",
                "uv": "uv 0.11.28",
                "dependencies": ["pytest==9.0.2"],
            },
        )
        events: list[dict[str, Any]] = result["events"] if result else []
        (directory / "events.jsonl").write_text(
            "".join(
                json.dumps(event) + "\n" for event in [*events, {"event": "finish", "exit": 0}]
            ),
            encoding="utf-8",
        )
        if result:
            suites = ET.Element("testsuites")
            suite = ET.SubElement(suites, "testsuite")
            for nodeid in result["selected"]:
                case = ET.SubElement(suite, "testcase")
                properties = ET.SubElement(case, "properties")
                final = next(
                    event
                    for event in result["events"]
                    if event.get("phase") == "teardown" and event["nodeid"] == nodeid
                )
                for name, value in final["properties"]:
                    ET.SubElement(properties, "property", name=name, value=value)
            xml = ET.tostring(suites, encoding="unicode")
            (directory / "result.xml").write_text(xml, encoding="utf-8")
            result["junit_sha256"] = hashlib.sha256(xml.encode()).hexdigest()
            module.write_object(directory / "result.json", result)
    monkeypatch.setattr(module, "binding", lambda: BINDING)
    monkeypatch.setenv(
        "CI_NEEDS",
        json.dumps(
            {
                "windows-preflight": {"result": "success"},
                "windows-tests": {"result": "success"},
            }
        ),
    )
    if fault == "metadata":
        (tmp_path / "m2-win-remainder/metadata.json").write_text("not JSON")
    elif fault == "extra_plan":
        (tmp_path / "m2-win-plan/unexpected.json").write_text("{}")
    elif fault == "plan_interrupted":
        (tmp_path / "m2-win-plan/events.jsonl").write_text("")
    elif fault == "needs_nan":
        monkeypatch.setenv(
            "CI_NEEDS",
            '{"windows-preflight":{"result":"success","x":NaN},'
            '"windows-tests":{"result":"success"}}',
        )
    elif fault in {"junit_skip", "property_missing", "property_changed", "property_duplicate"}:
        directory = tmp_path / "m2-win-operator"
        document = ET.parse(directory / "result.xml")
        case = document.getroot().find(".//testcase")
        assert case is not None
        if fault == "junit_skip":
            ET.SubElement(case, "skipped")
        else:
            properties = case.find("properties")
            assert properties is not None
            evidence_property = properties.find("property[@name='operator_evidence']")
            assert evidence_property is not None
            if fault == "property_missing":
                properties.remove(evidence_property)
            elif fault == "property_changed":
                evidence_property.set("value", '{"checks":0}')
            else:
                properties.append(copy.deepcopy(evidence_property))
        document.write(directory / "result.xml", encoding="utf-8")
        results[0]["junit_sha256"] = hashlib.sha256(
            (directory / "result.xml").read_bytes()
        ).hexdigest()
        module.write_object(directory / "result.json", results[0])
    elif fault == "phase_property_duplicate":
        directory = tmp_path / "m2-win-operator"
        results[0]["events"][-1]["properties"].append(["operator_evidence", '{"checks":108}'])
        module.write_object(directory / "result.json", results[0])
        (directory / "events.jsonl").write_text(
            "".join(
                json.dumps(event) + "\n"
                for event in [*results[0]["events"], {"event": "finish", "exit": 0}]
            ),
            encoding="utf-8",
        )
    if fault is None:
        module.aggregate(tmp_path)
    else:
        with pytest.raises(ValueError):
            module.aggregate(tmp_path)
