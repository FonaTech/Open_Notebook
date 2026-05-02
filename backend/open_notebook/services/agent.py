from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from open_notebook.core.json_utils import json_dumps
from open_notebook.core.llm_client import LLMClient
from open_notebook.models import (
    ConversationMessageOut,
    JobMode,
    JobOut,
    MessageRole,
    SourceOut,
)
from open_notebook.services.events import EventBroker
from open_notebook.services.llm_settings import LLMSettingsService
from open_notebook.services.storage import Storage
from open_notebook.workflows.runner import schedule_job


AGENT_SYSTEM = """You are the Open_Notebook visual generation agent.
You operate a NotebookLM-style workspace where uploaded sources and chat history drive tasks.

Core behavior:
- The chat box is primary. Use multi-turn clarification before generation when requirements are incomplete.
- In auto mode, infer the user's intent from the latest message, source summaries, and chat history.
- In explicit modes, keep the selected mode unless the user clearly asks to switch; clarify conflicts.
- When enough information is available, return action=run_task and a complete task_spec.
- Never invent facts from sources. If source details are missing, ask a concise clarification.
- Prefer concise, professional, source-grounded outputs.
- If options.ui_language is en, zh-CN, zh-TW, or ja, write assistant_message and question in that UI language.
- If task_spec.output_language is en, zh-CN, zh-TW, or ja, the generated content should use that output language even if the chat UI language is different.

Task readiness:
- PPT requires topic/objective, source basis if sources exist, page_count, audience or use case, and style preference.
- Poster requires topic/objective, aspect_ratio, must-include facts/text, and visual tone.
- Research figure requires figure type, key entities/relationships, required labels, and aspect_ratio.
- Edit requires target/reference image and concrete change/preserve instructions.

Return JSON only with this schema:
{
  "action": "clarify|answer|run_task",
  "mode": "auto|ppt|poster|research_figure|edit",
  "confidence": 0.0,
  "assistant_message": "short user-facing response in options.ui_language when provided",
  "question": "one concise question when action=clarify",
    "task_spec": {
    "goal": "concrete task objective",
    "audience": "target audience or empty",
    "page_count": 8,
    "aspect_ratio": "16:9",
    "image_size": "2K",
    "output_language": "auto|zh-CN|zh-TW|en|ja",
    "style": "concise professional academic/business style unless user asked otherwise",
    "must_include": ["facts/text that must appear"],
    "avoid": ["visual/text constraints"],
    "source_ids": ["source ids to use"]
  }
}
"""


@dataclass
class AgentResult:
    user_message: ConversationMessageOut
    assistant_message: ConversationMessageOut
    job: JobOut | None = None
    decision: dict[str, Any] | None = None


class NotebookAgent:
    def __init__(self, storage: Storage, broker: EventBroker):
        self.storage = storage
        self.broker = broker

    async def handle_user_message(
        self,
        *,
        session_id: str,
        content: str,
        mode_hint: JobMode = JobMode.auto,
        options: dict[str, Any] | None = None,
        source_ids: list[str] | None = None,
            background_tasks: Any | None = None,
    ) -> AgentResult:
        options = dict(options or {})
        ui_language = _normalize_ui_language(options.get("ui_language"))
        sources = self.storage.get_sources(session_id, source_ids or [])
        selected_source_ids = [s.id for s in sources]
        user_message = self.storage.add_message(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
            metadata={
                "mode_hint": mode_hint.value,
                "options": options,
                "source_ids": selected_source_ids,
            },
        )
        decision = await self._decide(
            session_id=session_id,
            latest=content,
            mode_hint=mode_hint,
            options=options,
            sources=sources,
        )
        decision = self._normalize_decision(decision, content, mode_hint, sources, options)

        job: JobOut | None = None
        assistant_text = str(decision.get("assistant_message") or "").strip()
        if decision["action"] == "run_task":
            job = self._create_job_from_decision(
                session_id=session_id,
                user_message_id=user_message.id,
                content=content,
                decision=decision,
                sources=sources,
                options=options,
            )
            assistant_text = assistant_text or _localized(
                ui_language,
                f"需求已明确，开始执行 {job.resolved_mode or job.mode} 任务。",
                f"The request is clear; starting the {job.resolved_mode or job.mode} task.",
                f"需求已明確，開始執行 {job.resolved_mode or job.mode} 任務。",
                f"要件が明確になりました。{job.resolved_mode or job.mode} タスクを開始します。",
            )
            decision.setdefault("task_spec", {})["job_id"] = job.id
            if background_tasks is not None:
                background_tasks.add_task(schedule_job, self.storage, self.broker, job.id)
        elif decision["action"] == "clarify":
            assistant_text = str(
                decision.get("question")
                or assistant_text
                or _localized(
                    ui_language,
                    "请补充一下具体需求。",
                    "Please add the specific requirements.",
                    "請補充一下具體需求。",
                    "具体的な要件を追加してください。",
                )
            ).strip()
        else:
            assistant_text = assistant_text or self._fallback_answer(content, sources, options)

        assistant_message = self.storage.add_message(
            session_id=session_id,
            role=MessageRole.assistant,
            content=assistant_text,
            metadata={
                "agent_action": decision["action"],
                "mode": decision.get("mode", mode_hint.value),
                "decision": decision,
                "job_id": job.id if job else "",
                "source_ids": selected_source_ids,
            },
        )
        return AgentResult(user_message, assistant_message, job, decision)

    async def _decide(
        self,
        *,
        session_id: str,
        latest: str,
        mode_hint: JobMode,
        options: dict[str, Any],
        sources: list[SourceOut],
    ) -> dict[str, Any]:
        payload = {
            "mode_hint": mode_hint.value,
            "latest_user_message": latest,
            "options": options,
            "sources": [
                {
                    "id": s.id,
                    "filename": s.filename,
                    "kind": s.kind.value,
                    "summary": s.summary,
                    "metadata": _compact_source_metadata(s.metadata),
                }
                for s in sources
            ],
            "recent_messages": [
                {"role": m.role.value, "content": m.content, "metadata": _compact_message_metadata(m.metadata)}
                for m in self.storage.list_messages(session_id, limit=16)
            ],
            "recent_jobs": [
                {
                    "id": j.id,
                    "mode": j.mode.value,
                    "resolved_mode": j.resolved_mode.value if j.resolved_mode else "",
                    "status": j.status.value,
                    "prompt": j.prompt[:500],
                    "plan_title": str(j.plan.get("title", ""))[:120] if isinstance(j.plan, dict) else "",
                }
                for j in self.storage.list_jobs(session_id)[:6]
            ],
        }
        try:
            return await self._llm_client().complete_json(AGENT_SYSTEM, payload, max_tokens=2400)
        except Exception:
            return self._heuristic_decision(latest, mode_hint, sources, options)

    def _normalize_decision(
        self,
        raw: dict[str, Any],
        latest: str,
        mode_hint: JobMode,
        sources: list[SourceOut],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        data = dict(raw or {})
        action = str(data.get("action") or "").strip().lower()
        if action not in {"clarify", "answer", "run_task"}:
            action = "clarify"
        mode = _normalize_mode(str(data.get("mode") or mode_hint.value or "auto"))
        if mode_hint != JobMode.auto and mode == JobMode.auto:
            mode = mode_hint
        if mode_hint != JobMode.auto and mode != mode_hint:
            action = "clarify"
            ui_language = _normalize_ui_language(options.get("ui_language"))
            data["question"] = _localized(
                ui_language,
                f"你当前选择的是 {mode_hint.value}，但描述像 {mode.value}。请确认要执行哪一种任务？",
                f"You selected {mode_hint.value}, but the request sounds like {mode.value}. Which task should I run?",
                f"你目前選擇的是 {mode_hint.value}，但描述像 {mode.value}。請確認要執行哪一種任務？",
                f"現在選択されているのは {mode_hint.value} ですが、依頼内容は {mode.value} に見えます。どちらを実行しますか？",
            )
        confidence = _safe_float(data.get("confidence"), 0.0)
        task_spec = data.get("task_spec") if isinstance(data.get("task_spec"), dict) else {}
        task_spec = self._normalize_task_spec(task_spec, latest, mode, sources, options)
        if action == "run_task" and (mode == JobMode.auto or confidence < 0.72 or not _task_ready(mode, task_spec, sources)):
            action = "clarify"
            data["question"] = _missing_question(latest, mode, task_spec, sources, options)
        data["action"] = action
        data["mode"] = mode.value
        data["confidence"] = confidence
        data["task_spec"] = task_spec
        return data

    def _normalize_task_spec(
        self,
        spec: dict[str, Any],
        latest: str,
        mode: JobMode,
        sources: list[SourceOut],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        out = dict(spec or {})
        out["goal"] = str(out.get("goal") or latest).strip()
        out["audience"] = str(out.get("audience") or options.get("audience") or "").strip()
        out["image_size"] = str(out.get("image_size") or options.get("image_size") or "2K")
        out["output_language"] = _normalize_output_language(
            out.get("output_language") or options.get("output_language") or "auto"
        )
        out["style"] = str(
            out.get("style")
            or options.get("style")
            or ("简洁干练的学术/商务汇报风格" if _has_cjk(latest) else "concise professional academic/business style")
        ).strip()
        if mode == JobMode.ppt:
            out["page_count"] = int(options.get("page_count") or out.get("page_count") or _extract_page_count(latest) or 8)
            out["aspect_ratio"] = "16:9"
        else:
            out["aspect_ratio"] = str(out.get("aspect_ratio") or options.get("aspect_ratio") or ("9:16" if mode == JobMode.poster else "16:9"))
        if not isinstance(out.get("must_include"), list):
            out["must_include"] = _source_key_points(sources)[:8]
        if not isinstance(out.get("avoid"), list):
            out["avoid"] = []
        out["source_ids"] = [s.id for s in sources]
        return out

    def _create_job_from_decision(
        self,
        *,
        session_id: str,
        user_message_id: str,
        content: str,
        decision: dict[str, Any],
        sources: list[SourceOut],
        options: dict[str, Any],
    ) -> JobOut:
        mode = _normalize_mode(str(decision.get("mode") or "poster"))
        if mode == JobMode.auto:
            mode = JobMode.poster
        task_spec = dict(decision.get("task_spec") or {})
        job_options = dict(options or {})
        job_options.update(
            {
                "source_ids": [s.id for s in sources],
                "agent_message_id": user_message_id,
                "task_spec": task_spec,
                "image_size": task_spec.get("image_size") or job_options.get("image_size") or "2K",
                "output_language": task_spec.get("output_language") or job_options.get("output_language") or "auto",
            }
        )
        if mode == JobMode.ppt:
            job_options["page_count"] = int(task_spec.get("page_count") or job_options.get("page_count") or 8)
        else:
            job_options["aspect_ratio"] = str(task_spec.get("aspect_ratio") or job_options.get("aspect_ratio") or "16:9")
        prompt = _compose_task_prompt(content, task_spec)
        return self.storage.create_job(session_id=session_id, mode=mode, prompt=prompt, options=job_options)

    def _heuristic_decision(
        self, latest: str, mode_hint: JobMode, sources: list[SourceOut], options: dict[str, Any]
    ) -> dict[str, Any]:
        mode = mode_hint if mode_hint != JobMode.auto else _infer_mode(latest)
        spec = self._normalize_task_spec({}, latest, mode, sources, options)
        if mode == JobMode.auto or not _task_ready(mode, spec, sources):
            return {
                "action": "clarify",
                "mode": mode.value,
                "confidence": 0.45,
                "question": _missing_question(latest, mode, spec, sources, options),
                "task_spec": spec,
            }
        return {
            "action": "run_task",
            "mode": mode.value,
            "confidence": 0.8,
            "assistant_message": _localized(
                _normalize_ui_language(options.get("ui_language")),
                "需求已明确，我会开始生成。",
                "The request is clear enough; I will start generation.",
                "需求已明確，我會開始生成。",
                "要件は十分に明確です。生成を開始します。",
            ),
            "task_spec": spec,
        }

    def _fallback_answer(self, latest: str, sources: list[SourceOut], options: dict[str, Any]) -> str:
        ui_language = _normalize_ui_language(options.get("ui_language"))
        if sources:
            return _localized(
                ui_language,
                "我已读取当前资料。请告诉我你想生成 PPT、海报、科研图，还是要继续细化问题。",
                "I have the current sources. Tell me whether to generate slides, a poster, a research figure, or keep refining the task.",
                "我已讀取目前資料。請告訴我你想生成 PPT、海報、科研圖，還是要繼續細化問題。",
                "現在の資料を読み込みました。スライド、ポスター、研究図を生成するか、さらに要件を詰めるかを教えてください。",
            )
        return _localized(
            ui_language,
            "请先添加资料，或直接说明你希望生成的内容。",
            "Add sources first, or describe what you want to generate.",
            "請先新增資料，或直接說明你希望生成的內容。",
            "まず資料を追加するか、生成したい内容を直接説明してください。",
        )

    def _llm_client(self) -> LLMClient:
        try:
            return LLMClient(LLMSettingsService(self.storage).active_profile())
        except Exception:
            return LLMClient()


def _normalize_mode(raw: str) -> JobMode:
    value = str(raw or "").strip().lower()
    aliases = {
        "slides": "ppt",
        "deck": "ppt",
        "presentation": "ppt",
        "figure": "research_figure",
        "diagram": "research_figure",
        "research": "research_figure",
    }
    value = aliases.get(value, value)
    try:
        return JobMode(value)
    except Exception:
        return JobMode.auto


def _normalize_output_language(raw: Any) -> str:
    value = str(raw or "auto").strip()
    aliases = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "cn": "zh-CN",
        "simplified_chinese": "zh-CN",
        "简体中文": "zh-CN",
        "zh_tw": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_hk": "zh-TW",
        "zh-hk": "zh-TW",
        "traditional_chinese": "zh-TW",
        "繁體中文": "zh-TW",
        "繁体中文": "zh-TW",
        "english": "en",
        "en-us": "en",
        "en": "en",
        "japanese": "ja",
        "日本語": "ja",
        "日文": "ja",
        "ja": "ja",
    }
    normalized = aliases.get(value.lower(), value)
    return normalized if normalized in {"auto", "zh-CN", "zh-TW", "en", "ja"} else "auto"


def _normalize_ui_language(raw: Any) -> str:
    value = _normalize_output_language(raw)
    return "zh-CN" if value == "auto" else value


def _infer_mode(text: str) -> JobMode:
    low = (text or "").lower()
    if any(x in low for x in ("ppt", "slides", "deck", "presentation", "演示", "幻灯片")):
        return JobMode.ppt
    if any(x in low for x in ("edit", "修改", "二次", "重绘", "调整")):
        return JobMode.edit
    if any(x in low for x in ("科研", "架构图", "原理图", "机制图", "3d", "diagram", "figure")):
        return JobMode.research_figure
    if any(x in low for x in ("poster", "海报", "信息图", "infographic")):
        return JobMode.poster
    return JobMode.auto


def _task_ready(mode: JobMode, spec: dict[str, Any], sources: list[SourceOut]) -> bool:
    goal = str(spec.get("goal") or "").strip()
    if len(goal) < 4:
        return False
    if mode == JobMode.ppt:
        return int(spec.get("page_count") or 0) > 0
    if mode == JobMode.poster:
        return bool(spec.get("aspect_ratio"))
    if mode == JobMode.research_figure:
        return bool(spec.get("aspect_ratio")) and (bool(spec.get("must_include")) or bool(sources))
    if mode == JobMode.edit:
        return any(s.kind.value == "image" for s in sources)
    return False


def _missing_question(text: str, mode: JobMode, spec: dict[str, Any], sources: list[SourceOut], options: dict[str, Any] | None = None) -> str:
    language = _normalize_ui_language((options or {}).get("ui_language")) if options is not None else ("zh-CN" if _has_cjk(text) else "en")
    if mode == JobMode.edit and not any(s.kind.value == "image" for s in sources):
        return _localized(language, "请先上传需要二次编辑的参考图片。", "Please upload the reference image to edit first.", "請先上傳需要二次編輯的參考圖片。", "二次編集する参照画像を先にアップロードしてください。")
    if mode == JobMode.ppt and not spec.get("audience"):
        return _localized(language, "这份 PPT 面向什么场景或听众？例如组会汇报、课程展示、项目路演。", "Who is the deck for, and in what setting?", "這份 PPT 面向什麼場景或聽眾？例如組會報告、課程展示、專案路演。", "このプレゼンはどの場面・聴衆向けですか？例：研究会発表、授業発表、プロジェクト提案。")
    if mode == JobMode.auto:
        return _localized(language, "你希望我基于资料生成 PPT、海报、科研绘图，还是进行图片二次编辑？", "Should I generate slides, a poster, a research figure, or edit an image?", "你希望我基於資料生成 PPT、海報、科研繪圖，還是進行圖片二次編輯？", "資料をもとにスライド、ポスター、研究図を生成しますか？それとも画像編集を行いますか？")
    return _localized(language, "请补充目标受众、必须包含的信息和偏好的视觉风格。", "Please add the audience, must-include information, and preferred visual style.", "請補充目標聽眾、必須包含的資訊和偏好的視覺風格。", "対象読者、必須情報、希望するビジュアルスタイルを追加してください。")


def _compose_task_prompt(user_text: str, spec: dict[str, Any]) -> str:
    return (
        f"{user_text.strip()}\n\n"
        "Agent clarified task specification:\n"
        f"{json_dumps(spec, indent=2)}"
    ).strip()


def _source_key_points(sources: list[SourceOut]) -> list[str]:
    out: list[str] = []
    for source in sources:
        summary = re.sub(r"\s+", " ", source.summary or "").strip()
        if summary:
            out.append(f"{source.filename}: {summary[:240]}")
    return out


def _compact_source_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out = dict(metadata or {})
    text = str(out.get("text_excerpt", ""))
    if len(text) > 2400:
        out["text_excerpt"] = text[:2400] + "..."
    return out


def _compact_message_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out = dict(metadata or {})
    if "decision" in out:
        out["decision"] = {"action": out.get("decision", {}).get("action"), "mode": out.get("decision", {}).get("mode")}
    return out


def _extract_page_count(text: str) -> int | None:
    m = re.search(r"(\d{1,2})\s*(页|pages?|slides?|张)", text or "", re.I)
    if not m:
        return None
    return max(1, min(60, int(m.group(1))))


def _safe_float(value: object, fallback: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return fallback


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _zh_or_en(text: str, zh: str, en: str) -> str:
    return zh if _has_cjk(text) else en


def _localized(language: str, zh_cn: str, en: str, zh_tw: str | None = None, ja: str | None = None) -> str:
    if language == "en":
        return en
    if language == "zh-TW":
        return zh_tw or zh_cn
    if language == "ja":
        return ja or en
    return zh_cn
