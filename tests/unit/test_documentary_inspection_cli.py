"""Portable public commands and optimization boundaries on invented documents."""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib.resources import files
from pathlib import Path

from test_documentary_inspection import invented

from peru_conflicts.inspection import builder, cli, validation


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest, _, _ = invented(self.root / "inputs")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def command(self, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_public_commands_build_validate_query_export(self) -> None:
        database = self.root / "new.sqlite"
        receipt = self.root / "build.json"
        code, out, err = self.command(
            ["build", str(self.manifest), str(database), "--receipt", str(receipt)]
        )
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(json.loads(out)["closed_stage_independent_validation"])
        self.assertEqual(
            json.loads(receipt.read_bytes())["sha256"],
            hashlib.sha256(database.read_bytes()).hexdigest(),
        )
        for name, extra in [
            ("validate", [str(self.manifest)]),
            ("query", ["priority"]),
            ("export", [str(self.root / "export")]),
        ]:
            code, _, err = self.command([name, str(database), *extra])
            self.assertEqual((code, err), (0, ""))
        self.assertTrue((self.root / "export/inspection_overview.html").exists())

    def test_existing_receipt_stops_before_build(self) -> None:
        receipt = self.root / "receipt.json"
        receipt.write_bytes(b"original")
        output = self.root / "never.sqlite"
        code, _, _ = self.command(
            ["build", str(self.manifest), str(output), "--receipt", str(receipt)]
        )
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())
        self.assertEqual(receipt.read_bytes(), b"original")

    def test_missing_document_is_actual_failure_without_output(self) -> None:
        value = json.loads(self.manifest.read_bytes())
        Path(value["documents"][0]["path"]).unlink()
        output = self.root / "missing.sqlite"
        code, _, err = self.command(["build", str(self.manifest), str(output)])
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())
        self.assertIn("incomplete stage retained", err)

    def test_export_existing_directory_is_preserved(self) -> None:
        database = self.root / "new.sqlite"
        builder.build_snapshot(self.manifest, database)
        folder = self.root / "existing"
        folder.mkdir()
        marker = folder / "marker"
        marker.write_bytes(b"untouched")
        code, _, err = self.command(["export", str(database), str(folder)])
        self.assertEqual(code, 1)
        self.assertEqual(marker.read_bytes(), b"untouched")
        self.assertIn("marker", err)

    def test_intended_checkout_import_and_schema_resource(self) -> None:
        expected = Path(__file__).resolve().parents[2] / "src/peru_conflicts/inspection"
        self.assertEqual(Path(builder.__file__).resolve().parent, expected)
        schema = (
            files("peru_conflicts.inspection").joinpath("schema.sql").read_text(encoding="utf-8")
        )
        self.assertIn("CREATE TABLE documents", schema)
        self.assertNotEqual(
            builder.LIBRARY_VERSION, json.loads(self.manifest.read_bytes())["snapshot_version"]
        )

    def test_validation_does_not_invoke_builder(self) -> None:
        from unittest.mock import patch

        database = self.root / "new.sqlite"
        builder.build_snapshot(self.manifest, database)
        with patch.object(
            builder, "build_snapshot", side_effect=AssertionError("generator must not run")
        ):
            self.assertTrue(validation.validate(database, self.manifest)["success"])

    def test_optimized_query_still_rejects_hash_change(self) -> None:
        database = self.root / "new.sqlite"
        builder.build_snapshot(self.manifest, database)
        source = Path(builder.__file__).resolve().parents[2]
        code = """import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from peru_conflicts.inspection.queries import query
objects=[SimpleNamespace(hexdigest=lambda:'before'),SimpleNamespace(hexdigest=lambda:'after')]
with patch('peru_conflicts.inspection.queries.hashlib.sha256',side_effect=objects):
    try:query(Path(sys.argv[2]),'units')
    except ValueError as exc:
        print(exc);raise SystemExit(0)
raise SystemExit(1)
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-O", "-c", code, str(source), str(database)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("changed sealed database", result.stdout)

    def test_optimized_build_fails_before_any_publication(self) -> None:
        source = Path(builder.__file__).resolve().parents[2]
        output = self.root / "optimized.sqlite"
        code = (
            "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
            "from peru_conflicts.inspection.builder import build_snapshot;"
            "build_snapshot(Path(sys.argv[2]),Path(sys.argv[3]))"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-O",
                "-c",
                code,
                str(source),
                str(self.manifest),
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("optimized Python", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
