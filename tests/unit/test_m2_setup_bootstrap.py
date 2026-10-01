"""Fresh isolated processes; trust lives in the test launcher, not the input document."""

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_m2_setup_deployment import clean_startup_environment, installation_fixture

from peru_conflicts.execution.python_environment_policy import capture_document
from peru_conflicts.execution.setup_deployment import Installation
from peru_conflicts.hashing import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "src/peru_conflicts/execution/setup_bootstrap.py"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def admitted_files(tmp_path_factory: pytest.TempPathFactory):
    root, grant, installation, bindings = installation_fixture(
        tmp_path_factory.mktemp("bootstrap-admission")
    )
    pin = json.loads(installation)
    environment = capture_document(sha(canonical_json_bytes(pin["runtime_files"])))
    return root, grant, installation, bindings, canonical_json_bytes(environment)


def launch(
    tmp_path: Path,
    files: tuple[Path, bytes, bytes, bytes, bytes],
    fault: str = "none",
    *,
    diagnostic: bool = False,
) -> subprocess.CompletedProcess[str]:
    _, grant, installation, bindings, environment = files
    pin = json.loads(installation)
    code_prefix = ""
    if fault == "source":
        pin["source_files"]["src/peru_conflicts/__init__.py"] = "0" * 64
    elif fault == "runtime":
        pin["runtime_files"][str(Path(sys.executable).resolve())] = "0" * 64
    elif fault == "expired":
        pin["validity_end"] = "2026-09-23T12:00:00Z"
    elif fault == "revoked":
        pin["revoked"] = True
    elif fault == "proposal":
        data = json.loads(grant)
        data["proposal_raw_sha256"] = "0" * 64
        grant = canonical_json_bytes(data)
        pin["grant_sha256"] = sha(grant)
    elif fault in {"origin", "bytecode", "native_source"}:
        copied = tmp_path / "source"
        for name in ("src", "scripts", "config", "docs", "schemas"):
            shutil.copytree(
                ROOT / name, copied / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        for name in ("uv.lock", "pyproject.toml"):
            shutil.copyfile(ROOT / name, copied / name)
        pin["source_root"] = str(copied)
        if fault == "origin":
            canary = copied / "src/pydantic.py"
            canary.write_text("raise RuntimeError('SYNTHETIC-PRIVATE-CANARY')", encoding="utf-8")
            pin["source_files"]["src/pydantic.py"] = sha(canary.read_bytes())
        elif fault == "native_source":
            extension = copied / "src/peru_conflicts/execution/setup_deployment.pyd"
            extension.write_bytes(b"SYNTHETIC-NOT-A-NATIVE-LIBRARY")
        else:
            target = copied / "src/peru_conflicts/__init__.py"
            original = target.read_bytes()
            target.write_text(
                f"from pathlib import Path; Path({str(tmp_path / 'bytecode-executed')!r}).touch()",
                encoding="utf-8",
            )
            py_compile.compile(
                str(target), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
            )
            target.write_bytes(original)
    installation = (
        Installation.model_validate_json(canonical_json_bytes(pin)).model_dump_json().encode()
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
    for name, value in (
        ("installation", installation),
        ("registry", registry),
        ("grant", grant),
        ("environment", environment),
        ("bindings", bindings),
    ):
        (tmp_path / f"{name}.json").write_bytes(value)
    # Independent launcher pins held OUTSIDE all uploaded documents. No public
    # application selector installs them; a synthetic subprocess owns this trust.
    anchor: dict[str, Any] = {
        "bootstrap_sha256": sha(BOOTSTRAP.read_bytes()),
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
    if fault in {"installation_pin", "registry_pin", "environment_pin", "bootstrap_pin"}:
        anchor[fault.replace("_pin", "_sha256")] = "0" * 64
    if fault == "installation_bytes":
        (tmp_path / "installation.json").write_bytes(installation + b" ")
    if fault == "search":
        code_prefix = f"sys.path.insert(0, {str(tmp_path)!r})"
        (tmp_path / "typing.py").write_text(
            f"from pathlib import Path; Path({str(tmp_path / 'search-executed')!r}).touch()",
            encoding="utf-8",
        )
    if fault == "preimport":
        code_prefix = "sys.modules['pydantic'] = object()"
    if fault == "preimport_dependency":
        code_prefix = "sys.modules['typing_extensions'] = types.ModuleType('typing_extensions')"
    if fault == "import_hook":
        code_prefix = "sys.meta_path.insert(0, object())"
    if fault == "loader_override":
        code_prefix = "os.environ['LD_LIBRARY_PATH'] = 'SYNTHETIC-OVERRIDE'"
    code = f"""
import sys, os, hashlib, types
from pathlib import Path
from datetime import datetime
def deny(event, args):
    if event.startswith('socket.') and event != 'socket.gethostname':
        raise AssertionError('NETWORK_FORBIDDEN')
sys.addaudithook(deny)
# Process-local test controls are not trust inputs; never process site hooks.
for key in tuple(os.environ):
    if key.lower().startswith(('python', 'pytest')):
        del os.environ[key]
anchor = {anchor!r}
anchor['initial_paths'] = list(sys.path)
{code_prefix}
original = Path({str(BOOTSTRAP)!r}).read_bytes()
if hashlib.sha256(original).hexdigest() != anchor['bootstrap_sha256']:
    print('REJECT:BOOTSTRAP:0'); raise SystemExit(0)
entry_path = Path({str(ROOT / "scripts/start_m2_setup.py")!r})
entry_raw = entry_path.read_bytes()
expected_entry = {sha((ROOT / "scripts/start_m2_setup.py").read_bytes())!r}
assert hashlib.sha256(entry_raw).hexdigest() == expected_entry
entry = types.ModuleType('_trusted_test_entry')
entry.__file__ = str(entry_path)
exec(compile(entry_raw, str(entry_path), 'exec'), entry.__dict__)
calls = []
def bindings():
    calls.append('private')
    if {fault == "private_error"!r}:
        raise RuntimeError('SYNTHETIC-PRIVATE-CANARY')
    return Path({str(tmp_path / "bindings.json")!r}).read_bytes()
{runtime_observer() if diagnostic else ""}
try:
    context = entry.launch(anchor, bindings,
        clock=lambda: datetime.fromisoformat('2026-09-23T12:00:00+00:00'))
except ValueError as error:
    assert error.__context__ is None and error.__cause__ is None
    assert 'peru_conflicts.execution.setup_transport' not in sys.modules
    print('REJECT:' + str(error) + ':' + str(len(calls)))
else:
    assert 'peru_conflicts.execution.setup_offline' not in sys.modules
    assert 'peru_conflicts.execution.setup_transport' not in sys.modules
    assert type(context).__name__ == 'AdmittedContext'
    grant = context.check(Path({pin["store"]["path"]!r}), Path({pin["checkpoint"]["path"]!r}))
    assert grant.run_ref == 'test-installed-run'
    print('ADMITTED:' + str(len(calls)))
finally:
    {"report_runtime()" if diagnostic else "pass"}
"""
    process = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
        env=clean_startup_environment(),
    )
    assert "SYNTHETIC-PRIVATE-CANARY" not in process.stdout + process.stderr
    assert not (tmp_path / "search-executed").exists()
    return process


def runtime_observer() -> str:
    """Observe unchanged bootstrap locals; never initialize sysconfig before it does."""
    return r"""
import json
observed = {}
stages = []
def observe(frame, event, arg):
    if frame.f_code.co_filename != str(entry_path.parent.parent /
            'src/peru_conflicts/execution/setup_bootstrap.py') or frame.f_code.co_name != 'start':
        return None
    state = frame.f_locals
    stage = state.get('stage')
    if stage and (not stages or stages[-1]['stage'] != stage):
        config = sys.modules.get('sysconfig')
        stages.append({'stage': stage, 'prefix': sys.prefix, 'exec_prefix': sys.exec_prefix,
            'sysconfig_loaded': config is not None,
            'sysconfig_cached': config is not None and
                getattr(config, '_CONFIG_VARS', None) is not None})
    if event == 'return':
        observed.update(state)
    if event == 'exception':
        message = str(arg[1])
        if message in {'runtime inventory', 'aliased input', 'unmeasured dependency executable',
                'environment identity', 'runtime import prefix', 'module origin'}:
            observed['predicate'] = message
    return observe
def report_runtime():
    sys.settrace(None)
    import sysconfig
    executable = Path(sys.executable)
    venv = executable.parent.parent
    roots = [(venv, '<venv>'), (Path(sys.base_prefix), '<base>'),
        (entry_path.parent.parent, '<source>')]
    def label(value):
        path = Path(value)
        for root, name in roots:
            if path.is_relative_to(root):
                return name + '/' + path.relative_to(root).as_posix()
        return '<outside>:' + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    links = []
    cursor = executable
    for _ in range(8):
        if not cursor.is_symlink():
            break
        target = cursor.readlink()
        cursor = target if target.is_absolute() else cursor.parent / target
        links.append(label(cursor))
    config_path = venv / 'pyvenv.cfg'
    config = config_path.read_bytes() if config_path.is_file() else b''
    expected = observed.get('pin', {}).get('runtime_files', {})
    actual = observed.get('runtime', {})
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    different = sorted(p for p in set(actual) & set(expected) if actual[p] != expected[p])
    def sample(paths):
        return [{'path': label(p), 'expected': expected.get(p), 'actual': actual.get(p)}
            for p in paths[:8]]
    for stage in stages:
        stage['prefix'] = label(stage['prefix'])
        stage['exec_prefix'] = label(stage['exec_prefix'])
    report = {'lexical_executable': label(executable),
        'resolved_executable': label(executable.resolve()), 'link_chain': links,
        'base_executable': label(sys._base_executable), 'base_prefix': label(sys.base_prefix),
        'version': sys.version, 'flags': [sys.flags.isolated, sys.flags.no_site,
            sys.flags.dont_write_bytecode],
        'configuration_present': bool(config),
        'configuration_sha256': hashlib.sha256(config).hexdigest(),
        'stages': stages, 'predicate': observed.get('predicate'),
        'parent_purelib': PARENT_PURELIB,
        'child_purelib_after': label(sysconfig.get_path('purelib')),
        'child_platlib_after': label(sysconfig.get_path('platlib')),
        'observed_site': label(observed['site']) if 'site' in observed else None,
        'runtime_counts': {'expected': len(expected), 'actual': len(actual),
            'missing': len(missing), 'extra': len(extra), 'different': len(different)},
        'missing_sample': sample(missing), 'extra_sample': sample(extra),
        'different_sample': sample(different), 'private_calls': len(calls),
        'project_imported': 'peru_conflicts' in sys.modules,
        'provider_imported': 'peru_conflicts.execution.setup_transport' in sys.modules}
    print('M2_RUNTIME_PROFILE ' + json.dumps(report, sort_keys=True), file=sys.stderr, flush=True)
sys.settrace(observe)
""".replace("PARENT_PURELIB", repr(_parent_package_root()))


def _parent_package_root() -> str:
    import sysconfig

    site = Path(sysconfig.get_path("purelib"))
    venv = Path(sys.executable).parent.parent
    if site.is_relative_to(venv):
        return "<venv>/" + site.relative_to(venv).as_posix()
    return "<outside>"


def test_verified_startup_reaches_existing_context(
    tmp_path: Path, admitted_files: Any, capsys: pytest.CaptureFixture[str]
):
    result = launch(tmp_path, admitted_files, diagnostic=True)
    with capsys.disabled():
        print(result.stderr, end="", flush=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ADMITTED:1"


@pytest.mark.parametrize(
    "override", ["LD_LIBRARY_PATH", "OPENSSL_CONF", "DYLD_LIBRARY_PATH", "M2_REPO"]
)
def test_synthetic_launcher_does_not_inherit_startup_overrides(
    tmp_path: Path, admitted_files: Any, monkeypatch: pytest.MonkeyPatch, override: str
):
    # The trusted synthetic launcher must establish its own clean environment;
    # production must still refuse these overrides, not inherit test-parent state.
    monkeypatch.setenv(override, "SYNTHETIC-OVERRIDE")
    result = launch(tmp_path, admitted_files)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ADMITTED:1"


def test_m2_repo_override_rejected_and_restored(monkeypatch: pytest.MonkeyPatch):
    import os

    before = os.environ.get("M2_REPO")
    code = f"""
import sys, types
from pathlib import Path
bootstrap = types.ModuleType('_startup_probe')
bootstrap.__file__ = {str(BOOTSTRAP)!r}
exec(compile(Path(bootstrap.__file__).read_bytes(), bootstrap.__file__, 'exec'),
    bootstrap.__dict__)
try:
    bootstrap._startup()
except ValueError as error:
    print(str(error))
else:
    print('VALID')
assert 'peru_conflicts' not in sys.modules
"""
    with monkeypatch.context() as scoped:
        scoped.setenv("M2_REPO", "SYNTHETIC-OVERRIDE")
        clean = clean_startup_environment()
        inherited = dict(clean, M2_REPO="SYNTHETIC-OVERRIDE")
        for environment, expected in ((inherited, "startup override"), (clean, "VALID")):
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c", code],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == expected
        assert os.environ["M2_REPO"] == "SYNTHETIC-OVERRIDE"
    assert os.environ.get("M2_REPO") == before


def test_unverified_bytecode_cannot_replace_verified_source(tmp_path: Path, admitted_files: Any):
    result = launch(tmp_path, admitted_files, "bytecode")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ADMITTED:1"
    assert not (tmp_path / "bytecode-executed").exists()


@pytest.mark.parametrize(
    ("fault", "stage", "private_calls"),
    [
        ("bootstrap_pin", "BOOTSTRAP", 0),
        ("installation_pin", "REGISTRY", 0),
        ("installation_bytes", "INSTALLATION", 0),
        ("registry_pin", "REGISTRY", 0),
        ("expired", "INSTALLATION", 0),
        ("revoked", "INSTALLATION", 0),
        ("source", "SOURCE", 0),
        ("native_source", "SOURCE", 0),
        ("runtime", "RUNTIME", 0),
        ("environment_pin", "ENVIRONMENT", 0),
        ("origin", "ORIGIN", 0),
        ("search", "STARTUP", 0),
        ("preimport", "STARTUP", 0),
        ("preimport_dependency", "STARTUP", 0),
        ("import_hook", "STARTUP", 0),
        ("loader_override", "STARTUP", 0),
        ("proposal", "ADMISSION", 0),
        ("private_error", "ADMISSION", 1),
    ],
)
def test_preimport_rejection_stage(
    tmp_path: Path,
    admitted_files: Any,
    fault: str,
    stage: str,
    private_calls: int,
):
    result = launch(tmp_path, admitted_files, fault)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"REJECT:{stage}:{private_calls}"


@pytest.mark.parametrize("flags", [[], ["-I"], ["-I", "-S"]])
def test_startup_requires_all_isolation_flags(tmp_path: Path, flags: list[str]):
    result = subprocess.run(
        [sys.executable, *flags, str(ROOT / "scripts/start_m2_setup.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=clean_startup_environment(),
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "M2 startup rejected: STARTUP"


@pytest.mark.parametrize("override", ["argument", "environment", "pythonpath"])
def test_public_entry_cannot_select_trust(tmp_path: Path, override: str):
    environment = clean_startup_environment()
    arguments: list[str] = []
    if override == "argument":
        arguments = ["--registry", "SYNTHETIC-PRIVATE-CANARY"]
    else:
        environment["M2_INSTALLATION" if override == "environment" else "PYTHONPATH"] = str(
            tmp_path
        )
    canary = tmp_path / "imported"
    (tmp_path / "peru_conflicts.py").write_text(
        f"from pathlib import Path; Path({str(canary)!r}).touch()", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ROOT / "scripts/start_m2_setup.py"), *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 2
    stage = "ARGUMENTS" if override == "argument" else "STARTUP"
    assert result.stderr.strip() == f"M2 startup rejected: {stage}"
    assert not canary.exists()


def test_entry_rejects_substituted_bootstrap_before_execution(tmp_path: Path):
    script = tmp_path / "scripts/start_m2_setup.py"
    script.parent.mkdir()
    script.write_bytes((ROOT / "scripts/start_m2_setup.py").read_bytes())
    bootstrap = tmp_path / "src/peru_conflicts/execution/setup_bootstrap.py"
    bootstrap.parent.mkdir(parents=True)
    marker = tmp_path / "unverified-executed"
    bootstrap.write_text(
        f"from pathlib import Path; Path({str(marker)!r}).touch()", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=clean_startup_environment(),
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "M2 startup rejected: BOOTSTRAP"
    assert not marker.exists()


def test_distributed_bootstrap_closed_before_project_import(tmp_path: Path):
    script = Path(__file__).resolve().parents[2] / "scripts/start_m2_setup.py"
    canary = tmp_path / "imported"
    (tmp_path / "peru_conflicts.py").write_text(
        f"from pathlib import Path; Path({str(canary)!r}).touch()", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=clean_startup_environment(),
    )
    assert result.returncode == 2
    assert result.stderr.strip() == "M2 startup rejected: CLOSED"
    assert not canary.exists()


def test_clean_subprocess_reports_initial_startup_boundary(capsys: pytest.CaptureFixture[str]):
    """Expose the exact pre-import predicate if a host refuses legitimate startup."""
    import os

    code = f"""
import sys, os, types, json
from pathlib import Path
from datetime import datetime
def deny(event, args):
    if event.startswith('socket.') and event != 'socket.gethostname':
        raise AssertionError('NETWORK_FORBIDDEN')
sys.addaudithook(deny)
raw = Path({str(BOOTSTRAP)!r}).read_bytes()
bootstrap = types.ModuleType('_startup_probe')
bootstrap.__file__ = {str(BOOTSTRAP)!r}
exec(compile(raw, bootstrap.__file__, 'exec'), bootstrap.__dict__)
try:
    bootstrap._startup()
except ValueError as error:
    predicate = str(error)
else:
    predicate = 'VALID'
base = Path(sys.base_prefix).resolve()
foreign = []
for name, module in tuple(sys.modules.items()):
    if name == '__main__' or name in ('typing.io', 'typing.re'):
        continue
    spec = getattr(module, '__spec__', None)
    if spec is not None and spec.origin in ('built-in', 'frozen'):
        continue
    origin = getattr(module, '__file__', None)
    if origin is None or not Path(origin).resolve().is_relative_to(base):
        foreign.append([name, origin])
print(json.dumps({{'predicate': predicate, 'executable': sys.executable,
    'base_prefix': sys.base_prefix, 'initial_paths': sys.path,
    'resolved_paths': [str(Path(p).resolve()) for p in sys.path],
    'isolated': sys.flags.isolated, 'no_site': sys.flags.no_site,
    'dont_write_bytecode': sys.flags.dont_write_bytecode,
    'override_names': [k for k in os.environ if k.lower().startswith(
        ('python', 'openssl_', 'ld_', 'dyld_', 'm2_'))],
    'foreign_modules': foreign}}))
"""
    legacy_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.lower().startswith(("python", "pytest"))
    }
    for label, environment in (
        ("legacy-inherited", legacy_environment),
        ("clean-test-launcher", clean_startup_environment()),
    ):
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", code],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        observed = json.loads(result.stdout)
        with capsys.disabled():
            print("M2_STARTUP_PROFILE " + label + " " + json.dumps(observed), flush=True)
        if label == "clean-test-launcher":
            assert observed["predicate"] == "VALID", observed
