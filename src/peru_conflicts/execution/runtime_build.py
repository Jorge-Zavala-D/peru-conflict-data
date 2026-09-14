"""Deterministic neutral runtime projection; this never issues a package."""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import sys
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES
from peru_conflicts.hashing import canonical_json_bytes
from peru_conflicts.models.common import Sha256, StrictModel

from .compatibility import CASE_SUBORDINATES
from .contracts import active_annotation_contract
from .neutral_forms import required_fields
from .packages import verify_package
from .python_environment import PythonEnvironmentTrustManifest, capture_rehearsal_environment
from .references import sha256

ROOT = Path(__file__).resolve().parents[3]
POLICY = "m2-neutral-runtime-source-selection-v1"
DEPENDENCIES = (
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
)

# Each selected definition is copied verbatim, including its decorators. Imports
# are explicit because the canonical modules also contain private capabilities.
SELECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "models.common": (
        (
            "import json\nfrom typing import Annotated, Self\nfrom pydantic import "
            "AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, mod"
            "el_validator\n"
        ),
        (
            "Identifier",
            "Sha256",
            "_validate_json_document",
            "JsonDocument",
            "StrictModel",
            "SourceBBox",
            "SourceSpan",
        ),
    ),
    "hashing": ("import hashlib\nimport json\nfrom typing import Any\n", ("canonical_json_bytes",)),
    "benchmark.models": (
        (
            "import hashlib\nimport json\nfrom enum import StrEnum\nfrom typing impo"
            "rt Literal, Self\nfrom pydantic import Field, model_validator\nfrom pe"
            "ru_conflicts.hashing import canonical_json_bytes\nfrom peru_conflicts"
            ".models.common import Identifier, Sha256, JsonDocument, SourceBBox, "
            "SourceSpan, StrictModel\n"
        ),
        (
            "BENCHMARK_SCHEMA_VERSION",
            "BENCHMARK_OBJECT_TYPES",
            "BenchmarkVersionedModel",
            "AnnotationUnitType",
            "EvidenceGranularity",
            "AnnotationState",
            "derive_annotation_unit_id",
            "AnnotationUnit",
            "EvidenceAnchor",
            "AnnotationSlot",
            "AnnotationObjectInstance",
            "FieldAnnotation",
        ),
    ),
    "execution.compatibility": (
        "from peru_conflicts.benchmark.models import BENCHMARK_OBJECT_TYPES, AnnotationUnitType\n",
        ("ANNEX_FAMILIES", "CASE_SUBORDINATES", "require_compatible"),
    ),
    "execution.discovery": (
        (
            "import hashlib\nfrom typing import Literal, Self\nfrom pydantic import"
            " Field, model_validator\nfrom peru_conflicts.benchmark.models import "
            "AnnotationUnit, AnnotationUnitType, derive_annotation_unit_id\nfrom p"
            "eru_conflicts.hashing import canonical_json_bytes\nfrom peru_conflict"
            "s.models.common import Identifier, Sha256, StrictModel\nfrom .compati"
            "bility import require_compatible\n"
        ),
        (
            "_digest",
            "DiscoveryWindow",
            "SourcePosition",
            "position_from_reference",
            "DiscoveredObject",
        ),
    ),
    "execution.references": (
        (
            "import hashlib\nfrom collections.abc import Mapping\nfrom typing impor"
            "t Literal, Self\nfrom pydantic import Field, model_validator\nfrom per"
            "u_conflicts.hashing import canonical_json_bytes\nfrom peru_conflicts."
            "models.common import Sha256, StrictModel\n"
        ),
        (
            "sha256",
            "reference_text",
            "select_position",
            "ReferencePage",
            "ReferenceSnapshotManifest",
            "build_manifest",
            "verify_pages",
        ),
    ),
    "execution.contracts": (
        (
            "from typing import Literal\nfrom peru_conflicts.models.common import "
            "Sha256, StrictModel\n"
        ),
        (
            "HistoricalAnnotationContractIdentityV3",
            "HistoricalAnnotationContractIdentityV4",
            "AnnotationContractIdentity",
        ),
    ),
    "execution.packages": (
        (
            "from typing import Literal\nfrom pydantic import Field\nfrom peru_conf"
            "licts.models.common import Sha256, StrictModel\nfrom .contracts impor"
            "t AnnotationContractIdentity\nfrom .references import ReferenceSnapsh"
            "otManifest\ndef verify_package(*args, **kwargs):\n    raise ValueError"
            "('independently pinned package verifier required')\n"
        ),
        ("FORM_HEADERS", "PackageManifest"),
    ),
    "execution.source_dates": (
        (
            "import json\nfrom peru_conflicts.benchmark.models import AnnotationSt"
            "ate, FieldAnnotation\n"
        ),
        ("validate_date_pair",),
    ),
    "execution.neutral_forms": (
        (
            "import csv\nimport io\nimport json\nfrom collections.abc import Callabl"
            "e, Mapping\nfrom pydantic import Field\nfrom peru_conflicts.benchmark."
            "models import BENCHMARK_OBJECT_TYPES, AnnotationObjectInstance, Anno"
            "tationState, AnnotationUnitType, EvidenceAnchor, EvidenceGranularity"
            ", FieldAnnotation\nfrom peru_conflicts.hashing import canonical_json_"
            "bytes\nfrom peru_conflicts.models.common import Identifier, Sha256, S"
            "trictModel\nfrom .compatibility import require_compatible\nfrom .disco"
            "very import DiscoveredObject, DiscoveryWindow, SourcePosition, posit"
            "ion_from_reference\nfrom .packages import FORM_HEADERS, PackageManife"
            "st, verify_package\nfrom .references import select_position, sha256\nf"
            "rom .source_dates import validate_date_pair\ndef required_fields(fami"
            "ly):\n    raise ValueError('independently pinned field registry requi"
            "red')\n"
        ),
        (
            "RequiredFieldRegistry",
            "PackageVerifier",
            "rows",
            "_unique",
            "DiscoveryFormHeader",
            "declarations",
            "empty_slots",
            "_slots",
            "_registered_fields",
            "NeutralDiscoveryAnnotations",
            "NeutralDraft",
            "_value",
            "_evidence",
            "validate_neutral_forms",
        ),
    ),
}


class RuntimeManifest(StrictModel):
    policy: Literal["m2-neutral-runtime-source-selection-v1"] = POLICY
    runtime_sha256: Sha256
    file_hashes: dict[str, Sha256]
    contract_sha256: Sha256
    registry_sha256: Sha256
    launcher_sha256: Sha256
    interpreter_sha256: Sha256
    dependency_sha256: Sha256
    python_environment_sha256: Sha256
    python_environment_manifest_sha256: Sha256
    python_environment: PythonEnvironmentTrustManifest
    dependency_versions: dict[str, str]
    python_version: str

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        environment = self.python_environment
        if (
            self.python_environment_sha256 != environment.python_environment_sha256
            or self.python_environment_manifest_sha256
            != sha256(_json(environment.model_dump(mode="json")))
            or self.interpreter_sha256 != environment.interpreter_sha256
            or self.dependency_sha256 != environment.dependency_sha256
        ):
            raise ValueError("runtime Python environment identity differs")
        if self.runtime_sha256 != sha256(
            _json({"policy": self.policy, "file_hashes": self.file_hashes})
        ):
            raise ValueError("runtime aggregate identity differs")
        for name, expected in (
            ("CONTRACT.json", self.contract_sha256),
            ("FIELD_REGISTRY.json", self.registry_sha256),
            ("DEPENDENCIES.json", self.dependency_sha256),
            ("PYTHON_ENVIRONMENT.json", self.python_environment_manifest_sha256),
        ):
            if self.file_hashes.get(name) != expected:
                raise ValueError("runtime material identity differs")
        return self


class NeutralViewIdentity(StrictModel):
    policy: Literal["m2-neutral-human-view-v1"] = "m2-neutral-human-view-v1"
    view_sha256: Sha256
    original_package_sha256: Sha256
    original_package_id: Sha256
    contract_sha256: Sha256
    file_hashes: dict[str, Sha256]

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        if self.view_sha256 != sha256(_json(self.model_dump(mode="json", exclude={"view_sha256"}))):
            raise ValueError("neutral view aggregate identity differs")
        if self.file_hashes.get("PACKAGE_MANIFEST.json") != self.original_package_sha256:
            raise ValueError("neutral view original package identity differs")
        return self


def _json(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def selected_source(module: str) -> bytes:
    imports, names = SELECTIONS[module]
    path = ROOT / "src/peru_conflicts" / (module.replace(".", "/") + ".py")
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    definitions: dict[str, ast.stmt] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            definitions[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    definitions[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            definitions[node.target.id] = node
    selected: list[str] = []
    for name in names:
        node = definitions[name]
        start = node.lineno
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.decorator_list:
            start = min(start, *(d.lineno for d in node.decorator_list))
        selected.append("".join(lines[start - 1 : node.end_lineno]))
    data = ("from __future__ import annotations\n" + imports + "\n\n".join(selected)).encode()
    _audit_source(module, data)
    return data


def _audit_source(module: str, data: bytes) -> None:
    allowed = {
        "__future__",
        "json",
        "hashlib",
        "typing",
        "enum",
        "collections.abc",
        "csv",
        "io",
        "pydantic",
    }
    forbidden = {
        "PartitionRole",
        "partition_role",
        "AnnotatorSubmission",
        "GoldAdjudication",
        "DiscoveryAssignmentContext",
        "MODEL_REGISTRY",
        "protocol_pilot",
        "parser_development",
        "held_out_evaluation",
    }
    for node in ast.walk(ast.parse(data)):
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports = [
                importlib.util.resolve_name(
                    "." * node.level + (node.module or ""),
                    "peru_conflicts." + module.rsplit(".", 1)[0],
                )
                if node.level
                else node.module or ""
            ]
        else:
            imports = []
        if any(
            name not in allowed and name.removeprefix("peru_conflicts.") not in SELECTIONS
            for name in imports
        ):
            raise ValueError("source import outside runtime allowlist")
        if (
            (isinstance(node, ast.Name) and node.id in forbidden)
            or (isinstance(node, ast.Attribute) and node.attr in forbidden)
            or (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in forbidden
            )
        ):
            raise ValueError("private semantic data in neutral source")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"__import__", "eval", "exec", "compile", "open"}
        ):
            raise ValueError("dynamic capability outside runtime allowlist")


def dependency_files() -> tuple[dict[str, bytes], dict[str, str]]:
    """Snapshot only the installed, explicitly named dependency distributions."""
    files: dict[str, bytes] = {}
    versions: dict[str, str] = {}
    for name in DEPENDENCIES:
        dist = importlib.metadata.distribution(name)
        versions[name] = dist.version
        for relative in dist.files or ():
            path = str(relative).replace("\\", "/")
            # RECORD also lists CLI entry points outside site-packages; none are
            # runtime dependencies. Bytecode is never a trusted source input.
            if ".." in Path(path).parts or "__pycache__" in Path(path).parts:
                continue
            if path.endswith((".pyc", ".pyo")):
                continue
            data = Path(str(dist.locate_file(relative))).read_bytes()
            if path in files and files[path] != data:
                raise ValueError("dependency distributions overlap")
            files[path] = data
    return files, versions


def write_new_tree(root: Path, files: dict[str, bytes]) -> None:
    """Builder output is an exclusive new directory, never an existing artifact."""
    if root.exists() or root.is_symlink():
        raise ValueError("output directory already exists")
    if root.parent.resolve(strict=True) != root.parent.absolute():
        raise ValueError("output parent cannot be aliased")
    root.mkdir()
    for name, data in sorted(files.items()):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)


def build_runtime(output_root: Path) -> RuntimeManifest:
    files = {
        "peru_conflicts/" + module.replace(".", "/") + ".py": selected_source(module)
        for module in SELECTIONS
    }
    for package in ("", "models/", "benchmark/", "execution/"):
        files["peru_conflicts/" + package + "__init__.py"] = b""
    registry = {
        family: required_fields(family)
        for family in sorted(BENCHMARK_OBJECT_TYPES | CASE_SUBORDINATES)
    }
    files["FIELD_REGISTRY.json"] = _json(registry)
    contract = active_annotation_contract()
    files["CONTRACT.json"] = _json(contract.model_dump(mode="json"))
    dependencies, versions = dependency_files()
    dependency_hashes = {name: sha256(data) for name, data in sorted(dependencies.items())}
    files["DEPENDENCIES.json"] = _json(
        {"versions": versions, "file_hashes": dependency_hashes, "python_version": sys.version}
    )
    environment = capture_rehearsal_environment(sha256(files["DEPENDENCIES.json"]))
    files["PYTHON_ENVIRONMENT.json"] = _json(environment.model_dump(mode="json"))
    files["PYTHON_ENVIRONMENT_POLICY.py"] = (
        Path(__file__).with_name("python_environment_policy.py").read_bytes()
    )
    hashes = {name: sha256(data) for name, data in sorted(files.items())}
    manifest = RuntimeManifest(
        runtime_sha256=sha256(_json({"policy": POLICY, "file_hashes": hashes})),
        file_hashes=hashes,
        contract_sha256=sha256(files["CONTRACT.json"]),
        registry_sha256=sha256(files["FIELD_REGISTRY.json"]),
        launcher_sha256=sha256(Path(__file__).with_name("runtime_cli.py").read_bytes()),
        interpreter_sha256=sha256(
            Path(getattr(sys, "_base_executable", sys.executable)).resolve().read_bytes()
        ),
        dependency_sha256=sha256(files["DEPENDENCIES.json"]),
        python_environment_sha256=environment.python_environment_sha256,
        python_environment_manifest_sha256=sha256(files["PYTHON_ENVIRONMENT.json"]),
        python_environment=environment,
        dependency_versions=versions,
        python_version=sys.version,
    )
    files["RUNTIME_MANIFEST.json"] = _json(manifest.model_dump(mode="json"))
    write_new_tree(output_root, files)
    return manifest


def build_neutral_view(original: dict[str, bytes], output_root: Path) -> NeutralViewIdentity:
    """Derive an unissued neutral view; preserve the complete original lineage."""
    manifest = verify_package(original)
    date = original["DATE_PAIR_INTERPRETATION.md"]
    if sha256(date) != "7d5e9bc442625690df03b8ce9739d07b3221dee033d125930b994251baef4ea5":
        raise ValueError("date interpretation boundary is not the reviewed version")
    lines = date.splitlines(keepends=True)
    if lines[8].strip() or not lines[9].startswith(b"For resolved action/alert pairs,"):
        raise ValueError("date interpretation neutral suffix boundary changed")
    files = dict(original)
    files["DATE_PAIR_INTERPRETATION.md"] = (
        b"# Source date and precision interpretation\n\n" + b"".join(lines[9:])
    )
    # The original safety instructions are already neutral. Preserve their bytes.
    guide_marker = b"## discoveries.csv\n"
    guide = original["FORM_GUIDE.md"]
    if guide.count(guide_marker) != 1:
        raise ValueError("form guide projection boundary changed")
    files["FORM_GUIDE.md"] = (
        b"# Source form commands\n\n"
        b"Use the separately trusted launcher and separately supplied identities.\n"
        b"Commands: page, position, slots, inspection-template, validate.\n"
        b"Commands print output and do not overwrite forms. Copy generated CSV\n"
        b"only into a new blank form. Validation never locks your work.\n"
        b"Select one-based Unicode line and column boundaries yourself. End\n"
        b"positions are exclusive. Cross-page boundaries are allowed.\n\n"
        + guide_marker
        + guide.split(guide_marker, 1)[1]
    )
    payload = {
        "policy": "m2-neutral-human-view-v1",
        "original_package_sha256": sha256(original["PACKAGE_MANIFEST.json"]),
        "original_package_id": manifest.package_id,
        "contract_sha256": sha256(_json(manifest.contract_identity.model_dump(mode="json"))),
        "file_hashes": {name: sha256(data) for name, data in sorted(files.items())},
    }
    identity = NeutralViewIdentity.model_validate_json(
        _json(payload | {"view_sha256": sha256(_json(payload))})
    )
    files["NEUTRAL_VIEW.json"] = _json(identity.model_dump(mode="json"))
    write_new_tree(output_root, files)
    return identity
