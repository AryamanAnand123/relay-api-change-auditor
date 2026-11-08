import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = script("prepare-release")
demo = script("build-demo-reports")


def test_review_archive_matches_every_inspected_source_byte_and_is_reproducible(tmp_path):
    (tmp_path / "README.md").write_text("Original synthetic source\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/test.py").write_text("value = 1\n", encoding="utf-8")
    entries = release.inspect_sources(tmp_path, ["backend/test.py", "README.md"])
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    release.create_archive(tmp_path, entries, first)
    release.create_archive(tmp_path, entries, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        manifest = json.loads(archive.read("relay-api-change-auditor/SOURCE-MANIFEST.json"))
        assert manifest["files"] == entries and manifest["file_count"] == 2
        assert len(archive.namelist()) == 3


@pytest.mark.parametrize("name", [".env", "backend/private.key", "backend/history.sqlite3", "frontend/node_modules/file.js", ".venv/file.py", "frontend/dist/index.html", "../outside.py", "unreviewed.txt"])
def test_unwanted_runtime_secret_dependency_and_unreviewed_paths_are_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        release.inspect_sources(tmp_path, [name])


def test_actual_key_and_generic_token_detection_do_not_print_credentials(tmp_path):
    key = "gsk_" + "a" * 40
    path = tmp_path / "README.md"; path.write_text(key, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        release.inspect_sources(tmp_path, ["README.md"], known_key=key)
    assert key not in str(error.value)
    with pytest.raises(ValueError):
        release.inspect_sources(tmp_path, ["README.md"])


def test_source_changed_after_inspection_prevents_unreviewed_archive(tmp_path):
    path = tmp_path / "README.md"; path.write_text("before", encoding="utf-8")
    entries = release.inspect_sources(tmp_path, ["README.md"])
    path.write_text("after", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after inspection"):
        release.create_archive(tmp_path, entries, tmp_path / "changed.zip")


def test_public_example_reports_are_reproducible_without_history_or_provider(tmp_path):
    files = demo.build(tmp_path)
    assert len(files) == 6
    for entry in files:
        assert (tmp_path / entry["file"]).read_bytes() == (ROOT / "examples/reports" / entry["file"]).read_bytes()
    report = json.loads((tmp_path / "orders-breaking.json").read_text(encoding="utf-8"))
    assert report["example_only"] and report["result"]["comparison"]["summary"]["breaking"] == 3
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert not manifest["history_access"] and manifest["model_calls"] == 0
