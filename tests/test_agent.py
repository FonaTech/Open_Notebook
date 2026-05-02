from pathlib import Path

import pytest

from open_notebook.config import Settings
from open_notebook.models import JobMode
from open_notebook.services.agent import NotebookAgent
from open_notebook.services.events import EventBroker
from open_notebook.services.storage import Storage


@pytest.mark.asyncio
async def test_agent_clarifies_auto_without_task(tmp_path: Path, monkeypatch):
    storage = Storage(Settings(data_dir=tmp_path))
    session = storage.create_session("Agent")
    agent = NotebookAgent(storage, EventBroker())

    async def fake_decide(**kwargs):
        return {
            "action": "clarify",
            "mode": "auto",
            "confidence": 0.5,
            "question": "你希望生成 PPT、海报还是科研绘图？",
            "task_spec": {},
        }

    monkeypatch.setattr(agent, "_decide", fake_decide)
    result = await agent.handle_user_message(
        session_id=session.id,
        content="帮我处理这个资料",
        mode_hint=JobMode.auto,
    )

    assert result.job is None
    assert result.assistant_message.content == "你希望生成 PPT、海报还是科研绘图？"
    assert len(storage.list_messages(session.id)) == 2


@pytest.mark.asyncio
async def test_agent_runs_ppt_when_decision_ready(tmp_path: Path, monkeypatch):
    storage = Storage(Settings(data_dir=tmp_path))
    session = storage.create_session("Agent")
    agent = NotebookAgent(storage, EventBroker())

    async def fake_decide(**kwargs):
        return {
            "action": "run_task",
            "mode": "ppt",
            "confidence": 0.9,
            "assistant_message": "开始生成 8 页 PPT。",
            "task_spec": {
                "goal": "根据论文生成组会汇报 PPT",
                "audience": "组会",
                "page_count": 8,
                "aspect_ratio": "16:9",
                "image_size": "2K",
                "style": "简洁干练",
                "must_include": ["方法", "结果"],
            },
        }

    monkeypatch.setattr(agent, "_decide", fake_decide)
    result = await agent.handle_user_message(
        session_id=session.id,
        content="根据资料做 8 页组会 PPT",
        mode_hint=JobMode.auto,
    )

    assert result.job is not None
    assert result.job.mode == JobMode.ppt
    assert result.job.options["page_count"] == 8
    assert result.assistant_message.metadata["job_id"] == result.job.id
