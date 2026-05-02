from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility for local smoke tests.
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Any

from pydantic import BaseModel, Field


class JobMode(StrEnum):
    auto = "auto"
    ppt = "ppt"
    poster = "poster"
    research_figure = "research_figure"
    edit = "edit"


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    reviewing = "reviewing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class SourceKind(StrEnum):
    document = "document"
    spreadsheet = "spreadsheet"
    image = "image"
    text = "text"
    unknown = "unknown"


class ArtifactKind(StrEnum):
    image = "image"
    pptx = "pptx"
    pdf = "pdf"
    html = "html"
    json = "json"
    text = "text"


class SessionCreate(BaseModel):
    title: str = "Untitled Notebook"


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceOut(BaseModel):
    id: str
    session_id: str
    kind: SourceKind
    filename: str
    path: str
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class JobCreate(BaseModel):
    mode: JobMode = JobMode.auto
    prompt: str
    source_ids: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    id: str
    session_id: str
    mode: JobMode
    resolved_mode: JobMode | None = None
    status: JobStatus
    prompt: str
    options: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: str
    updated_at: str


class ArtifactOut(BaseModel):
    id: str
    job_id: str
    kind: ArtifactKind
    label: str
    path: str
    mime_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class LLMProfile(BaseModel):
    id: str
    provider: str
    label: str
    model: str
    base_url: str = ""
    endpoint: str = ""
    api_key: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    payload_template: str = ""
    thinking_stream: bool = False
    temperature: float = 0.2
    request_timeout: int = 120
    capabilities: dict[str, bool] = Field(default_factory=dict)
    media_endpoints: dict[str, str] = Field(default_factory=dict)
    source: str = "config"


class ModelCatalog(BaseModel):
    selected: str
    provider: str
    options: list[dict[str, Any]]
    active_capabilities: dict[str, bool] = Field(default_factory=dict)
