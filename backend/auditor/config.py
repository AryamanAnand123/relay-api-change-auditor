"""Project-specific settings; importing these does not create runtime files."""

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = Path(
    os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))
) / "ApiChangeAuditor"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_AUDITOR_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "API Change Impact Auditor"
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    history_max_records: int = Field(default=100, ge=1, le=1000)
    history_max_bytes: int = Field(default=64 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024)
    ai_enabled: bool = True
    ai_daily_limit: int = Field(default=50, ge=1, le=100)

    @field_validator("runtime_root")
    @classmethod
    def runtime_is_separate(cls, value):
        if not value.is_absolute():
            raise ValueError("Runtime root must be an absolute path outside the source checkout")
        resolved = value.resolve()
        cedar_runtime = DEFAULT_RUNTIME_ROOT.parent / "LangchainProj"
        if resolved.is_relative_to(PROJECT_ROOT) or resolved.is_relative_to(cedar_runtime):
            raise ValueError("Runtime storage must be separate from Apiproj source and Cedar runtime")
        return resolved
