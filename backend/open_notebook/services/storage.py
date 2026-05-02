from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from open_notebook.config import Settings, get_settings
from open_notebook.core.json_utils import json_dumps
from open_notebook.models import (
    ArtifactKind,
    ArtifactOut,
    JobMode,
    JobOut,
    JobStatus,
    SessionOut,
    SourceKind,
    SourceOut,
)
from open_notebook.utils.ids import new_id, slugify
from open_notebook.utils.time import utc_now_iso


class Storage:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.projects_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    resolved_mode TEXT,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    options TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def create_session(self, title: str) -> SessionOut:
        sid = new_id("ses")
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(id,title,metadata,created_at,updated_at) VALUES(?,?,?,?,?)",
                (sid, title or "Untitled Notebook", "{}", now, now),
            )
        return self.get_session(sid)

    def list_sessions(self) -> list[SessionOut]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [self._session_from_row(r) for r in rows]

    def get_session(self, session_id: str) -> SessionOut:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise KeyError(f"session not found: {session_id}")
        return self._session_from_row(row)

    def touch_session(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (utc_now_iso(), session_id))

    def session_dir(self, session_id: str) -> Path:
        return self.settings.projects_dir / session_id

    def job_dir(self, session_id: str, job_id: str) -> Path:
        return self.session_dir(session_id) / "jobs" / job_id

    def source_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "sources"

    def save_source(
        self,
        *,
        session_id: str,
        filename: str,
        raw_path: Path,
        kind: SourceKind,
        summary: str,
        metadata: dict[str, Any],
    ) -> SourceOut:
        source_id = new_id("src")
        target_dir = self.source_dir(session_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix
        target = target_dir / f"{source_id}_{slugify(Path(filename).stem, 'source')}{suffix}"
        shutil.copy2(raw_path, target)
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sources(id,session_id,kind,filename,path,summary,metadata,created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    source_id,
                    session_id,
                    kind.value,
                    filename,
                    str(target),
                    summary,
                    json_dumps(metadata),
                    now,
                ),
            )
        self.touch_session(session_id)
        return self.get_source(source_id)

    def list_sources(self, session_id: str) -> list[SourceOut]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sources WHERE session_id=? ORDER BY created_at ASC", (session_id,)
            ).fetchall()
        return [self._source_from_row(r) for r in rows]

    def get_source(self, source_id: str) -> SourceOut:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise KeyError(f"source not found: {source_id}")
        return self._source_from_row(row)

    def get_sources(self, session_id: str, source_ids: list[str]) -> list[SourceOut]:
        if not source_ids:
            return self.list_sources(session_id)
        out = []
        for sid in source_ids:
            src = self.get_source(sid)
            if src.session_id == session_id:
                out.append(src)
        return out

    def create_job(
        self,
        *,
        session_id: str,
        mode: JobMode,
        prompt: str,
        options: dict[str, Any],
    ) -> JobOut:
        job_id = new_id("job")
        now = utc_now_iso()
        self.job_dir(session_id, job_id).mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(id,session_id,mode,resolved_mode,status,prompt,options,plan,error,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    session_id,
                    mode.value,
                    None,
                    JobStatus.pending.value,
                    prompt,
                    json_dumps(options),
                    "{}",
                    "",
                    now,
                    now,
                ),
            )
        self.touch_session(session_id)
        return self.get_job(job_id)

    def update_job(self, job_id: str, **fields: Any) -> JobOut:
        if not fields:
            return self.get_job(job_id)
        fields["updated_at"] = utc_now_iso()
        encoded: dict[str, Any] = {}
        for key, value in fields.items():
            if key in {"options", "plan"}:
                encoded[key] = json_dumps(value)
            elif key in {"mode", "resolved_mode", "status"} and hasattr(value, "value"):
                encoded[key] = value.value
            else:
                encoded[key] = value
        assignments = ", ".join(f"{k}=?" for k in encoded)
        values = list(encoded.values()) + [job_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id=?", values)
        job = self.get_job(job_id)
        self.touch_session(job.session_id)
        return job

    def get_job(self, job_id: str) -> JobOut:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(f"job not found: {job_id}")
        return self._job_from_row(row)

    def list_jobs(self, session_id: str) -> list[JobOut]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE session_id=? ORDER BY created_at DESC", (session_id,)
            ).fetchall()
        return [self._job_from_row(r) for r in rows]

    def add_artifact(
        self,
        *,
        job_id: str,
        kind: ArtifactKind,
        label: str,
        path: Path,
        mime_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactOut:
        artifact_id = new_id("art")
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts(id,job_id,kind,label,path,mime_type,metadata,created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    artifact_id,
                    job_id,
                    kind.value,
                    label,
                    str(path),
                    mime_type,
                    json_dumps(metadata or {}),
                    now,
                ),
            )
        return self.get_artifact(artifact_id)

    def list_artifacts(self, job_id: str) -> list[ArtifactOut]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY created_at ASC", (job_id,)
            ).fetchall()
        return [self._artifact_from_row(r) for r in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactOut:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise KeyError(f"artifact not found: {artifact_id}")
        return self._artifact_from_row(row)

    def add_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(job_id,type,payload,created_at) VALUES(?,?,?,?)",
                (job_id, event_type, json_dumps(payload), utc_now_iso()),
            )

    def list_events(self, job_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE job_id=? AND id>? ORDER BY id ASC",
                (job_id, after_id),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "job_id": r["job_id"],
                "type": r["type"],
                "payload": json.loads(r["payload"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def set_setting(self, key: str, value: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, json_dumps(value), utc_now_iso()),
            )

    def get_setting(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default or {}
        return json.loads(row["value"] or "{}")

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> SessionOut:
        return SessionOut(
            id=row["id"],
            title=row["title"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> SourceOut:
        return SourceOut(
            id=row["id"],
            session_id=row["session_id"],
            kind=SourceKind(row["kind"]),
            filename=row["filename"],
            path=row["path"],
            summary=row["summary"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> JobOut:
        return JobOut(
            id=row["id"],
            session_id=row["session_id"],
            mode=JobMode(row["mode"]),
            resolved_mode=JobMode(row["resolved_mode"]) if row["resolved_mode"] else None,
            status=JobStatus(row["status"]),
            prompt=row["prompt"],
            options=json.loads(row["options"] or "{}"),
            plan=json.loads(row["plan"] or "{}"),
            error=row["error"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactOut:
        return ArtifactOut(
            id=row["id"],
            job_id=row["job_id"],
            kind=ArtifactKind(row["kind"]),
            label=row["label"],
            path=row["path"],
            mime_type=row["mime_type"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
        )


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage
