from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from open_notebook.dependencies import broker_dep, storage_dep
from open_notebook.models import (
    ArtifactOut,
    ConversationMessageCreate,
    JobCreate,
    JobOut,
    SessionCreate,
    SessionOut,
    SourceOut,
)
from open_notebook.services.events import EventBroker
from open_notebook.services.agent import NotebookAgent
from open_notebook.services.llm_settings import LLMSettingsService
from open_notebook.services.model_assets import download_model, model_status
from open_notebook.services.sources import save_upload
from open_notebook.services.storage import Storage
from open_notebook.workflows.runner import schedule_job

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, storage: Storage = Depends(storage_dep)) -> SessionOut:
    return storage.create_session(payload.title)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(storage: Storage = Depends(storage_dep)) -> list[SessionOut]:
    return storage.list_sessions()


@router.get("/sessions/{session_id}", response_model=dict)
def get_session(session_id: str, storage: Storage = Depends(storage_dep)) -> dict:
    try:
        return {
            "session": storage.get_session(session_id),
            "sources": storage.list_sources(session_id),
            "jobs": storage.list_jobs(session_id),
            "messages": storage.list_messages(session_id),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/sources", response_model=SourceOut)
async def upload_source(
    session_id: str,
    file: UploadFile = File(...),
    storage: Storage = Depends(storage_dep),
) -> SourceOut:
    try:
        storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await save_upload(storage, session_id=session_id, filename=file.filename or "upload.bin", fileobj=file.file)


@router.get("/sessions/{session_id}/sources", response_model=list[SourceOut])
def list_sources(session_id: str, storage: Storage = Depends(storage_dep)) -> list[SourceOut]:
    return storage.list_sources(session_id)


@router.post("/sessions/{session_id}/jobs", response_model=JobOut)
async def create_job(
    session_id: str,
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    storage: Storage = Depends(storage_dep),
    broker: EventBroker = Depends(broker_dep),
) -> JobOut:
    try:
        storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    options = dict(payload.options)
    options["source_ids"] = payload.source_ids
    job = storage.create_job(
        session_id=session_id,
        mode=payload.mode,
        prompt=payload.prompt,
        options=options,
    )
    background_tasks.add_task(schedule_job, storage, broker, job.id)
    return job


@router.post("/sessions/{session_id}/messages", response_model=dict)
async def create_message(
    session_id: str,
    payload: ConversationMessageCreate,
    background_tasks: BackgroundTasks,
    storage: Storage = Depends(storage_dep),
    broker: EventBroker = Depends(broker_dep),
) -> dict:
    try:
        storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = await NotebookAgent(storage, broker).handle_user_message(
        session_id=session_id,
        content=payload.content,
        mode_hint=payload.mode_hint,
        options=payload.options,
        source_ids=payload.source_ids,
        background_tasks=background_tasks,
    )
    return {
        "user_message": result.user_message,
        "assistant_message": result.assistant_message,
        "job": result.job,
        "decision": result.decision,
    }


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, storage: Storage = Depends(storage_dep)):
    try:
        storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def stream():
        last_seen = ""
        while True:
            messages = storage.list_messages(session_id, limit=120)
            jobs = storage.list_jobs(session_id)
            signature = json.dumps(
                {
                    "messages": [(m.id, m.created_at) for m in messages],
                    "jobs": [(j.id, j.status.value, j.updated_at) for j in jobs[:12]],
                },
                ensure_ascii=False,
            )
            if signature != last_seen:
                last_seen = signature
                yield _sse(
                    "snapshot",
                    {
                        "messages": [m.model_dump(mode="json") for m in messages],
                        "jobs": [j.model_dump(mode="json") for j in jobs],
                    },
                    0,
                )
            await asyncio.sleep(1.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}", response_model=dict)
def get_job(job_id: str, storage: Storage = Depends(storage_dep)) -> dict:
    try:
        return {"job": storage.get_job(job_id), "artifacts": storage.list_artifacts(job_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    storage: Storage = Depends(storage_dep),
    broker: EventBroker = Depends(broker_dep),
):
    async def stream():
        last_id = 0
        for row in storage.list_events(job_id, after_id=0):
            last_id = row["id"]
            yield _sse(row["type"], row["payload"], last_id)
        async for event in broker.subscribe(job_id):
            rows = storage.list_events(job_id, after_id=last_id)
            if rows:
                for row in rows:
                    last_id = row["id"]
                    yield _sse(row["type"], row["payload"], last_id)
            else:
                yield _sse(event["type"], event["payload"], last_id)
            await asyncio.sleep(0)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, storage: Storage = Depends(storage_dep)):
    try:
        artifact = storage.get_artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = Path(artifact.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")
    return FileResponse(path, media_type=artifact.mime_type, filename=path.name)


@router.get("/settings/llm/catalog")
def llm_catalog(storage: Storage = Depends(storage_dep)):
    return LLMSettingsService(storage).catalog()


@router.post("/settings/llm/import")
def llm_import(config: dict, storage: Storage = Depends(storage_dep)):
    return LLMSettingsService(storage).import_config(config)


@router.post("/settings/llm/select")
def llm_select(payload: dict, storage: Storage = Depends(storage_dep)):
    return LLMSettingsService(storage).select(str(payload.get("selection", "")))


@router.get("/settings/llm/export")
def llm_export(storage: Storage = Depends(storage_dep)):
    return LLMSettingsService(storage).export_config()


@router.post("/settings/llm/probe")
async def llm_probe(storage: Storage = Depends(storage_dep)):
    return await LLMSettingsService(storage).probe()


@router.get("/settings/sensenova/status")
def sensenova_status():
    return model_status()


@router.post("/settings/sensenova/download")
def sensenova_download():
    return download_model()


def _sse(event: str, payload: dict, event_id: int) -> str:
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
