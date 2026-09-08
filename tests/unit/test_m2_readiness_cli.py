"""Human operation uses line/column and CSV, never handwritten canonical model JSON."""

from pathlib import Path

import pytest

from peru_conflicts.execution import readiness_cli
from peru_conflicts.execution.packages import build_package, publish_new
from peru_conflicts.execution.references import build_manifest


def test_position_helper_and_blank_validation_are_neutral(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "m2-readiness-human-package"
    root.mkdir()
    pages = {1: "Árbol 😀\nSecond invented line.\n".encode()}
    package = build_package(
        "synthetic-run", "annotator-a", [(build_manifest(260, "a" * 64, pages, "b" * 64), pages)]
    )
    for name, data in package.items():
        publish_new(root, name, data)
    assert (
        readiness_cli.main(
            [
                "position",
                str(root),
                "--report",
                "260",
                "--page",
                "1",
                "--line",
                "1",
                "--column",
                "7",
            ]
        )
        == 0
    )
    selected = capsys.readouterr().out
    assert '"offset":6' in selected and "😀" in selected
    assert "not a scientific start recommendation" in selected
    assert readiness_cli.main(["validate", str(root)]) == 0
    status = capsys.readouterr().out
    assert '"complete":false' in status
    assert "partition" not in status and "locked" not in status
    assert readiness_cli.main(["slots", str(root)]) == 0
    assert capsys.readouterr().out.count("\n") == 1
    (root / "unexpected.csv").write_bytes(b"machine suggestion")
    assert readiness_cli.main(["validate", str(root)]) == 2
    assert "unapproved" in capsys.readouterr().err
