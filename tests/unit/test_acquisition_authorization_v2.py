"""Fail-closed authorization and execution-tree trust boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peru_conflicts.acquisition.authorization import (
    ArtifactDigestMismatch,
    AuthorizationNotReviewed,
    ExecutionTreeMismatch,
    RegistryTrustError,
    ReviewedNetworkAuthorizationV2,
    build_execution_tree_manifest,
    compute_data_root_identity_sha256,
    load_reviewed_network_authorization,
    resolve_public_protected_main_sha,
    validate_authorization_against_registry,
    verify_execution_tree,
)
from peru_conflicts.acquisition.models_v2 import (
    AuthorizationCapabilitiesV2,
    AuthorizationRegistryGrantV2,
    AuthorizationRegistryV2,
    NetworkAuthorizationArtifactV2,
    RedirectPolicyV2,
    StorageNamespaceMarkerV2,
    authorization_registry_core_sha256,
    marker_bytes,
)
from peru_conflicts.hashing import canonical_json_bytes

SHA = "a" * 64
COMMIT = "c" * 40
NETWORK_OVERRIDE_ENV = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "SSLKEYLOGFILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_ENGINES",
    "OPENSSL_MODULES",
)


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _artifact(*, execution_git_commit: str = COMMIT) -> NetworkAuthorizationArtifactV2:
    marker = StorageNamespaceMarkerV2(
        schema_version="0.2.0",
        namespace_id="namespace-1",
        owner_nonce_sha256=SHA,
    )
    return NetworkAuthorizationArtifactV2.model_validate(
        {
            "schema_version": "0.2.0",
            "authorization_id": "authorization-1",
            "authorization_status": "authorized",
            "scope": "m1_03b_reports_260_269_compare_only",
            "plan_id": "m1-03-reports-260-269-v2",
            "plan_file_sha256": SHA,
            "plan_semantic_sha256": SHA,
            "ordered_target_set_sha256": SHA,
            "plan_limits_sha256": SHA,
            "protected_source_receipt_path": "docs/source_integrity_receipt_m1_03b1.md",
            "protected_source_receipt_git_commit": COMMIT,
            "protected_source_receipt_sha256": SHA,
            "execution_git_commit": execution_git_commit,
            "execution_tree_manifest_sha256": SHA,
            "execution_tree_sha256": SHA,
            "dependency_records": tuple(
                {
                    "distribution": distribution,
                    "record_path": f"{distribution}-1.0.dist-info/RECORD",
                    "record_sha256": SHA,
                }
                for distribution in (
                    "annotated-types",
                    "pydantic",
                    "pydantic-core",
                    "pyyaml",
                    "typing-extensions",
                    "typing-inspection",
                )
            ),
            "approved_report_numbers": tuple(range(260, 270)),
            "approved_hosts": ("defensoria.gob.pe", "www.defensoria.gob.pe"),
            "capabilities": AuthorizationCapabilitiesV2(
                external_network_comparison=True,
                operational_ledger_writes=True,
                raw_staging=False,
                raw_promotion=False,
                historical_full_corpus_expansion=False,
            ),
            "redirect_policy": RedirectPolicyV2(
                max_hops=5,
                path_policy="canonical_wire_equivalent_only",
                approved_host_aliases=("defensoria.gob.pe", "www.defensoria.gob.pe"),
                require_https=True,
                default_port_only=True,
                allow_query=False,
            ),
            "storage_namespace_marker": marker,
            "storage_namespace_marker_sha256": hashlib.sha256(marker_bytes(marker)).hexdigest(),
            "data_root_identity_sha256": SHA,
            "execution_host_identity_sha256": SHA,
            "approved_by": "Jorge Zavala",
            "approved_at": datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
            "reuse_policy": "one_shot_same_run_resume_only",
        }
    )


def _artifact_bytes(artifact: NetworkAuthorizationArtifactV2) -> bytes:
    return canonical_json_bytes(artifact.model_dump(mode="json")) + b"\n"


def test_wrong_artifact_hash_fails_before_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "authorization.json"
    path.write_bytes(b"not-json")
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        path,
    )

    with pytest.raises(ArtifactDigestMismatch):
        load_reviewed_network_authorization(path, required_sha256=SHA)


def test_production_registry_is_empty_and_valid_looking_artifact_is_not_reviewed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    payload = _artifact_bytes(artifact)
    path = tmp_path / "authorization.json"
    path.write_bytes(payload)
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        path,
    )

    with pytest.raises(AuthorizationNotReviewed):
        load_reviewed_network_authorization(
            path,
            required_sha256=hashlib.sha256(payload).hexdigest(),
        )


def test_raw_model_is_not_a_loader_sealed_reviewed_authorization() -> None:
    with pytest.raises(AuthorizationNotReviewed, match="loader-sealed"):
        ReviewedNetworkAuthorizationV2.require(_artifact())


def test_registry_bytes_have_an_independent_compiled_trust_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dirty_registry = tmp_path / "registry.json"
    dirty_registry.write_text(
        json.dumps(
            {
                "schema_version": "0.2.0",
                "grants": [
                    {
                        "authorization_id": "authorization-1",
                        "artifact_sha256": SHA,
                        "artifact_core_sha256": authorization_registry_core_sha256(_artifact()),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_REGISTRY_PATH", dirty_registry
    )

    path = tmp_path / "authorization.json"
    payload = _artifact_bytes(_artifact())
    path.write_bytes(payload)
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        path,
    )
    with pytest.raises(RegistryTrustError):
        load_reviewed_network_authorization(
            path, required_sha256=hashlib.sha256(payload).hexdigest()
        )


def test_registry_pin_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dirty_pin = tmp_path / "registry.sha256"
    dirty_pin.write_text("b" * 64 + "\n", encoding="ascii")
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_REGISTRY_PIN_PATH",
        dirty_pin,
    )
    path = tmp_path / "authorization.json"
    payload = _artifact_bytes(_artifact())
    path.write_bytes(payload)
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        path,
    )

    with pytest.raises(RegistryTrustError, match="pin"):
        load_reviewed_network_authorization(
            path, required_sha256=hashlib.sha256(payload).hexdigest()
        )


def test_pure_registry_validator_accepts_only_exact_semantic_grant() -> None:
    artifact = _artifact()
    artifact_bytes = _artifact_bytes(artifact)
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    registry = AuthorizationRegistryV2(
        schema_version="0.2.0",
        grants=(
            AuthorizationRegistryGrantV2(
                authorization_id=artifact.authorization_id,
                artifact_sha256=artifact_sha256,
                artifact_core_sha256=authorization_registry_core_sha256(artifact),
            ),
        ),
    )
    assert (
        validate_authorization_against_registry(
            artifact,
            registry,
            artifact_sha256=artifact_sha256,
        )
        == artifact
    )

    reserialized = json.dumps(artifact.model_dump(mode="json"), indent=2, default=str).encode()
    with pytest.raises(AuthorizationNotReviewed):
        validate_authorization_against_registry(
            artifact,
            registry,
            artifact_sha256=hashlib.sha256(reserialized).hexdigest(),
        )

    changed = artifact.model_copy(update={"execution_tree_sha256": "b" * 64})
    with pytest.raises(AuthorizationNotReviewed):
        validate_authorization_against_registry(
            changed,
            registry,
            artifact_sha256=artifact_sha256,
        )

    changed_commit = artifact.model_copy(update={"execution_git_commit": "d" * 40})
    assert authorization_registry_core_sha256(changed_commit) != (
        authorization_registry_core_sha256(artifact)
    )
    with pytest.raises(AuthorizationNotReviewed):
        validate_authorization_against_registry(
            changed_commit,
            registry,
            artifact_sha256=artifact_sha256,
        )


def test_loader_seals_only_the_fixed_exact_artifact_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    raw = _artifact_bytes(artifact)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_bytes(raw)
    registry = AuthorizationRegistryV2(
        schema_version="0.2.0",
        grants=(
            AuthorizationRegistryGrantV2(
                authorization_id=artifact.authorization_id,
                artifact_sha256=raw_sha256,
                artifact_core_sha256=authorization_registry_core_sha256(artifact),
            ),
        ),
    )
    registry_bytes = canonical_json_bytes(registry.model_dump(mode="json")) + b"\n"
    registry_path = tmp_path / "registry.json"
    registry_path.write_bytes(registry_bytes)
    registry_pin = tmp_path / "registry.sha256"
    registry_pin.write_bytes((hashlib.sha256(registry_bytes).hexdigest() + "\n").encode("ascii"))
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_AUTHORIZATION_PATH",
        authorization_path,
    )
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_REGISTRY_PATH",
        registry_path,
    )
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.PRODUCTION_REGISTRY_PIN_PATH",
        registry_pin,
    )
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.resolve_public_protected_main_sha",
        lambda: "e" * 40,
    )

    sealed = load_reviewed_network_authorization(
        authorization_path,
        required_sha256=raw_sha256,
    )
    assert ReviewedNetworkAuthorizationV2.require(sealed).protected_main_sha == "e" * 40

    reserialized = json.dumps(artifact.model_dump(mode="json"), indent=2, default=str).encode()
    authorization_path.write_bytes(reserialized)
    with pytest.raises(AuthorizationNotReviewed):
        load_reviewed_network_authorization(
            authorization_path,
            required_sha256=hashlib.sha256(reserialized).hexdigest(),
        )


@pytest.mark.parametrize(
    "name",
    tuple(name for canonical in NETWORK_OVERRIDE_ENV for name in (canonical, canonical.lower())),
)
def test_application_public_main_resolver_rejects_network_overrides_before_connection(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    calls = 0

    class Connection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            nonlocal calls
            del args, kwargs
            calls += 1

    for canonical in NETWORK_OVERRIDE_ENV:
        monkeypatch.delenv(canonical, raising=False)
        monkeypatch.delenv(canonical.lower(), raising=False)
    monkeypatch.setenv(name, "unapproved")
    monkeypatch.setattr(
        "peru_conflicts.acquisition.authorization.http.client.HTTPSConnection",
        Connection,
    )
    with pytest.raises(ExecutionTreeMismatch, match="proxy, TLS, or OpenSSL override"):
        resolve_public_protected_main_sha()
    assert calls == 0


def test_execution_tree_detects_dirty_untracked_and_wrong_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "user.name", "Test")
    (repo / "src").mkdir()
    (repo / "src" / "runner.py").write_bytes(b"VALUE = 1\n")
    (repo / "pyproject.toml").write_bytes(b"[project]\nname='x'\n")
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "baseline")
    head = _run(repo, "rev-parse", "HEAD")
    _run(repo, "update-ref", "refs/remotes/origin/main", head)

    manifest = build_execution_tree_manifest(
        repo,
        paths=("pyproject.toml", "src/runner.py"),
    )
    verify_execution_tree(
        repo_root=repo,
        expected_git_commit=head,
        expected_manifest=manifest,
        required_paths=("pyproject.toml", "src/runner.py"),
        protected_main_sha=head,
    )

    with pytest.raises(ExecutionTreeMismatch):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=COMMIT,
            expected_manifest=manifest,
            required_paths=("pyproject.toml", "src/runner.py"),
            protected_main_sha=head,
        )
    (repo / "src" / "runner.py").write_bytes(b"VALUE = 2\n")
    with pytest.raises(ExecutionTreeMismatch):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=head,
            expected_manifest=manifest,
            required_paths=("pyproject.toml", "src/runner.py"),
            protected_main_sha=head,
        )
    (repo / "src" / "shadow.py").write_bytes(b"VALUE = 3\n")
    with pytest.raises(ExecutionTreeMismatch):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=head,
            expected_manifest=manifest,
            required_paths=("pyproject.toml", "src/runner.py"),
            protected_main_sha=head,
        )


def test_execution_tree_ignores_path_git_and_hostile_git_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "user.name", "Test")
    runner = repo / "runner.py"
    runner.write_bytes(b"VALUE = 1\n")
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "baseline")
    head = _run(repo, "rev-parse", "HEAD")
    manifest = build_execution_tree_manifest(repo, paths=("runner.py",))

    hostile = tmp_path / "hostile-bin"
    hostile.mkdir()
    marker = tmp_path / "fake-git-ran"
    (hostile / "git.cmd").write_text(
        f'@echo off\r\ntype nul > "{marker}"\r\nexit /b 0\r\n',
        encoding="ascii",
    )
    monkeypatch.setenv("PATH", str(hostile))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-the-repository"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hostile / "git.cmd"))

    verify_execution_tree(
        repo_root=repo,
        expected_git_commit=head,
        expected_manifest=manifest,
        required_paths=("runner.py",),
        protected_main_sha=head,
    )
    assert not marker.exists()


def test_execution_tree_allows_only_protected_main_external_anchor_delta(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "user.name", "Test")
    (repo / "src").mkdir()
    loader = repo / "src" / "authorization.py"
    loader.write_bytes(b"VALUE = 1\n")
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "reviewed execution")
    execution_commit = _run(repo, "rev-parse", "HEAD")
    manifest = build_execution_tree_manifest(repo, paths=("src/authorization.py",))
    _run(repo, "update-ref", "refs/remotes/origin/main", execution_commit)

    anchors = (
        "config/acquisition_authorizations/reviewed_registry_v2.json",
        "config/acquisition_authorizations/reviewed_registry_v2.sha256",
    )
    registry = repo / anchors[0]
    registry.parent.mkdir(parents=True)
    registry.write_bytes(b"{}\n")
    pin = repo / anchors[1]
    pin.write_bytes(("a" * 64 + "\n").encode("ascii"))
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "reviewed external anchors")
    anchor_commit = _run(repo, "rev-parse", "HEAD")

    with pytest.raises(ExecutionTreeMismatch, match="public protected GitHub main"):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=execution_commit,
            expected_manifest=manifest,
            required_paths=("src/authorization.py",),
            external_trust_anchors=anchors,
            protected_main_sha=execution_commit,
        )

    _run(repo, "update-ref", "refs/remotes/origin/main", anchor_commit)
    with pytest.raises(ExecutionTreeMismatch, match="public protected GitHub main"):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=execution_commit,
            expected_manifest=manifest,
            required_paths=("src/authorization.py",),
            external_trust_anchors=anchors,
            protected_main_sha=execution_commit,
        )

    verify_execution_tree(
        repo_root=repo,
        expected_git_commit=execution_commit,
        expected_manifest=manifest,
        required_paths=("src/authorization.py",),
        external_trust_anchors=anchors,
        protected_main_sha=anchor_commit,
    )

    loader.write_bytes(b"VALUE = 2\n")
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "unreviewed loader change")
    changed_commit = _run(repo, "rev-parse", "HEAD")
    _run(repo, "update-ref", "refs/remotes/origin/main", changed_commit)
    with pytest.raises(ExecutionTreeMismatch, match="outside external anchors"):
        verify_execution_tree(
            repo_root=repo,
            expected_git_commit=execution_commit,
            expected_manifest=manifest,
            required_paths=("src/authorization.py",),
            external_trust_anchors=anchors,
            protected_main_sha=changed_commit,
        )


def test_data_root_identity_rejects_a_copied_root_and_same_path_replacement(
    tmp_path: Path,
) -> None:
    marker_nonce = SHA
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    first_hash = compute_data_root_identity_sha256(
        first,
        marker_nonce_sha256=marker_nonce,
        execution_host_identity_sha256=SHA,
    )
    second_hash = compute_data_root_identity_sha256(
        second,
        marker_nonce_sha256=marker_nonce,
        execution_host_identity_sha256=SHA,
    )
    assert first_hash != second_hash

    retained_original = tmp_path / "retained-original"
    first.rename(retained_original)
    first.mkdir()
    replacement_hash = compute_data_root_identity_sha256(
        first,
        marker_nonce_sha256=marker_nonce,
        execution_host_identity_sha256=SHA,
    )
    assert replacement_hash != first_hash
