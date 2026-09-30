"""Operator lifecycle through the isolated verified entry, never public test authority."""

import hashlib
import inspect
import json
import pickle
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest
from test_m2_setup_deployment import clean_startup_environment, installation_fixture

from peru_conflicts.execution.python_environment_policy import capture_document
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.hashing import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "scripts/start_m2_setup.py"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("operation", ["admit", "next", "capture", "import", "status", "recover"])
def test_public_operator_is_closed(operation: str):
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ENTRY), operation],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=clean_startup_environment(),
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "M2 startup rejected: CLOSED"


def prepare(
    tmp_path: Path, *, native: bool = False, sharing: bool = False, complete: bool = False
) -> tuple[Path, dict[str, object]]:
    root, grant, installation, bindings = installation_fixture(tmp_path)
    pin = json.loads(installation)
    pin["credential_refs"] = {session: "SYNTHETIC-" + session for session in pin["credential_refs"]}
    if native:
        pin["transport_profile"] = "native_required_guarantees"
    if complete:
        pin["test_service_evidence"] = "complete_synthetic_service"
    if sharing:
        from peru_conflicts.execution.setup_dropbox import (
            _SCOPES,  # pyright: ignore[reportPrivateUsage]
        )

        pin["credential_refs"] = {s: s for s in pin["credential_refs"]}
        pin["scopes"] = {s: sorted(set(_SCOPES.values())) for s in pin["credential_refs"]}
    installation = (
        Installation.model_validate_json(canonical_json_bytes(pin)).model_dump_json().encode()
    )
    environment = canonical_json_bytes(
        capture_document(sha(canonical_json_bytes(pin["runtime_files"])))
    )
    registry = canonical_json_bytes(
        {
            "version": "m2-real-registry-v2",
            "grants": [
                {
                    "grant_sha256": sha(grant),
                    "installation_sha256": sha(installation),
                    "revoked": False,
                }
            ],
        }
    )
    for name, raw in (
        ("grant", grant),
        ("installation", installation),
        ("bindings", bindings),
        ("registry", registry),
        ("environment", environment),
    ):
        (tmp_path / f"{name}.json").write_bytes(raw)
    anchor: dict[str, object] = {
        "bootstrap_sha256": sha(
            (ROOT / "src/peru_conflicts/execution/setup_bootstrap.py").read_bytes()
        ),
        "installation_path": str(tmp_path / "installation.json"),
        "installation_sha256": sha(installation),
        "registry_path": str(tmp_path / "registry.json"),
        "registry_sha256": sha(registry),
        "grant_path": str(tmp_path / "grant.json"),
        "environment_path": str(tmp_path / "environment.json"),
        "environment_sha256": sha(environment),
        "executable": str(Path(sys.executable).resolve()),
        "initial_paths": [],
    }
    return root, anchor


def invoke(
    tmp_path: Path,
    anchor: dict[str, object],
    operation: str,
    *,
    fault: str = "none",
    sharing: str = "",
):
    sharing_code = ""
    # A sibling of the explicit basetemp survives pytest clearing that subtree.
    progress_path = tmp_path.parent.with_name(tmp_path.parent.name + "-progress") / (
        tmp_path.name + ".jsonl"
    )
    if sharing:
        from test_m2_setup_native_procedure import connect_service

        from peru_conflicts.execution.setup_offline import (
            FakeHTTP,
            _metadata,  # pyright: ignore[reportPrivateUsage]
        )

        # Reuse only independent service/connection code, not offline admission.
        # No offline module or trust dictionaries exist in the isolated child.
        service_source = "from __future__ import annotations\n" + "\n".join(
            inspect.getsource(x) for x in (_metadata, FakeHTTP, connect_service)
        )
        sharing_code = f"""
import pickle, ssl, pytest
from pathlib import PurePosixPath
from typing import Any, cast
from collections.abc import Callable
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.execution.setup_dropbox import (
    FolderObservation, FileObservation, Exchange, PreparedRequest, encode_request,
    dropbox_content_hash,
)
exec(compile({service_source!r}, '<independent-test-service>', 'exec'), globals())
assert '_ADMISSIONS' not in globals() and '_WITNESSES' not in globals()
service = FakeHTTP(None)
state_path = Path({str(tmp_path / "test-service-state.pickle")!r})
if state_path.exists():
    # Fixed test-owned fixture, never a collector ingress or operator argument.
    service.__dict__.update(pickle.loads(state_path.read_bytes()))
service.async_sharing = True
if {sharing!r} == 'complete-prefix':
    service.pending_polls = 1
    service.page_size = 1
before = len(service.calls)
progress_path = Path({str(progress_path)!r})
progress_path.parent.mkdir(exist_ok=True)
def progress(phase, summary):
    import time
    with progress_path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({{'time_ns': time.time_ns(), 'phase': phase,
            'state': summary.get('state'), 'sequence': summary.get('sequence'),
            'checks': len(summary.get('checks', {{}})),
            'provider_requests': len(service.calls)}}) + '\\n')
        stream.flush()
patch = pytest.MonkeyPatch()
connect_service(patch, service)
factory = setup_transport._connection
resolver = setup_transport._read_credential
def counted_factory(*args, **kwargs):
    counts['factory'] += 1
    return factory(*args, **kwargs)
def counted_resolver(reference):
    counts['resolver'] += 1
    return resolver(reference)
setup_transport._connection = counted_factory
setup_transport._read_credential = counted_resolver
if {sharing!r} in ('prefix', 'complete-prefix'):
    assert entry.operate('admit', context)['exit_code'] == 0
    for _ in range(50):
        preview = entry.operate('next', context)
        result = entry.operate('capture', context)
        assert result['result'] in ('PASS', 'PENDING'), result
        if preview['action'] == 'share':
            assert result['state'] == 'PENDING'
            break
    else:
        raise AssertionError('lawful sharing prefix did not terminate')
if {sharing!r} == 'complete':
    for _ in range(1200):
        progress('preview_start', {{}})
        preview = entry.operate('next', context)
        progress('preview_end', preview)
        if preview['state'] == 'COMPLETED':
            break
        assert preview['state'] in ('READY', 'PENDING'), preview
        result = entry.operate('capture', context)
        progress('capture_end', result)
        assert result['result'] in ('PASS', 'PENDING'), (preview, result)
        assert result['state'] not in ('STOPPED', 'UNKNOWN', 'BLOCKED'), result
    else:
        raise AssertionError('operator schedule did not terminate')
"""
    # Trust is prepared by this independent parent, not read from the capture/CLI.
    code = f"""
import sys, os, types, hashlib
from pathlib import Path
from datetime import datetime
def deny(event, args):
    if event.startswith('socket.') and event != 'socket.gethostname':
        raise AssertionError('NETWORK_FORBIDDEN')
sys.addaudithook(deny)
for key in tuple(os.environ):
    if key.lower().startswith(('python', 'pytest')):
        del os.environ[key]
anchor = {anchor!r}
anchor['initial_paths'] = list(sys.path)
entry_path = Path({str(ENTRY)!r})
raw = entry_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == {sha(ENTRY.read_bytes())!r}
entry = types.ModuleType('_protected_test_entry')
entry.__file__ = str(entry_path)
exec(compile(raw, str(entry_path), 'exec'), entry.__dict__)
assert hasattr(entry, 'operate'), 'operator connection is absent'
context = entry.launch(anchor, lambda: Path({str(tmp_path / "bindings.json")!r}).read_bytes(),
    lambda: datetime.fromisoformat('2026-09-23T12:00:00+00:00'))
assert 'peru_conflicts.execution.setup_offline' not in sys.modules
sys.modules['peru_conflicts.execution.setup_offline'] = None
import io, json
from peru_conflicts.execution import setup_transport
counts = dict(resolver=0, factory=0, send=0)
accounts = {{'fixture-session-coordinator':
                ('dbid:offline-coordinator', 'offline-coordinator-home'),
            'fixture-session-annotator-a': ('dbid:offline-annotator-a', 'offline-a-home'),
            'fixture-session-annotator-b': ('dbid:offline-annotator-b', 'offline-b-home')}}
class Connection:
    def __init__(self, host, **kwargs):
        counts['factory'] += 1
        assert host == 'api.dropboxapi.com'
    def request(self, method, path, body, headers):
        counts['send'] += 1
        assert method == 'POST' and path == '/2/users/get_current_account' and body == b'{{}}'
        self.session = headers['Authorization'].removeprefix('Bearer SYNTHETIC-')
        if {fault!r} == 'lost':
            raise TimeoutError('SYNTHETIC-SECRET-CANARY')
    def getresponse(self):
        account, namespace = accounts[self.session]
        raw = json.dumps({{'account_id': account, 'root_info': {{'.tag': 'user',
            'root_namespace_id': namespace, 'home_namespace_id': namespace}}}}).encode()
        class Response:
            status = 200
            stream = io.BytesIO(raw)
            def getheaders(self): return [('x-dropbox-request-id', 'synthetic-request')]
            def getheader(self, name, default=None): return default
            def read(self, size): return self.stream.read(size)
            read1 = read
        return Response()
    def close(self): pass
def credential(reference):
    counts['resolver'] += 1
    return reference
setup_transport._connection = Connection
setup_transport._read_credential = credential
{sharing_code}
result = entry.operate({operation!r}, context)
if {bool(sharing)!r}:
    counts['send'] = len(service.calls) - before
    result['test_routes'] = [request.route for request in service.calls[before:]]
    state_path.write_bytes(pickle.dumps(service.__dict__))
assert sys.modules['peru_conflicts.execution.setup_offline'] is None
print(json.dumps({{'result': result, 'counts': counts}}))
"""
    script = tmp_path / "test-operator-child.py"
    script.write_text(code, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=21600 if sharing == "complete" else 900 if sharing.endswith("prefix") else 240,
        env=clean_startup_environment(),
    )
    assert "SYNTHETIC-SECRET-CANARY" not in result.stdout + result.stderr
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_operator_admit_status_next_and_native_capture(tmp_path: Path):
    root, anchor = prepare(tmp_path)
    admitted = invoke(tmp_path, anchor, "admit")
    assert admitted["result"]["state"] == "READY"
    assert len(admitted["result"]["not_run"]) == 108
    assert admitted["result"]["checks"] == {}
    assert admitted["result"]["controls"] == {
        "APP-ACCEPTED-BYTES-A": "NOT_RUN",
        "APP-ACCEPTED-BYTES-B": "NOT_RUN",
    }
    before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    for operation in ("status", "recover", "next"):
        result = invoke(tmp_path, anchor, operation)
        assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}
        assert result["result"]["state"] == "READY"
    assert before == {str(p): p.read_bytes() for p in root.rglob("*.json")}
    result = invoke(tmp_path, anchor, "capture")
    assert result["result"]["result"] == "PASS"
    assert result["counts"] == {"resolver": 1, "factory": 1, "send": 1}
    records = [json.loads(p.read_bytes()) for p in sorted((root / "run").glob("0*.json"))]
    assert records[-1]["kind"] == "outcome"
    original = json.loads(bytes.fromhex(records[-2]["payload"]["original_hex"]))
    assert (
        bytes.fromhex(original["exchanges"][0]["response_hex"])
        == json.dumps(
            {
                "account_id": "dbid:offline-coordinator",
                "root_info": {
                    ".tag": "user",
                    "root_namespace_id": "offline-coordinator-home",
                    "home_namespace_id": "offline-coordinator-home",
                },
            }
        ).encode()
    )
    # A completed action allows the next lawful action; it is not a replay.
    second = invoke(tmp_path, anchor, "capture")
    assert second["result"]["result"] == "PASS"
    assert second["counts"]["send"] == 1


def test_operator_consumed_unknown_cannot_redispatch(tmp_path: Path):
    _, anchor = prepare(tmp_path)
    invoke(tmp_path, anchor, "admit")
    lost = invoke(tmp_path, anchor, "capture", fault="lost")
    assert lost["counts"]["send"] == 1
    for operation in ("status", "recover", "capture"):
        result = invoke(tmp_path, anchor, operation)
        assert result["result"]["state"] == "UNKNOWN"
        assert len(result["result"]["not_run"]) == 108
        assert result["result"]["checks"] == {}
        assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}


def test_complete_operator_route_and_terminal_state(
    tmp_path: Path, record_property: Callable[[str, object], None]
):
    """Catches skipped controls/checks, lifecycle redispatch and false terminal reporting."""
    from peru_conflicts.execution.setup_authority import schedule

    root, anchor = prepare(tmp_path, sharing=True, complete=True)
    prefix = invoke(tmp_path, anchor, "status", sharing="complete-prefix")
    assert prefix["result"]["state"] == "PENDING"
    assert prefix["result"]["test_routes"].count("sharing/share_folder") == 1
    # Fresh verified interpreter resumes the acknowledged job, not its mutation.
    completed = invoke(tmp_path, anchor, "status", sharing="complete")
    assert completed["result"]["state"] == "COMPLETED"
    records = [json.loads(p.read_bytes()) for p in sorted((root / "run").glob("0*.json"))]
    checks = [r for r in records if r["kind"] == "outcome" and r["order"]["check_id"]]
    expected = {str(r["check_id"]): r for r in schedule()}
    assert len(checks) == len(expected) == 108
    assert {r["order"]["check_id"] for r in checks} == set(expected)
    for record in checks:
        order = record["order"]
        row = expected[order["check_id"]]
        assert (
            order["actor"]["actor"],
            order["action"],
            order["logical_path"],
            order["expected"],
        ) == (row["actor"], row["operation"], row["operation_target"], row["expected_outcome"])
        assert record["payload"]["result"] == "PASS"
    assert Counter(r["order"]["action"] for r in checks) == {"list": 36, "read": 36, "write": 36}
    assert Counter(r["order"]["expected"] for r in checks) == {"ALLOW": 46, "DENY": 62}
    assert completed["result"]["checks"] == dict.fromkeys(expected, "PASS")
    assert completed["result"]["not_run"] == []
    assert completed["result"]["controls"] == {
        "APP-ACCEPTED-BYTES-A": "PASS",
        "APP-ACCEPTED-BYTES-B": "PASS",
    }
    controls = [r for r in records if r["kind"] == "capture" and r["order"]["action"] == "control"]
    assert [r["order"]["control_id"] for r in controls] == [
        "APP-ACCEPTED-BYTES-A",
        "APP-ACCEPTED-BYTES-B",
    ]
    receipts = [json.loads(bytes.fromhex(r["payload"]["original_hex"])) for r in controls]
    assert len({r["isolated_store_sha256"] for r in receipts}) == 2
    for receipt in receipts:
        assert receipt["level"] == "COMPONENT"
        assert receipt["live_path_coverage"] == "NOT_ESTABLISHED"
        assert receipt["original_sha256"] == receipt["preserved_sha256"]
        assert receipt["replacement"] == "FileExistsError"
    # This pickle is independent test-provider state, never application ingress/trust.
    service = pickle.loads((tmp_path / "test-service-state.pickle").read_bytes())
    assert len(service["shares"]) == 4
    assert all(len(s["mounts"]) == 1 and not s["pending"] for s in service["shares"].values())
    routes = Counter(r.route for r in service["calls"])
    assert routes["sharing/share_folder"] == 4
    assert routes["sharing/check_share_job_status"] == 8
    assert any(route.endswith("/continue") for route in routes)
    assert not service["contents"]
    assert not any(o.kind == "file" for o in service["objects"].values())
    assert not any(r["payload"].get("reconciliation_required") for r in records)
    for path in sorted((root / "run").glob("0*.json")):
        assert (root / "checkpoint" / path.name).read_bytes() == sha(path.read_bytes()).encode()
    originals = [r for r in records if r["kind"] == "capture"]
    assert all(r["payload"]["original_hex"] for r in originals)
    action_exchanges = [r for r in records if r["kind"] == "native_exchange"]
    observations = [r for r in records if r["kind"] == "native_observation"]
    assert len(action_exchanges) + len(observations) == len(service["calls"])
    for original in originals:
        if original["order"]["action"] == "control":
            continue
        capture = json.loads(bytes.fromhex(original["payload"]["original_hex"]))
        assert capture["exchanges"] == [
            r["payload"] for r in action_exchanges if r["order"] == original["order"]
        ]
    before = {
        str(p): p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "writer.lock"
    }
    for operation in ("status", "next", "capture", "recover"):
        terminal = invoke(tmp_path, anchor, operation, sharing="resume")
        assert terminal["result"]["state"] == "COMPLETED"
        assert terminal["result"]["exit_code"] == 0
        assert "action" not in terminal["result"]
        assert terminal["counts"] == {"resolver": 0, "factory": 0, "send": 0}
    assert before == {
        str(p): p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "writer.lock"
    }
    record_property(
        "operator_evidence",
        json.dumps(
            {
                "prefix_counts": prefix["counts"],
                "continuation_counts": completed["counts"],
                "routes": dict(routes),
                "records": len(records),
                "originals": len(originals),
                "action_exchanges": len(action_exchanges),
                "supplementary_observations": len(observations),
                "check_ids": sorted(expected),
                "check_count": len(checks),
                "controls": receipts,
                "remaining_probes": 0,
                "reconciliation": 0,
                "terminal": "COMPLETED",
                "real_checks": "NOT_RUN",
            },
            sort_keys=True,
        ),
    )


@pytest.mark.parametrize("fault", ["valid", "malformed", "secret", "mismatch"])
def test_operator_transferred_import_and_restart(tmp_path: Path, fault: str):
    from peru_conflicts.execution.setup_bridge import digest
    from peru_conflicts.execution.setup_dropbox import OriginalCapture, RealWorkOrder
    from peru_conflicts.execution.setup_offline import FakeHTTP

    root, anchor = prepare(tmp_path)
    invoke(tmp_path, anchor, "admit")
    lost = invoke(tmp_path, anchor, "capture", fault="lost")
    assert lost["counts"]["send"] == 1
    record = json.loads((root / "run/000001.json").read_bytes())
    order = RealWorkOrder.model_validate_json(json.dumps(record["order"]))
    service = FakeHTTP(None)
    exchange = service._respond(order.request, None)  # pyright: ignore[reportPrivateUsage]
    original = (
        OriginalCapture(
            order_sha256=digest(order),
            actor_session_ref=order.actor.session_ref,
            namespace=order.namespace,
            started=order.issued_at,
            ended=order.issued_at,
            exchanges=(exchange,),
            before_hex=(),
            after_hex=(),
        )
        .model_dump_json()
        .encode()
    )
    if fault == "malformed":
        original = b'{"duplicate":1,"duplicate":2}'
    elif fault == "secret":
        original = b'{"access_token":"SYNTHETIC-SECRET-CANARY"}'
    (root / "witness" / (digest(order) + ".json")).write_bytes(
        canonical_json_bytes({"order": digest(order), "capture": sha(original)})
    )
    (root / "witness" / (sha(original) + ".capture")).write_bytes(
        original + b" " if fault == "mismatch" else original
    )
    result = invoke(tmp_path, anchor, "import")
    assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}
    records = [json.loads(p.read_bytes()) for p in sorted((root / "run").glob("0*.json"))]
    captures = [
        bytes.fromhex(r["payload"]["original_hex"]) for r in records if r["kind"] == "capture"
    ]
    assert captures == ([original] if fault in {"valid", "malformed"} else [])
    expected = {
        "valid": "READY",
        "malformed": "STOPPED",
        "secret": "UNKNOWN",
        "mismatch": "UNKNOWN",
    }[fault]
    assert result["result"]["state"] == expected
    before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    recovered = invoke(tmp_path, anchor, "recover")
    assert recovered["result"]["state"] == expected
    assert recovered["counts"] == {"resolver": 0, "factory": 0, "send": 0}
    assert before == {str(p): p.read_bytes() for p in root.rglob("*.json")}


@pytest.mark.parametrize(
    "arguments",
    [
        ["--registry", "SYNTHETIC-SECRET-CANARY"],
        ["import", "SYNTHETIC-SECRET-CANARY"],
        ["--enable-live"],
    ],
)
def test_operator_rejects_selectors_without_echo(arguments: list[str]):
    for entry in (ENTRY, ROOT / "scripts/prepare_m2_setup_work_order.py"):
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(entry), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 2
        assert "SYNTHETIC-SECRET-CANARY" not in result.stdout + result.stderr


def test_operator_missing_and_corrupt_history_never_initialized(tmp_path: Path):
    root, anchor = prepare(tmp_path)
    for operation in ("status", "capture"):
        result = invoke(tmp_path, anchor, operation)
        assert result["result"]["state"] == "REJECTED"
        assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}
        assert not list((root / "run").iterdir())
    invoke(tmp_path, anchor, "admit")
    invoke(tmp_path, anchor, "capture", fault="lost")
    target = root / "run/000002.json"
    target.write_bytes(target.read_bytes() + b" ")
    before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    result = invoke(tmp_path, anchor, "recover")
    assert result["result"]["state"] == "REJECTED"
    assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}
    assert before == {str(p): p.read_bytes() for p in root.rglob("*.json")}


def test_installation_schema_is_exported_additively(tmp_path: Path):
    from peru_conflicts.execution import setup_deployment

    exporter = getattr(setup_deployment, "export_installation_schema", None)
    assert callable(exporter), "installation operational schema is not exported"
    path = exporter(tmp_path)
    assert isinstance(path, Path)
    value = json.loads(path.read_bytes())
    assert path.name == "setup_installation_v1.json"
    assert value["additionalProperties"] is False
    assert {"store", "checkpoint", "witness_store", "runtime_files"} <= set(value["required"])


def test_operator_native_guarantees_remain_refused(tmp_path: Path):
    root, anchor = prepare(tmp_path, native=True)
    invoke(tmp_path, anchor, "admit")
    result = invoke(tmp_path, anchor, "capture")
    assert result["result"]["state"] == "INTENT_PENDING"
    assert result["result"]["exit_code"] == 3
    assert result["counts"] == {"resolver": 0, "factory": 0, "send": 0}
    records = [json.loads(p.read_bytes()) for p in sorted((root / "run").glob("0*.json"))]
    assert [r["kind"] for r in records] == ["intent"]
    restarted = invoke(tmp_path, anchor, "capture")
    assert restarted["result"]["state"] == "INTENT_PENDING"
    assert restarted["counts"] == {"resolver": 0, "factory": 0, "send": 0}


def test_operator_acknowledged_async_restarts_with_status_only(tmp_path: Path):
    _, anchor = prepare(tmp_path, sharing=True)
    pending = invoke(tmp_path, anchor, "status", sharing="prefix")
    assert pending["result"]["state"] == "PENDING"
    assert pending["result"]["test_routes"].count("sharing/share_folder") == 1
    resumed = invoke(tmp_path, anchor, "capture", sharing="resume")
    assert resumed["result"]["result"] == "PASS"
    assert resumed["result"]["test_routes"].count("sharing/check_share_job_status") == 1
    assert "sharing/share_folder" not in resumed["result"]["test_routes"]
    assert invoke(tmp_path, anchor, "next")["result"]["action"] == "invite"


def test_top_level_schema_check_rejects_installation_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    import runpy
    import shutil

    copied = tmp_path / "schemas"
    shutil.copytree(ROOT / "schemas", copied)
    monkeypatch.setattr(sys, "argv", ["export_schemas.py", "--check", "--output", str(copied)])
    with pytest.raises(SystemExit) as current:
        runpy.run_path(str(ROOT / "scripts/export_schemas.py"), run_name="__main__")
    assert current.value.code == 0
    (copied / "execution/setup_installation_v1.json").write_bytes(b"{}\n")
    with pytest.raises(SystemExit) as drift:
        runpy.run_path(str(ROOT / "scripts/export_schemas.py"), run_name="__main__")
    assert drift.value.code == 1
    assert "installation-v1" in capsys.readouterr().out
