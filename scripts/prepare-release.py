"""Audit Git-visible source and create a review archive; never commit/push/deploy."""

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {"README.md", "PLAN.md", ".env.example", ".gitignore", ".gitattributes", "pyproject.toml", "alembic.ini", "LICENSE", "LICENSE.md", "LICENSE.txt"}
TOP_DIRECTORIES = {"backend", "frontend", "scripts", "docs", "evaluation", "examples"}
FORBIDDEN_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "dist", "__pycache__", ".pytest_cache", "runtime", "uploads", "downloads", ".aws", ".codex", ".agents", "release"}
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".in", ".mako", ".json", ".toml", ".ini", ".js", ".jsx", ".mjs", ".css", ".html", ".svg", ".png", ".ps1", ".tex"}
TOKEN_PATTERNS = [re.compile(rb"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----"),
                  re.compile(rb"gsk_[A-Za-z0-9]{32,}"), re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
                  re.compile(rb"sk-proj-[A-Za-z0-9_-]{30,}")]


def inspect_sources(root, names, known_key=None):
    root = root.resolve()
    entries = []
    for name in sorted(set(names)):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source list contains a path outside the repository")
        path = root / relative
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or path.is_symlink():
            raise ValueError("Source list contains an escaping path or symlink")
        lower = [part.lower() for part in relative.parts]
        if any(part in FORBIDDEN_DIRECTORIES for part in lower):
            raise ValueError("Excluded runtime/dependency directory in source list: " + name)
        if (relative.name.lower().startswith(".env") and name != ".env.example") or any(suffix in relative.name.lower() for suffix in (".sqlite", ".db", ".pem", ".key", ".pfx", ".p12")) or relative.suffix.lower() in {".log", ".pyc", ".zip"}:
            raise ValueError("Credential, runtime, or generated artifact in source list: " + name)
        if len(relative.parts) == 1:
            if name not in TOP_FILES:
                raise ValueError("Unreviewed root file: " + name)
        elif relative.parts[0] not in TOP_DIRECTORIES:
            raise ValueError("Unreviewed source directory: " + relative.parts[0])
        elif relative.suffix.lower() not in ALLOWED_SUFFIXES and relative.name != ".npmrc":
            raise ValueError("Unreviewed source file type: " + name)
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Missing or unexpectedly large source file: " + name)
        data = path.read_bytes()
        if (known_key and known_key.encode() in data) or any(pattern.search(data) for pattern in TOKEN_PATTERNS):
            raise ValueError("Possible credential content detected; contents withheld: " + name)
        entries.append({"path": relative.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return entries


def create_archive(root, entries, destination):
    manifest = {"format": "relay-source-review-v1", "scope": "Exact reviewed workspace bytes, not a published Git commit", "file_count": len(entries), "files": entries}
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            data = (root / entry["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Source changed after inspection; rerun review preparation")
            info = zipfile.ZipInfo("relay-api-change-auditor/" + entry["path"], date_time=(2026, 11, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
        info = zipfile.ZipInfo("relay-api-change-auditor/SOURCE-MANIFEST.json", date_time=(2026, 11, 8, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, manifest_bytes)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Source archive integrity check failed")
        expected = {"relay-api-change-auditor/" + entry["path"] for entry in entries} | {"relay-api-change-auditor/SOURCE-MANIFEST.json"}
        if set(archive.namelist()) != expected:
            raise ValueError("Archive entry set differs from manifest")
        for entry in entries:
            data = archive.read("relay-api-change-auditor/" + entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Archived source hash mismatch")
    return manifest


def main():
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    sys.path.insert(0, str(ROOT / "backend"))
    from auditor.config import Settings
    from auditor.explanations import load_key
    entries = inspect_sources(ROOT, [name for name in names if name], load_key(Settings()))
    destination = ROOT / "release/relay-api-change-auditor-source.zip"
    manifest = create_archive(ROOT, entries, destination)
    (destination.parent / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "review_archive_ready", "files": len(entries), "archive": str(destination),
                      "archive_bytes": destination.stat().st_size, "archive_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                      "credential_scan": "clean", "published": False, "git_mutated": False}))


if __name__ == "__main__":
    main()
