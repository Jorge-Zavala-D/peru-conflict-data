"""Isolation and independent trust for the neutral runtime candidate."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

import pytest
from pydantic import BaseModel
from test_m2_annotation import blank, complete, form, populated
from test_m2_benchmark_alignment import invented_complete_population

from peru_conflicts.execution import neutral_forms
from peru_conflicts.execution.packages import FORM_HEADERS
from peru_conflicts.execution.references import sha256
from peru_conflicts.hashing import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[2]


def json_bytes(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def test_runtime_builder_exists_and_emits_deterministic_candidate(tmp_path: Path) -> None:
    spec = importlib.util.find_spec("peru_conflicts.execution.runtime_build")
    assert spec is not None, "isolated runtime builder is missing"
    from peru_conflicts.execution.runtime_build import build_runtime

    left = build_runtime(tmp_path / "left")
    right = build_runtime(tmp_path / "right")
    assert left == right
    assert left.runtime_sha256
    assert left.file_hashes
    assert hasattr(left, "interpreter_sha256"), "independent interpreter binary pin is missing"


@pytest.fixture
def isolated(tmp_path: Path) -> tuple[list[str], Path, Path]:
    assert importlib.util.find_spec("peru_conflicts.execution.runtime_cli") is not None, (
        "trusted isolated launcher is missing"
    )
    from peru_conflicts.execution.runtime_build import (
        build_neutral_view,
        build_runtime,
        dependency_files,
        write_new_tree,
    )

    runtime = build_runtime(tmp_path / "runtime")
    dependencies, _ = dependency_files()
    write_new_tree(tmp_path / "dependencies", dependencies)
    view = build_neutral_view(blank(), tmp_path / "package")
    launcher = tmp_path / "trusted_launcher.py"
    shutil.copyfile(ROOT / "src/peru_conflicts/execution/runtime_cli.py", launcher)
    receipt = {
        "kind": "UNISSUED_RUNTIME_REHEARSAL",
        "runtime_sha256": runtime.runtime_sha256,
        "dependency_sha256": runtime.dependency_sha256,
        "launcher_sha256": runtime.launcher_sha256,
        "interpreter_sha256": runtime.interpreter_sha256,
        "python_environment_sha256": runtime.python_environment_sha256,
        "python_environment_manifest_sha256": runtime.python_environment_manifest_sha256,
        "view_sha256": view.view_sha256,
        "original_package_sha256": view.original_package_sha256,
        "contract_sha256": runtime.contract_sha256,
        "role": "annotator-a",
        "run_id": "synthetic-run",
    }
    receipt_bytes = json_bytes(receipt)
    (tmp_path / "receipt.json").write_bytes(receipt_bytes)
    command = [
        str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
        "-I",
        "-S",
        "-B",
        str(launcher),
        "--runtime",
        str(tmp_path / "runtime"),
        "--dependencies",
        str(tmp_path / "dependencies"),
        "--package",
        str(tmp_path / "package"),
        "--issuance",
        str(tmp_path / "receipt.json"),
        "--issuance-sha256",
        sha256(receipt_bytes),
        "--role",
        "annotator-a",
    ]
    for key in (
        "runtime_sha256",
        "dependency_sha256",
        "launcher_sha256",
        "interpreter_sha256",
        "python_environment_sha256",
        "python_environment_manifest_sha256",
        "view_sha256",
        "contract_sha256",
    ):
        command += ["--" + key.replace("_", "-"), str(receipt[key])]
    command += ["--package-sha256", view.original_package_sha256]
    return command, tmp_path / "package", tmp_path


def run(isolated: tuple[list[str], Path, Path], *args: str) -> subprocess.CompletedProcess[str]:
    command, _, root = isolated
    return subprocess.run(
        [*command, *args], cwd=root, text=True, encoding="utf-8", capture_output=True, timeout=30
    )


@pytest.mark.parametrize("change", ["manifest", "aggregate", "stdlib", "identity", "production"])
def test_substituted_python_environment_rejected_before_output(
    isolated: tuple[list[str], Path, Path], change: str
) -> None:
    """Even repinning runtime bytes cannot override independent environment pins."""
    runtime_root = isolated[2] / "runtime"
    manifest_path = runtime_root / "RUNTIME_MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    if change == "manifest":
        environment_path = runtime_root / "PYTHON_ENVIRONMENT.json"
        environment_path.write_bytes(b"{}\n")
        manifest["file_hashes"]["PYTHON_ENVIRONMENT.json"] = sha256(environment_path.read_bytes())
    elif change == "aggregate":
        manifest["python_environment_sha256"] = "0" * 64
    else:
        environment_path = runtime_root / "PYTHON_ENVIRONMENT.json"
        environment = json.loads(environment_path.read_bytes())
        if change == "stdlib":
            name = environment["stdlib_path"] + "/os.py"
            environment["file_hashes"][name] = "0" * 64
        elif change == "identity":
            environment["identity"]["build"] = "different CPython build"
        else:
            environment["production_approved"] = True
        environment.pop("python_environment_sha256")
        environment["python_environment_sha256"] = sha256(json_bytes(environment))
        environment_path.write_bytes(json_bytes(environment))
        manifest["python_environment"] = environment
        manifest["python_environment_sha256"] = environment["python_environment_sha256"]
        manifest["python_environment_manifest_sha256"] = sha256(environment_path.read_bytes())
        manifest["file_hashes"]["PYTHON_ENVIRONMENT.json"] = sha256(environment_path.read_bytes())
    manifest["runtime_sha256"] = sha256(
        json_bytes({"policy": manifest["policy"], "file_hashes": manifest["file_hashes"]})
    )
    manifest_path.write_bytes(json_bytes(manifest))
    receipt_path = isolated[2] / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["runtime_sha256"] = manifest["runtime_sha256"]
    if change in {"stdlib", "identity", "production"}:
        # All claims and supplied pins are self-consistent, but do not describe
        # the actual running installation (or falsely claim production approval).
        for key in ("python_environment_sha256", "python_environment_manifest_sha256"):
            receipt[key] = manifest[key]
            isolated[0][isolated[0].index("--" + key.replace("_", "-")) + 1] = manifest[key]
    receipt_path.write_bytes(json_bytes(receipt))
    for key, value in {
        "--runtime-sha256": manifest["runtime_sha256"],
        "--issuance-sha256": sha256(receipt_path.read_bytes()),
    }.items():
        isolated[0][isolated[0].index(key) + 1] = value
    result = run(isolated, "validate")
    assert result.returncode != 0
    assert not result.stdout


def test_isolated_commands_and_incomplete_zero_semantics(
    isolated: tuple[list[str], Path, Path],
) -> None:
    page = run(isolated, "page", "--report", "260", "--page", "1")
    assert page.returncode == 0, page.stderr
    assert (
        page.stdout
        == "1: Same name. First invented block.\n2: Same name. Second invented block.\n3: \n"
    )
    position = run(
        isolated, "position", "--report", "260", "--page", "1", "--line", "2", "--column", "1"
    )
    assert position.returncode == 0, position.stderr
    assert json.loads(position.stdout)["codepoint_offset"] == 33
    draft = run(isolated, "validate")
    assert draft.returncode == 0, draft.stderr
    assert json.loads(draft.stdout)["complete"] is False
    assert run(isolated, "validate", "--require-complete").returncode != 0
    assert run(isolated, "slots").stdout == FORM_HEADERS["annotations.csv"] + "\n"
    template = run(isolated, "inspection-template")
    assert template.returncode == 0, template.stderr
    assert len(template.stdout.splitlines()) == 12
    package = blank()
    complete(package)
    isolated[1].joinpath("inspection.csv").write_bytes(package["inspection.csv"])
    assert json.loads(run(isolated, "validate", "--require-complete").stdout)["complete"] is True


def test_launch_uses_independent_base_interpreter(isolated: tuple[list[str], Path, Path]) -> None:
    assert not Path(isolated[0][0]).resolve().is_relative_to(ROOT)


@pytest.mark.parametrize(
    "argument",
    [
        "--runtime-sha256",
        "--dependency-sha256",
        "--launcher-sha256",
        "--interpreter-sha256",
        "--view-sha256",
        "--package-sha256",
        "--contract-sha256",
        "--issuance-sha256",
        "--role",
    ],
)
def test_independent_stale_pins_fail_before_commands(
    isolated: tuple[list[str], Path, Path], argument: str
) -> None:
    command = isolated[0]
    command[command.index(argument) + 1] = "annotator-b" if argument == "--role" else "0" * 64
    result = run(isolated, "page", "--report", "260", "--page", "1")
    assert result.returncode != 0
    assert not result.stdout


@pytest.mark.parametrize(
    "name",
    [
        "references/260/0001.txt",
        "INSTRUCTIONS.md",
        "FORM_GUIDE.md",
        "DATE_PAIR_INTERPRETATION.md",
        "DATE_SEMANTICS_ADDENDUM.md",
        "annotations.csv",
        "extra.txt",
    ],
)
def test_modified_package_files_are_rejected(
    isolated: tuple[list[str], Path, Path], name: str
) -> None:
    isolated[1].joinpath(name).write_bytes(b"changed\n")
    assert run(isolated, "validate").returncode != 0


def test_neutral_projection_preserves_normative_date_suffix(
    isolated: tuple[list[str], Path, Path],
) -> None:
    original = blank()
    data = isolated[1].joinpath("DATE_PAIR_INTERPRETATION.md").read_bytes()
    assert data.split(b"\n", 2)[2] == b"".join(
        original["DATE_PAIR_INTERPRETATION.md"].splitlines(keepends=True)[9:]
    )
    assert b"Jorge" not in data
    assert isolated[1].joinpath("INSTRUCTIONS.md").read_bytes() == original["INSTRUCTIONS.md"]
    marker = b"## discoveries.csv\n"
    assert (
        isolated[1].joinpath("FORM_GUIDE.md").read_bytes().split(marker, 1)[1]
        == original["FORM_GUIDE.md"].split(marker, 1)[1]
    )
    assert (
        isolated[1].joinpath("DATE_SEMANTICS_ADDENDUM.md").read_bytes()
        == original["DATE_SEMANTICS_ADDENDUM.md"]
    )


@pytest.mark.parametrize("command", ["lock", "launch", "extract", "search", "score"])
def test_prohibited_commands_unavailable(
    isolated: tuple[list[str], Path, Path], command: str
) -> None:
    assert run(isolated, command).returncode != 0


def test_unclosed_quoted_csv_is_rejected_by_shared_core() -> None:
    package = populated()
    header = FORM_HEADERS["evidence.csv"]
    package["evidence.csv"] = (
        header
        + "\n"
        + ",".join(
            ["e1", "260", "1", "synthetic-section", "page_only"] + [""] * 11 + ['"unfinished']
        )
    ).encode()
    with pytest.raises(ValueError):
        neutral_forms.rows(package, "evidence.csv")


def install_forms(isolated: tuple[list[str], Path, Path], package: dict[str, bytes]) -> None:
    for name in FORM_HEADERS:
        isolated[1].joinpath(name).write_bytes(package[name])


def test_every_family_matches_canonical_neutral_output(
    isolated: tuple[list[str], Path, Path],
) -> None:
    package = invented_complete_population()
    install_forms(isolated, package)
    expected_package = neutral_forms.PackageManifest.model_validate_json(
        package["PACKAGE_MANIFEST.json"]
    )
    expected = neutral_forms.validate_neutral_forms(
        package, expected_package=expected_package, require_complete=True
    )
    actual = run(isolated, "validate", "--require-complete")
    assert actual.returncode == 0, actual.stderr
    output = json.loads(actual.stdout)
    for field in ("discoveries", "records", "unresolved", "inspections", "complete"):
        assert output[field] == expected.model_dump(mode="json")[field]
    assert {value["domain_object_type"] for value in output["records"][0]["annotations"]} == {
        "actor",
        "alert",
        "agreement",
        "case_observation",
        "case_name",
        "dp_action",
        "demand",
        "dialogue_event",
        "location",
        "mediation_observation",
        "protest_event",
        "violence_event",
    }


@pytest.mark.parametrize(
    "state,kind,value,comment",
    [
        ("observed", "string", '=1+1, "quoted"\n0012\n2026-01-02\ne\u0301 Perú', ""),
        ("explicit_zero", "number", "0", ""),
        ("not_reported", "", "", ""),
        ("not_applicable", "", "", ""),
        ("source_ambiguous", "string", "0012", "Two readings retained"),
        ("structurally_unavailable", "", "", ""),
        ("illegible_uninspectable", "", "", ""),
        ("annotation_uncertain", "string", "01/02/03", "Uncertain source"),
        ("observed", "boolean", "true", ""),
        ("observed", "json", '{"original":"0012","unknown":null}', ""),
    ],
)
def test_states_types_and_literal_csv_match(
    isolated: tuple[list[str], Path, Path], state: str, kind: str, value: str, comment: str
) -> None:
    package = populated()
    values = neutral_forms.rows(package, "annotations.csv")
    values[0].update(state=state, value_type=kind, original_value=value, comment=comment)
    package["annotations.csv"] = form("annotations.csv", values)
    install_forms(isolated, package)
    expected = neutral_forms.validate_neutral_forms(
        package,
        expected_package=neutral_forms.PackageManifest.model_validate_json(
            package["PACKAGE_MANIFEST.json"]
        ),
        require_complete=True,
    )
    result = run(isolated, "validate", "--require-complete")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["records"] == expected.model_dump(mode="json")["records"]
    raw = json.loads(result.stdout)["records"][0]["annotations"][0]["raw_value_json"]
    if kind == "string":
        assert json.loads(raw) == value
    elif kind == "number":
        assert raw == "0"
    elif kind == "boolean":
        assert raw == "true"


@pytest.mark.parametrize(
    "granularity,fields",
    [
        ("page_only", {"rationale": "Whole page manually inspected"}),
        ("span", {"start_line": "1", "start_column": "1", "end_line": "1", "end_column": "5"}),
        ("bounding_box", {"x0": "0", "y0": "0", "x1": "10", "y1": "10"}),
        ("table_cell", {"table": "Literal table", "row": "0012", "column": "Original column"}),
    ],
)
def test_typed_evidence_matches_canonical(
    isolated: tuple[list[str], Path, Path], granularity: str, fields: dict[str, str]
) -> None:
    package = populated()
    evidence = neutral_forms.rows(package, "evidence.csv")[0]
    evidence.update(granularity=granularity, **fields)
    package["evidence.csv"] = form("evidence.csv", [evidence])
    install_forms(isolated, package)
    expected = neutral_forms.validate_neutral_forms(
        package,
        expected_package=neutral_forms.PackageManifest.model_validate_json(
            package["PACKAGE_MANIFEST.json"]
        ),
        require_complete=True,
    )
    result = run(isolated, "validate", "--require-complete")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["records"] == expected.model_dump(mode="json")["records"]


@pytest.mark.parametrize(
    "area,name",
    [
        ("runtime", "peru_conflicts/execution/neutral_forms.py"),
        ("dependencies", "typing_extensions.py"),
    ],
)
def test_tampered_code_is_not_executed(
    isolated: tuple[list[str], Path, Path], area: str, name: str
) -> None:
    marker = isolated[2] / "code_executed"
    isolated[2].joinpath(area, name).write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8"
    )
    assert run(isolated, "validate").returncode != 0
    assert not marker.exists()


def test_self_consistent_substitution_does_not_repin_itself(
    isolated: tuple[list[str], Path, Path],
) -> None:
    root = isolated[1]
    view = json.loads(root.joinpath("NEUTRAL_VIEW.json").read_bytes())
    root.joinpath("INSTRUCTIONS.md").write_bytes(b"Unauthorized instruction replacement\n")
    view["file_hashes"]["INSTRUCTIONS.md"] = sha256(root.joinpath("INSTRUCTIONS.md").read_bytes())
    del view["view_sha256"]
    view["view_sha256"] = sha256(json_bytes(view))
    root.joinpath("NEUTRAL_VIEW.json").write_bytes(json_bytes(view))
    receipt_path = isolated[2] / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["view_sha256"] = view["view_sha256"]
    receipt_path.write_bytes(json_bytes(receipt))
    assert run(isolated, "validate").returncode != 0


def test_aliased_package_directory_is_rejected(isolated: tuple[list[str], Path, Path]) -> None:
    link = isolated[2] / "package-alias"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(isolated[1])], capture_output=True
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(isolated[1], target_is_directory=True)
    isolated[0][isolated[0].index("--package") + 1] = str(link)
    assert run(isolated, "validate").returncode != 0


def test_hardlinked_receipt_is_rejected_before_output(
    isolated: tuple[list[str], Path, Path],
) -> None:
    alias = isolated[2] / "receipt-alias.json"
    os.link(isolated[2] / "receipt.json", alias)
    assert alias.stat().st_nlink == 2
    isolated[0][isolated[0].index("--issuance") + 1] = str(alias)
    result = run(isolated, "validate")
    assert result.returncode != 0
    assert not result.stdout


def test_nonregular_receipt_is_rejected_before_output(
    isolated: tuple[list[str], Path, Path],
) -> None:
    directory = isolated[2] / "receipt-directory"
    directory.mkdir()
    isolated[0][isolated[0].index("--issuance") + 1] = str(directory)
    result = run(isolated, "validate")
    assert result.returncode != 0
    assert not result.stdout


def test_single_receipt_capture_preserves_normal_bytes(tmp_path: Path) -> None:
    from peru_conflicts.execution import runtime_cli

    assert hasattr(runtime_cli, "read_file"), "retained single-file capture is missing"
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b'{"kind":"UNISSUED_RUNTIME_REHEARSAL"}\n')
    with ExitStack() as stack:
        assert runtime_cli.read_file(receipt, stack) == b'{"kind":"UNISSUED_RUNTIME_REHEARSAL"}\n'


@pytest.mark.parametrize("replacement_kind", ["regular", "nonregular"])
def test_single_receipt_capture_rejects_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replacement_kind: str
) -> None:
    from peru_conflicts.execution import runtime_cli

    assert hasattr(runtime_cli, "read_file"), "retained single-file capture is missing"
    folder = tmp_path / "receipt-parent"
    folder.mkdir()
    receipt = folder / "receipt.json"
    receipt.write_bytes(b'{"original":true}\n')
    original_open = os.open
    attempted = False

    def replace_before_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal attempted
        if str(path).endswith("receipt.json"):
            attempted = True
            replacement = tmp_path / "replacement"
            if replacement_kind == "regular":
                replacement.write_bytes(b'{"changed":true}\n')
            elif os.name == "nt":
                replacement.mkdir()
            else:
                os.mkfifo(replacement)
            try:
                receipt.unlink()
                replacement.rename(receipt)
            except PermissionError:
                raise ValueError("retained receipt custody blocked replacement") from None
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", replace_before_open)
    with ExitStack() as stack, pytest.raises((ValueError, OSError)):
        runtime_cli.read_file(receipt, stack)
    assert attempted


@pytest.mark.parametrize(
    "name", ["../escape", "a/../b", "/absolute", "a\\b", "C:escape", "a//b", "a/./b"]
)
def test_traversal_is_rejected(name: str) -> None:
    from peru_conflicts.execution.runtime_cli import relative_name

    with pytest.raises(ValueError):
        relative_name(name)


def test_replacement_during_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from peru_conflicts.execution import runtime_cli

    root = tmp_path / "capture"
    root.mkdir()
    source = root / "input.txt"
    source.write_bytes(b"original")
    original_open = os.open
    attempted = False

    def replace_before_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal attempted
        if str(path).endswith("input.txt"):
            attempted = True
            # Windows retained custody prevents this rename; POSIX must catch
            # the replacement through before/opened/bound descriptor identities.
            replacement = tmp_path / "replacement.txt"
            replacement.write_bytes(b"changed")
            try:
                replacement.replace(source)
            except PermissionError:
                raise ValueError("retained read custody blocked replacement") from None
        return original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", replace_before_open)
    with ExitStack() as stack, pytest.raises(ValueError):
        runtime_cli.read_tree(root, stack)
    assert attempted


@pytest.mark.parametrize(
    "contamination", ["import subprocess", "partition_role = 'protocol_pilot'"]
)
def test_source_selection_rejects_new_capabilities_or_private_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contamination: str
) -> None:
    from peru_conflicts.execution import runtime_build

    target = tmp_path / "src/peru_conflicts/models"
    target.mkdir(parents=True)
    source = ROOT.joinpath("src/peru_conflicts/models/common.py").read_text(encoding="utf-8")
    target.joinpath("common.py").write_text(
        source.replace(
            "class StrictModel(BaseModel):", "class StrictModel(BaseModel):\n    " + contamination
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_build, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        runtime_build.selected_source("models.common")


def test_manifest_models_reject_self_inconsistent_identities(tmp_path: Path) -> None:
    from peru_conflicts.execution.runtime_build import (
        NeutralViewIdentity,
        RuntimeManifest,
        build_neutral_view,
        build_runtime,
    )

    runtime = build_runtime(tmp_path / "runtime")
    view = build_neutral_view(blank(), tmp_path / "package")
    for value, model, field in [
        (runtime, RuntimeManifest, "runtime_sha256"),
        (view, NeutralViewIdentity, "view_sha256"),
    ]:
        payload = value.model_dump(mode="json")
        payload[field] = "0" * 64
        with pytest.raises(ValueError):
            model.model_validate_json(json_bytes(payload))


@pytest.mark.parametrize("family,prefix", [("dp_action", "action"), ("alert", "alert")])
@pytest.mark.parametrize(
    "date_state,precision_state,accepted",
    [
        ("observed", "observed", True),
        ("observed", "annotation_uncertain", True),
        ("observed", "source_ambiguous", True),
        ("observed", "illegible_uninspectable", True),
        ("observed", "not_reported", False),
        ("not_reported", "observed", False),
        ("not_reported", "not_reported", True),
        ("explicit_zero", "observed", False),
    ],
)
def test_date_pair_outcomes_match_canonical(
    isolated: tuple[list[str], Path, Path],
    family: str,
    prefix: str,
    date_state: str,
    precision_state: str,
    accepted: bool,
) -> None:
    package = invented_complete_population()
    values = neutral_forms.rows(package, "annotations.csv")
    for row in values:
        if row["field_name"] not in {
            f"{family}.{prefix}_date_original",
            f"{family}.{prefix}_date_precision_original",
        }:
            continue
        state = date_state if row["field_name"].endswith("_date_original") else precision_state
        row.update(
            state=state,
            value_type="string"
            if state == "observed"
            else "number"
            if state == "explicit_zero"
            else "",
            original_value="2026-01-02"
            if state == "observed"
            else "0"
            if state == "explicit_zero"
            else "",
            comment="Retained uncertainty",
        )
    package["annotations.csv"] = form("annotations.csv", values)
    install_forms(isolated, package)
    manifest = neutral_forms.PackageManifest.model_validate_json(package["PACKAGE_MANIFEST.json"])
    if accepted:
        expected = neutral_forms.validate_neutral_forms(
            package, expected_package=manifest, require_complete=True
        )
        result = run(isolated, "validate", "--require-complete")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["records"] == expected.model_dump(mode="json")["records"]
    else:
        with pytest.raises(ValueError):
            neutral_forms.validate_neutral_forms(
                package, expected_package=manifest, require_complete=True
            )
        assert run(isolated, "validate", "--require-complete").returncode != 0


def test_unresolved_discovery_and_boundary_changes_match(
    isolated: tuple[list[str], Path, Path],
) -> None:
    package = populated()
    declarations = neutral_forms.rows(package, "discoveries.csv")
    declarations[0].update(unresolved="true", note="Cannot distinguish source boundary")
    package["discoveries.csv"] = form("discoveries.csv", declarations)
    package["objects.csv"] = (FORM_HEADERS["objects.csv"] + "\n").encode()
    package["annotations.csv"] = (FORM_HEADERS["annotations.csv"] + "\n").encode()
    install_forms(isolated, package)
    result = run(isolated, "validate", "--require-complete")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["unresolved"] == declarations
    assert json.loads(result.stdout)["discoveries"] == []
    package = populated(end_page="2")
    install_forms(isolated, package)
    result = run(isolated, "validate", "--require-complete")
    expected = neutral_forms.validate_neutral_forms(
        package,
        expected_package=neutral_forms.PackageManifest.model_validate_json(
            package["PACKAGE_MANIFEST.json"]
        ),
        require_complete=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        json.loads(result.stdout)["discoveries"] == expected.model_dump(mode="json")["discoveries"]
    )


def test_isolated_import_closure_and_canonical_schemas(
    isolated: tuple[list[str], Path, Path],
) -> None:
    import importlib

    from peru_conflicts.execution.runtime_build import SELECTIONS

    # A separate trusted test harness exercises the built import surface directly;
    # command tests exercise the production verifier before these same imports.
    code = """
import sys, runpy, importlib, json
from pathlib import Path
from contextlib import ExitStack
root = Path(sys.argv[1])
launcher = runpy.run_path(str(root / 'trusted_launcher.py'))
with ExitStack() as stack:
    files = launcher['read_tree'](root / 'runtime', stack)
    sys.path.append(str(root / 'dependencies'))
    sys.meta_path.insert(0, launcher['MemoryModules'](files))
    for module in (
        'peru_conflicts.benchmark.metrics',
        'peru_conflicts.execution.annotation',
        'peru_conflicts.execution.coordination',
        'peru_conflicts.acquisition.fs_safety',
        'peru_conflicts.execution.runtime_build',
        'peru_conflicts.models.events',
    ):
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            pass
        else:
            raise AssertionError('prohibited module loaded')
    models = importlib.import_module('peru_conflicts.benchmark.models')
    assert not hasattr(models, 'PartitionRole')
    assert not hasattr(models, 'AnnotatorSubmission')
    assert not hasattr(models, 'GoldAdjudication')
    names = json.loads(sys.argv[2])
    schemas = {}
    for module, definitions in names.items():
        loaded = importlib.import_module('peru_conflicts.' + module)
        for name in definitions:
            value = getattr(loaded, name)
            if isinstance(value, type) and hasattr(value, 'model_json_schema'):
                schemas[module + '.' + name] = value.model_json_schema()
    print(json.dumps(schemas, ensure_ascii=False))
"""
    names = {module: list(values[1]) for module, values in SELECTIONS.items()}
    result = subprocess.run(
        [isolated[0][0], "-I", "-S", "-B", "-c", code, str(isolated[2]), json.dumps(names)],
        cwd=isolated[2],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    expected = {}
    for module, definitions in names.items():
        loaded = importlib.import_module("peru_conflicts." + module)
        for name in definitions:
            value = getattr(loaded, name)
            if isinstance(value, type) and issubclass(value, BaseModel):
                expected[module + "." + name] = value.model_json_schema()
    assert json.loads(result.stdout) == expected
