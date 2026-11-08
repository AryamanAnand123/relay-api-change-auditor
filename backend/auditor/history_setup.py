"""Explicit user-owned runtime initialization and versioned migrations."""

import os
import subprocess
from pathlib import Path

from alembic import command
from alembic.config import Config

from auditor.config import PROJECT_ROOT
from auditor.history import HistoryStore

MARKER = "API Change Impact Auditor history runtime v1\n"


def migration_config():
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    return config


def initialize_history(settings):
    root = settings.runtime_root
    marker = root / ".api-auditor-runtime"
    if root.exists() and any(root.iterdir()) and (not marker.is_file() or marker.read_text(encoding="utf-8") != MARKER):
        raise RuntimeError("Runtime directory is not empty and does not belong to this history setup; choose a separate directory.")
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(root), "/inheritance:r", "/grant:r", identity + ":(OI)(CI)F"], check=True, capture_output=True)
    else:
        root.chmod(0o700)
    marker.write_text(MARKER, encoding="utf-8")
    store = HistoryStore(settings)
    try:
        with store.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        return store.readiness()
    finally:
        store.close()
