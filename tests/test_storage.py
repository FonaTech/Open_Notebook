from pathlib import Path

from open_notebook.config import Settings
from open_notebook.models import JobMode, MessageRole
from open_notebook.services.storage import Storage


def test_storage_session_job(tmp_path: Path):
    storage = Storage(Settings(data_dir=tmp_path))
    session = storage.create_session("Test")
    job = storage.create_job(session_id=session.id, mode=JobMode.poster, prompt="做海报", options={})
    assert storage.get_session(session.id).title == "Test"
    assert storage.get_job(job.id).prompt == "做海报"
    assert storage.list_jobs(session.id)[0].id == job.id


def test_storage_messages_persist(tmp_path: Path):
    storage = Storage(Settings(data_dir=tmp_path))
    session = storage.create_session("Chat")
    user = storage.add_message(
        session_id=session.id,
        role=MessageRole.user,
        content="做一个简洁 PPT",
        metadata={"mode_hint": "ppt"},
    )
    assistant = storage.add_message(
        session_id=session.id,
        role=MessageRole.assistant,
        content="请说明听众。",
        metadata={"agent_action": "clarify"},
    )

    rows = storage.list_messages(session.id)
    assert [m.id for m in rows] == [user.id, assistant.id]
    assert rows[0].metadata["mode_hint"] == "ppt"
