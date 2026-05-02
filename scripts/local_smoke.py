from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from pathlib import Path

from open_notebook.config import Settings
from open_notebook.core.image_driver import FakeImageDriver, LocalU1ImageDriver
from open_notebook.core.llm_client import LLMClient
from open_notebook.models import JobMode, LLMProfile
from open_notebook.services.events import EventBroker
from open_notebook.services.storage import Storage
from open_notebook.workflows.runner import WorkflowRunner


async def test_ollama(model: str) -> None:
    profile = LLMProfile(
        id="ollama",
        provider="ollama",
        label="Ollama",
        model=model,
        base_url="http://127.0.0.1:11434",
        request_timeout=180,
    )
    out = await LLMClient(profile).chat(
        [{"role": "user", "content": "Return exactly OPEN_NOTEBOOK_OK and nothing else."}],
        max_tokens=64,
    )
    print("[ollama]", out[:500].replace("\n", " "))
    if not out.strip():
        raise SystemExit("Ollama returned an empty response")


def test_local_u1_smoke() -> None:
    result = LocalU1ImageDriver().smoke_check()
    print("[local-u1-smoke]", result)


async def test_workflows(tmp: Path, ollama_model: str) -> None:
    os.environ["OPEN_NOTEBOOK_FAKE_IMAGE"] = "1"
    storage = Storage(Settings(data_dir=tmp))
    broker = EventBroker()
    storage.set_setting(
        "llm_config",
        {
            "profiles": [
                {
                    "id": "ollama",
                    "provider": "ollama",
                    "label": "Ollama",
                    "model": ollama_model,
                    "base_url": "http://127.0.0.1:11434",
                    "request_timeout": 180,
                }
            ],
            "active_profile_id": "ollama",
        },
    )
    session = storage.create_session("smoke")
    runner = WorkflowRunner(storage, broker)
    jobs = [
        (JobMode.auto, "请自动判断：做一张关于 SenseNova U1 架构的中文信息海报"),
        (JobMode.ppt, "做一个 3 页中文 PPT，介绍 SenseNova U1 的统一多模态能力"),
        (JobMode.poster, "做一张 9:16 中文大型海报，主题是科研绘图工作流"),
        (JobMode.research_figure, "生成一个 16:9 科研机制图，说明 LLM 如何驱动 SenseNova 逐页生图"),
        (JobMode.edit, "把参考海报改成更适合论文展示的风格"),
    ]
    for mode, prompt in jobs:
        job = storage.create_job(
            session_id=session.id,
            mode=mode,
            prompt=prompt,
            options={"page_count": 3, "image_size": "1K", "aspect_ratio": "16:9"},
        )
        await runner.run_job(job.id)
        done = storage.get_job(job.id)
        artifacts = storage.list_artifacts(job.id)
        print("[workflow]", mode.value, done.status.value, "artifacts", len(artifacts), "error", done.error)
        if done.status.value != "completed":
            raise SystemExit(f"workflow failed: {mode} {done.error}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-model", default=os.getenv("OPEN_NOTEBOOK_OLLAMA_MODEL", "qwen3.6:latest"))
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-u1-smoke", action="store_true")
    parser.add_argument("--skip-workflows", action="store_true")
    args = parser.parse_args()
    if not args.skip_ollama:
        await test_ollama(args.ollama_model)
    if not args.skip_u1_smoke:
        test_local_u1_smoke()
    if not args.skip_workflows:
        with tempfile.TemporaryDirectory() as td:
            await test_workflows(Path(td), args.ollama_model)


if __name__ == "__main__":
    asyncio.run(main())
