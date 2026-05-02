from pathlib import Path

from open_notebook.config import Settings
from open_notebook.models import JobMode
from open_notebook.services.storage import Storage


def test_storage_session_job(tmp_path: Path):
    storage = Storage(Settings(data_dir=tmp_path))
    session = storage.create_session("Test")
    job = storage.create_job(session_id=session.id, mode=JobMode.poster, prompt="做海报", options={})
    assert storage.get_session(session.id).title == "Test"
    assert storage.get_job(job.id).prompt == "做海报"
    assert storage.list_jobs(session.id)[0].id == job.id
