"""Native API-shaped fixtures; no credentials, accounts or network."""

import hashlib

import pytest

from peru_conflicts.execution.setup_dropbox import dropbox_content_hash, folder_metadata


@pytest.mark.parametrize("path", ["/../escape", "//alias", "/a/./b", "/a\\b", "/a:b"])
def test_unsafe_paths_rejected(path: str) -> None:
    from peru_conflicts.execution.setup_dropbox import encode_request

    with pytest.raises(ValueError):
        encode_request(
            "files/create_folder_v2", {"path": path, "autorename": False}, "ns", "session"
        )


@pytest.mark.parametrize(
    "change",
    [
        {"autorename": True},
        {"strict_conflict": False},
        {"mode": {".tag": "overwrite"}},
        {"extra": True},
    ],
)
def test_upload_refuses_overwrite_rename_or_unscoped_fields(change: dict[str, object]) -> None:
    from peru_conflicts.execution.setup_dropbox import PROBE, encode_request

    args: dict[str, object] = {
        "path": "/fixture",
        "mode": {".tag": "add"},
        "autorename": False,
        "strict_conflict": True,
    }
    args.update(change)
    with pytest.raises(ValueError):
        encode_request("files/upload", args, "ns", "session", upload=PROBE)


def test_header_json_escapes_non_ascii_without_changing_target() -> None:
    import json

    from peru_conflicts.execution.setup_dropbox import PROBE, encode_request

    request = encode_request(
        "files/upload",
        {
            "path": "/prueba-español",
            "mode": {".tag": "add"},
            "autorename": False,
            "strict_conflict": True,
        },
        "ns",
        "session",
        upload=PROBE,
    )
    assert request.api_arg is not None
    request.api_arg.encode("ascii")
    assert json.loads(request.api_arg)["path"] == "/prueba-español"


@pytest.mark.parametrize(
    "field,value", [("rev", "new-rev"), ("id", "id:replacement"), ("path_display", "/outside")]
)
def test_cleanup_never_adopts_same_bytes_or_movement(field: str, value: str) -> None:
    from peru_conflicts.execution.setup_dropbox import FileObservation, cleanup_arguments

    owned = FileObservation(
        id="id:owned",
        name="probe",
        rev="original",
        size=36,
        content_hash="same-bytes",
        path_display="/inside/probe",
    )
    with pytest.raises(ValueError, match="drift"):
        cleanup_arguments(owned, owned.model_copy(update={field: value}))


def test_cleanup_rejects_folder_and_path_addressing() -> None:
    from peru_conflicts.execution.setup_dropbox import (
        FolderObservation,
        cleanup_arguments,
        encode_request,
    )

    folder = FolderObservation(id="id:folder", name="folder", path_display="/fixture")
    with pytest.raises(ValueError, match="folder deletion"):
        cleanup_arguments(folder, folder)
    with pytest.raises(ValueError):
        encode_request(
            "files/delete_v2", {"path": "/fixture", "parent_rev": "revision"}, "ns", "session"
        )


def test_endpoint_typed_folder_does_not_need_union_tag() -> None:
    folder = folder_metadata(b'{"metadata":{"id":"id:fixture","name":"fixture"}}')
    assert folder.id == "id:fixture"
    assert folder.path_display is None


@pytest.mark.parametrize(
    "path", ["id:folder/../escape", "id:folder/./child", "id:folder/a\\b", "id:/missing"]
)
def test_id_addressing_cannot_bypass_path_safety(path: str) -> None:
    from peru_conflicts.execution.setup_dropbox import PROBE, encode_request

    with pytest.raises(ValueError, match="unsafe"):
        encode_request(
            "files/upload",
            {"path": path, "mode": {".tag": "add"}, "autorename": False, "strict_conflict": True},
            "offline-ns",
            "offline-session",
            upload=PROBE,
        )


@pytest.mark.parametrize(
    "body", [b"", b"abc", b"x" * (4194304 + 1)], ids=["empty", "small", "multiblock"]
)
def test_dropbox_hash_is_not_raw_hash(body: bytes) -> None:
    blocks = b"".join(
        hashlib.sha256(body[i : i + 4194304]).digest() for i in range(0, len(body), 4194304)
    )
    assert dropbox_content_hash(body) == hashlib.sha256(blocks).hexdigest()
    if body:
        assert dropbox_content_hash(body) != hashlib.sha256(body).hexdigest()
