from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


def _load_env() -> None:
    cwd = Path.cwd()
    for candidate in (cwd / ".env", cwd.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


_load_env()


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("OPEN_NOTEBOOK_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("OPEN_NOTEBOOK_PORT", "8017")))
    data_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("OPEN_NOTEBOOK_DATA_DIR", "./data")).expanduser()
    )
    fake_image: bool = Field(
        default_factory=lambda: os.getenv("OPEN_NOTEBOOK_FAKE_IMAGE", "0").lower()
        in {"1", "true", "yes", "on"}
    )
    default_ollama_url: str = "http://localhost:11434"
    default_ollama_model: str = "qwen2.5:7b"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "open_notebook.sqlite3"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    return settings
