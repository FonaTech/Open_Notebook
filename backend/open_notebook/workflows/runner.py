from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from open_notebook.core.generation_profiles import sensenova_profile_for_task
from open_notebook.core.image_driver import get_image_driver
from open_notebook.core.json_utils import json_dumps
from open_notebook.core.llm_client import LLMClient, LLMClientError
from open_notebook.exporters.deck import images_to_pdf, images_to_pptx
from open_notebook.models import ArtifactKind, JobMode, JobOut, JobStatus, SourceKind, SourceOut
from open_notebook.services.events import EventBroker
from open_notebook.services.llm_settings import LLMSettingsService
from open_notebook.services.storage import Storage
from open_notebook.workflows import prompts


class WorkflowRunner:
    def __init__(self, storage: Storage, broker: EventBroker):
        self.storage = storage
        self.broker = broker

    async def run_job(self, job_id: str) -> None:
        job = self.storage.get_job(job_id)
        await self._event(job_id, "status", {"message": "任务已启动"})
        self.storage.update_job(job_id, status=JobStatus.running)
        try:
            sources = self.storage.get_sources(job.session_id, job.options.get("source_ids", []))
            resolved = await self._resolve_mode(job, sources)
            self.storage.update_job(job_id, resolved_mode=resolved)
            digest = await self._digest_sources(job, sources)
            if resolved == JobMode.ppt:
                await self._run_ppt(job_id, digest, sources)
            elif resolved == JobMode.poster:
                await self._run_poster(job_id, digest, sources)
            elif resolved == JobMode.research_figure:
                await self._run_research_figure(job_id, digest, sources)
            elif resolved == JobMode.edit:
                await self._run_edit(job_id, digest, sources)
            else:
                raise RuntimeError(f"Unsupported resolved mode: {resolved}")
            self.storage.update_job(job_id, status=JobStatus.completed)
            await self._event(job_id, "completed", {"message": "任务完成"})
        except Exception as exc:
            self.storage.update_job(job_id, status=JobStatus.failed, error=str(exc))
            await self._event(job_id, "failed", {"error": str(exc)})

    async def _resolve_mode(self, job: JobOut, sources: list[SourceOut]) -> JobMode:
        if job.mode != JobMode.auto:
            await self._event(job.id, "route", {"mode": job.mode.value, "reason": "user selected"})
            return job.mode
        llm = self._llm_client()
        payload = {
            "user_prompt": job.prompt,
            "sources": [{"filename": s.filename, "kind": s.kind.value, "summary": s.summary} for s in sources],
        }
        try:
            data = await llm.complete_json(prompts.INTENT_ROUTER_SYSTEM, payload, max_tokens=1200)
            mode = JobMode(str(data.get("mode", "poster")))
            await self._event(job.id, "route", data)
            return mode
        except Exception:
            text = job.prompt.lower()
            if any(x in text for x in ("ppt", "slides", "演示", "幻灯片")):
                return JobMode.ppt
            if any(x in text for x in ("edit", "修改", "二次", "重绘", "调整")):
                return JobMode.edit
            if any(x in text for x in ("科研", "架构图", "原理图", "机制图", "3d", "diagram")):
                return JobMode.research_figure
            return JobMode.poster

    async def _digest_sources(self, job: JobOut, sources: list[SourceOut]) -> dict[str, Any]:
        await self._event(job.id, "status", {"message": "正在整理上传资料"})
        source_view = [
            {
                "filename": s.filename,
                "kind": s.kind.value,
                "summary": s.summary,
                "metadata": _compact_metadata(s.metadata),
            }
            for s in sources
        ]
        if not source_view:
            return {
                "topic_summary": job.prompt,
                "key_points": [job.prompt],
                "data_highlights": [],
                "visual_entities": [],
                "tables": [],
                "images": [],
                "language": "zh" if _has_cjk(job.prompt) else "en",
            }
        llm = self._llm_client()
        try:
            digest = await llm.complete_json(
                prompts.DOCUMENT_DIGEST_SYSTEM,
                {"user_prompt": job.prompt, "sources": source_view},
                max_tokens=4500,
            )
        except Exception:
            digest = {
                "topic_summary": "\n".join(s["summary"] for s in source_view)[:2000],
                "key_points": [s["summary"][:400] for s in source_view],
                "data_highlights": [],
                "visual_entities": [],
                "tables": [],
                "images": [],
                "language": "zh" if _has_cjk(job.prompt) else "en",
            }
        self._write_job_json(job, "sources_digest.json", digest)
        await self._event(job.id, "digest", {"summary": digest.get("topic_summary", "")})
        return digest

    async def _run_ppt(self, job_id: str, digest: dict[str, Any], sources: list[SourceOut]) -> None:
        job = self.storage.get_job(job_id)
        job_dir = self.storage.job_dir(job.session_id, job_id)
        page_count = int(job.options.get("page_count") or _extract_page_count(job.prompt) or 8)
        llm = self._llm_client()
        digest_for_planning = dict(digest)
        digest_for_planning["_options"] = job.options
        await self._event(job_id, "status", {"message": f"正在规划 {page_count} 页 PPT"})
        plan = await self._with_fallback_json(
            llm,
            prompts.PPT_PLAN_SYSTEM,
            {
                "user_prompt": job.prompt,
                "page_count": page_count,
                "digest": digest,
                "options": job.options,
            },
            fallback=_fallback_ppt_plan(job.prompt, digest_for_planning, page_count),
        )
        plan = _enforce_ppt_style_contract(plan)
        plan["page_count"] = page_count
        pages = plan.get("pages") if isinstance(plan.get("pages"), list) else []
        if len(pages) != page_count:
            plan = _fallback_ppt_plan(job.prompt, digest_for_planning, page_count)
            pages = plan["pages"]
        self.storage.update_job(job_id, plan=plan)
        self._write_job_json(job, "plan.json", plan)
        prompt_dir = job_dir / "prompts"
        image_dir = job_dir / "images"
        export_dir = job_dir / "exports"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        driver = get_image_driver()
        image_paths: list[Path] = []
        for page in pages:
            page_no = int(page.get("page_no", len(image_paths) + 1))
            await self._event(job_id, "progress", {"message": f"正在生成第 {page_no}/{page_count} 页 prompt"})
            page_prompt = await self._build_page_prompt(llm, plan, page)
            (prompt_dir / f"page_{page_no:03d}.txt").write_text(page_prompt, encoding="utf-8")
            image_path = image_dir / f"page_{page_no:03d}.png"
            profile = sensenova_profile_for_task(
                "ppt",
                image_size=str(job.options.get("image_size", "2K")),
                aspect_ratio="16:9",
                seed=job.options.get("seed"),
            )
            await self._event(
                job_id,
                "progress",
                {
                    "message": f"SenseNova 正在生成第 {page_no}/{page_count} 页整图",
                    "profile": profile.to_metadata(),
                },
            )
            result = await driver.generate(
                prompt=page_prompt,
                output_path=image_path,
                image_size=str(job.options.get("image_size", "2K")),
                aspect_ratio="16:9",
                seed=job.options.get("seed"),
                profile=profile,
            )
            image_paths.append(result.output_path)
            self.storage.add_artifact(
                job_id=job_id,
                kind=ArtifactKind.image,
                label=f"Slide {page_no:03d}",
                path=result.output_path,
                mime_type="image/png",
                metadata=result.metadata,
            )
            await self._event(job_id, "artifact", {"label": f"Slide {page_no:03d}", "path": str(result.output_path)})
        pptx_path = export_dir / "deck.pptx"
        pdf_path = export_dir / "deck.pdf"
        images_to_pptx(image_paths, pptx_path)
        images_to_pdf(image_paths, pdf_path)
        self.storage.add_artifact(job_id=job_id, kind=ArtifactKind.pptx, label="PPTX", path=pptx_path, mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        self.storage.add_artifact(job_id=job_id, kind=ArtifactKind.pdf, label="PDF", path=pdf_path, mime_type="application/pdf")
        await self._event(job_id, "exports", {"pptx": str(pptx_path), "pdf": str(pdf_path)})

    async def _run_poster(self, job_id: str, digest: dict[str, Any], sources: list[SourceOut]) -> None:
        job = self.storage.get_job(job_id)
        job_dir = self.storage.job_dir(job.session_id, job_id)
        llm = self._llm_client()
        aspect_ratio = str(job.options.get("aspect_ratio") or "9:16")
        await self._event(job_id, "status", {"message": "正在规划完整海报"})
        plan = await self._with_fallback_json(
            llm,
            prompts.POSTER_PLAN_SYSTEM,
            {"user_prompt": job.prompt, "digest": digest, "aspect_ratio": aspect_ratio, "options": job.options},
            fallback=_fallback_poster_plan(job.prompt, digest, aspect_ratio, job.options),
        )
        final_prompt = str(plan.get("prompt") or _poster_prompt_from_plan(plan, job.prompt))
        self.storage.update_job(job_id, plan=plan)
        self._write_job_json(job, "plan.json", plan)
        (job_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (job_dir / "prompts" / "poster.txt").write_text(final_prompt, encoding="utf-8")
        image_path = job_dir / "images" / "poster.png"
        profile = sensenova_profile_for_task(
            "poster",
            image_size=str(job.options.get("image_size", "2K")),
            aspect_ratio=str(plan.get("aspect_ratio") or aspect_ratio),
            seed=job.options.get("seed"),
        )
        await self._event(job_id, "progress", {"message": "SenseNova 正在生成完整大型海报", "profile": profile.to_metadata()})
        result = await get_image_driver().generate(
            prompt=final_prompt,
            output_path=image_path,
            image_size=str(job.options.get("image_size", "2K")),
            aspect_ratio=str(plan.get("aspect_ratio") or aspect_ratio),
            seed=job.options.get("seed"),
            profile=profile,
        )
        self.storage.add_artifact(job_id=job_id, kind=ArtifactKind.image, label="Poster", path=result.output_path, mime_type="image/png", metadata=result.metadata)

    async def _run_research_figure(
        self, job_id: str, digest: dict[str, Any], sources: list[SourceOut]
    ) -> None:
        job = self.storage.get_job(job_id)
        job_dir = self.storage.job_dir(job.session_id, job_id)
        llm = self._llm_client()
        await self._event(job_id, "status", {"message": "正在规划科研绘图/架构图"})
        plan = await self._with_fallback_json(
            llm,
            prompts.RESEARCH_FIGURE_PLAN_SYSTEM,
            {"user_prompt": job.prompt, "digest": digest, "options": job.options},
            fallback=_fallback_research_plan(job.prompt, digest, job.options),
        )
        final_prompt = str(plan.get("prompt") or _research_prompt_from_plan(plan, job.prompt))
        self.storage.update_job(job_id, plan=plan)
        self._write_job_json(job, "plan.json", plan)
        (job_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (job_dir / "prompts" / "research_figure.txt").write_text(final_prompt, encoding="utf-8")
        image_path = job_dir / "images" / "research_figure.png"
        profile = sensenova_profile_for_task(
            "research_figure",
            image_size=str(job.options.get("image_size", "2K")),
            aspect_ratio=str(plan.get("aspect_ratio") or job.options.get("aspect_ratio") or "16:9"),
            seed=job.options.get("seed"),
        )
        await self._event(job_id, "progress", {"message": "SenseNova 正在生成完整科研图", "profile": profile.to_metadata()})
        result = await get_image_driver().generate(
            prompt=final_prompt,
            output_path=image_path,
            image_size=str(job.options.get("image_size", "2K")),
            aspect_ratio=str(plan.get("aspect_ratio") or job.options.get("aspect_ratio") or "16:9"),
            seed=job.options.get("seed"),
            profile=profile,
        )
        self.storage.add_artifact(job_id=job_id, kind=ArtifactKind.image, label="Research Figure", path=result.output_path, mime_type="image/png", metadata=result.metadata)

    async def _run_edit(self, job_id: str, digest: dict[str, Any], sources: list[SourceOut]) -> None:
        job = self.storage.get_job(job_id)
        job_dir = self.storage.job_dir(job.session_id, job_id)
        images = [Path(s.path) for s in sources if s.kind == SourceKind.image]
        llm = self._llm_client()
        await self._event(job_id, "status", {"message": "正在生成图片二次编辑指令"})
        plan = await self._with_fallback_json(
            llm,
            prompts.EDIT_PLAN_SYSTEM,
            {"user_prompt": job.prompt, "digest": digest, "reference_images": [p.name for p in images], "options": job.options},
            fallback={"language": _output_language(job.options, job.prompt), "prompt": job.prompt, "preserve": [], "change": [job.prompt]},
        )
        final_prompt = str(plan.get("prompt") or job.prompt)
        self.storage.update_job(job_id, plan=plan)
        self._write_job_json(job, "plan.json", plan)
        (job_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (job_dir / "prompts" / "edit.txt").write_text(final_prompt, encoding="utf-8")
        image_path = job_dir / "images" / "edited.png"
        profile = sensenova_profile_for_task(
            "edit",
            image_size=str(job.options.get("image_size", "2K")),
            aspect_ratio=str(job.options.get("aspect_ratio") or "16:9"),
            seed=job.options.get("seed"),
        )
        await self._event(job_id, "progress", {"message": "SenseNova 正在执行图片二次绘制", "profile": profile.to_metadata()})
        driver = get_image_driver()
        if hasattr(driver, "edit"):
            result = await driver.edit(
                prompt=final_prompt,
                images=images,
                output_path=image_path,
                image_size=str(job.options.get("image_size", "2K")),
                aspect_ratio=str(job.options.get("aspect_ratio") or "16:9"),
                profile=profile,
            )
        else:
            result = await driver.generate(prompt=final_prompt, output_path=image_path)
        self.storage.add_artifact(job_id=job_id, kind=ArtifactKind.image, label="Edited Image", path=result.output_path, mime_type="image/png", metadata=result.metadata)

    async def _build_page_prompt(self, llm: LLMClient, plan: dict[str, Any], page: dict[str, Any]) -> str:
        fallback = _page_prompt_from_plan(plan, page)
        try:
            text = await llm.chat(
                [{"role": "user", "content": json_dumps({"style_brief": plan.get("style_brief"), "page": page}, indent=2)}],
                system=prompts.PAGE_PROMPT_SYSTEM,
                max_tokens=1600,
            )
            return _enforce_page_prompt_contract(text.strip() or fallback, plan, page)
        except Exception:
            return _enforce_page_prompt_contract(fallback, plan, page)

    async def _with_fallback_json(
        self,
        llm: LLMClient,
        system: str,
        user: dict[str, Any],
        *,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await llm.complete_json(system, user, max_tokens=6000)
        except (LLMClientError, Exception):
            return fallback

    def _write_job_json(self, job: JobOut, name: str, data: dict[str, Any]) -> Path:
        path = self.storage.job_dir(job.session_id, job.id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_dumps(data, indent=2), encoding="utf-8")
        return path

    async def _event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.broker.publish(self.storage, job_id, event_type, payload)

    def _llm_client(self) -> LLMClient:
        try:
            profile = LLMSettingsService(self.storage).active_profile()
            return LLMClient(profile)
        except Exception:
            return LLMClient()


async def schedule_job(storage: Storage, broker: EventBroker, job_id: str) -> None:
    runner = WorkflowRunner(storage, broker)
    await runner.run_job(job_id)


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out = dict(metadata or {})
    excerpt = str(out.get("text_excerpt", ""))
    if len(excerpt) > 5000:
        out["text_excerpt"] = excerpt[:5000] + "..."
    return out


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _output_language(options: dict[str, Any], prompt: str = "") -> str:
    raw = str((options or {}).get("output_language") or "auto").strip()
    aliases = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "cn": "zh-CN",
        "zh_tw": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_hk": "zh-TW",
        "zh-hk": "zh-TW",
        "english": "en",
        "en-us": "en",
        "japanese": "ja",
        "日本語": "ja",
        "日文": "ja",
    }
    normalized = aliases.get(raw.lower(), raw)
    if normalized in {"zh-CN", "zh-TW", "en", "ja"}:
        return normalized
    return "zh-CN" if _has_cjk(prompt) else "en"


def _lang_text(language: str, zh_cn: str, en: str, zh_tw: str | None = None, ja: str | None = None) -> str:
    if language == "en":
        return en
    if language == "ja":
        return ja or en
    if language == "zh-TW":
        return zh_tw or zh_cn
    return zh_cn


def _extract_page_count(text: str) -> int | None:
    import re

    m = re.search(r"(\d{1,2})\s*(页|pages?|slides?|张)", text or "", re.I)
    if not m:
        return None
    return max(1, min(60, int(m.group(1))))


def _fallback_ppt_plan(prompt: str, digest: dict[str, Any], page_count: int) -> dict[str, Any]:
    options = digest.get("_options") if isinstance(digest.get("_options"), dict) else {}
    language = _output_language(options, prompt)
    topic = digest.get("topic_summary") or prompt
    pages = []
    for i in range(1, page_count + 1):
        if i == 1:
            page_type = "cover"
            headline = str(topic)[:24]
            body = []
        elif i == page_count:
            page_type = "closing"
            headline = _lang_text(language, "总结与行动", "Summary and Next Steps", "總結與行動", "まとめと次のステップ")
            body = []
        elif i in {2, max(2, page_count // 2)}:
            page_type = "section"
            headline = _lang_text(language, f"核心章节 {i - 1}", f"Section {i - 1}", f"核心章節 {i - 1}", f"主要セクション {i - 1}")
            body = [_short_slide_point(str(x)) for x in (digest.get("key_points") or [prompt])[:4]]
        else:
            page_type = "content"
            headline = _lang_text(language, f"关键内容 {i - 1}", f"Key Point {i - 1}", f"關鍵內容 {i - 1}", f"重要ポイント {i - 1}")
            body = [_short_slide_point(str(x)) for x in (digest.get("key_points") or [prompt])[:4]]
        pages.append(
            {
                "page_no": i,
                "page_type": page_type,
                "headline": headline,
                "subheadline": str(topic)[:60] if i == 1 else "",
                "body_points": body,
                "callouts": [],
                "visual_hints": _lang_text(
                    language,
                    "完整 16:9 成品页，简洁网格，留白充足，少量图标或示意图，文字清晰",
                    "complete 16:9 finished slide with clean grid, generous whitespace, simple icons or diagram, readable text",
                    "完整 16:9 成品頁，簡潔網格，留白充足，少量圖示或示意圖，文字清晰",
                    "完成された16:9スライド、明快なグリッド、十分な余白、少量のアイコンまたは図解、読みやすい文字",
                ),
                "facts_to_preserve": [str(x) for x in (digest.get("key_points") or [])[:4]],
            }
        )
    return {
        "title": str(topic)[:40],
        "language": language,
        "page_count": page_count,
        "style_brief": _lang_text(
            language,
            "简洁干练的学术/商务汇报风格，浅色背景或克制深色背景，强网格，留白充足，少装饰，文字准确清晰。",
            "Concise professional academic/business deck style, light or restrained dark background, strong grid, generous whitespace, minimal decoration, crisp readable text.",
            "簡潔俐落的學術/商務簡報風格，淺色背景或克制深色背景，強網格，留白充足，少裝飾，文字準確清晰。",
            "簡潔でプロフェッショナルな学術/ビジネス発表スタイル、明るい背景または控えめな暗色背景、強いグリッド、十分な余白、装飾を抑え、文字は正確で読みやすい。",
        ),
        "pages": pages,
    }


def _page_prompt_from_plan(plan: dict[str, Any], page: dict[str, Any]) -> str:
    body = "；".join(str(x) for x in page.get("body_points", []))
    callouts = "；".join(str(x) for x in page.get("callouts", []))
    return (
        "A complete 16:9 widescreen presentation slide generated as one finished image. "
        f"Deck art direction: {plan.get('style_brief', '')}. "
        f"Slide type: {page.get('page_type')}. "
        "Use a clean professional grid, generous whitespace, restrained colors, simple charts or icons, and minimal decoration. "
        "Avoid cinematic neon, particles, busy 3D scenes, glowing clouds, and poster-like clutter. "
        f"Render the headline exactly: '{page.get('headline', '')}'. "
        f"Subtitle: '{page.get('subheadline', '')}'. "
        f"Readable body points on the image: {body}. "
        f"Readable callouts: {callouts}. "
        f"Composition: {page.get('visual_hints', '')}. "
        "All text must be baked into the image, sharp, correctly spelled, and not a placeholder."
    )


def _enforce_ppt_style_contract(plan: dict[str, Any]) -> dict[str, Any]:
    out = dict(plan or {})
    style = str(out.get("style_brief") or "").strip()
    contract = (
        "Default to concise professional academic/business presentation design: clean grid, generous whitespace, "
        "restrained colors, simple icons/charts, minimal decoration, and highly readable typography. "
        "Avoid cinematic neon, particle effects, busy 3D scenes, glowing clouds, and poster-like clutter unless explicitly requested."
    )
    out["style_brief"] = f"{style}\n{contract}".strip()
    pages = []
    for raw in out.get("pages", []) if isinstance(out.get("pages"), list) else []:
        page = dict(raw or {})
        page["headline"] = str(page.get("headline") or "").strip()[:96]
        body = page.get("body_points") if isinstance(page.get("body_points"), list) else []
        page["body_points"] = [_short_slide_point(str(x)) for x in body[:4] if str(x).strip()]
        visual = str(page.get("visual_hints") or "").strip()
        page["visual_hints"] = (
            f"{visual}. Clean slide layout with strong alignment, ample margins, simple visual metaphor, no decorative clutter."
        ).strip(". ")
        pages.append(page)
    out["pages"] = pages
    return out


def _enforce_page_prompt_contract(text: str, plan: dict[str, Any], page: dict[str, Any]) -> str:
    required_points = "; ".join(str(x) for x in page.get("body_points", [])[:4])
    contract = (
        "\nLayout contract: clean professional presentation page, strong grid alignment, generous whitespace, "
        "subtle accent color, simple diagram/icon/chart only when useful, no cinematic neon, no particle effects, "
        "no busy 3D scene, no decorative clutter.\n"
        f"Text contract: render headline exactly once as '{page.get('headline', '')}'. "
        f"Render these body points clearly if present: {required_points}. Keep all text away from edges and highly readable.\n"
        f"Visual contract: {page.get('visual_hints', '')}"
    )
    return (text.strip() + contract).strip()


def _short_slide_point(text: str) -> str:
    clean = " ".join(str(text or "").replace("\n", " ").split())
    if _has_cjk(clean):
        return clean[:28]
    words = clean.split()
    return " ".join(words[:12]) if len(words) > 12 else clean[:72]


def _fallback_poster_plan(prompt: str, digest: dict[str, Any], aspect_ratio: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    language = _output_language(options or {}, prompt)
    text_blocks = [str(x) for x in (digest.get("key_points") or [prompt])[:8]]
    final = _lang_text(
        language,
        f"生成一张完整 {aspect_ratio} 大型海报，主题为“{prompt}”。综合所有资料，把以下文字清晰烤进图中：{'；'.join(text_blocks)}。高密度信息图排版，标题醒目，分区清楚，简体中文准确可读。",
        f"Create one complete {aspect_ratio} large poster about {prompt}. Include readable text blocks: {'; '.join(text_blocks)}. High-density infographic layout.",
        f"生成一張完整 {aspect_ratio} 大型海報，主題為「{prompt}」。綜合所有資料，把以下文字清晰烤進圖中：{'；'.join(text_blocks)}。高密度資訊圖排版，標題醒目，分區清楚，繁體中文準確可讀。",
        f"{prompt} をテーマに、完全な {aspect_ratio} 大型ポスターを1枚作成する。次の文字を画像内に読みやすく配置する：{'；'.join(text_blocks)}。高密度のインフォグラフィック構成、明確なタイトル、整理されたセクション、日本語テキストを正確に読みやすく表示。",
    )
    return {
        "title": prompt[:40],
        "language": language,
        "aspect_ratio": aspect_ratio,
        "style_brief": _lang_text(language, "高密度信息海报，完整画布一次生成", "high-density full-canvas poster", "高密度資訊海報，完整畫布一次生成", "高密度のフルキャンバスポスター"),
        "on_image_text": text_blocks,
        "visual_structure": "full poster with clear sections",
        "facts_to_preserve": text_blocks,
        "prompt": final,
    }


def _poster_prompt_from_plan(plan: dict[str, Any], prompt: str) -> str:
    return (
        f"Create one complete {plan.get('aspect_ratio', '9:16')} full-canvas poster. "
        f"Title: {plan.get('title', prompt)}. Style: {plan.get('style_brief', '')}. "
        f"Structure: {plan.get('visual_structure', '')}. Required readable text: "
        + "; ".join(str(x) for x in plan.get("on_image_text", []))
    )


def _fallback_research_plan(prompt: str, digest: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    language = _output_language(options or {}, prompt)
    labels = [str(x)[:32] for x in (digest.get("visual_entities") or digest.get("key_points") or [prompt])[:8]]
    final = _lang_text(
        language,
        f"生成一张完整 16:9 科研绘图/架构图，主题“{prompt}”。图中必须包含标签：{'、'.join(labels)}。使用清晰箭头、分层结构、科研论文图形摘要风格，所有简体中文标签准确可读。",
        f"Create one complete 16:9 scientific figure about {prompt}. Required labels: {', '.join(labels)}. Use clear arrows and layered structure.",
        f"生成一張完整 16:9 科研繪圖/架構圖，主題「{prompt}」。圖中必須包含標籤：{'、'.join(labels)}。使用清晰箭頭、分層結構、科研論文圖形摘要風格，所有繁體中文標籤準確可讀。",
        f"{prompt} をテーマに、完全な16:9の研究図/構成図を作成する。必須ラベル：{'、'.join(labels)}。明確な矢印、階層構造、論文向け graphical abstract スタイルを使い、日本語ラベルを正確に読みやすく表示。",
    )
    return {
        "figure_type": _lang_text(language, "科研图解", "research figure", "科研圖解", "研究図解"),
        "language": language,
        "aspect_ratio": "16:9",
        "title": prompt[:40],
        "required_labels": labels,
        "relationships": [],
        "style_brief": _lang_text(language, "科研图形摘要，清晰标签，分层箭头", "graphical abstract with clear labels and arrows", "科研圖形摘要，清晰標籤，分層箭頭", "明確なラベルと階層矢印を備えた研究用 graphical abstract"),
        "facts_to_preserve": [str(x) for x in (digest.get("key_points") or [])[:6]],
        "prompt": final,
    }


def _research_prompt_from_plan(plan: dict[str, Any], prompt: str) -> str:
    return (
        f"Create one complete {plan.get('aspect_ratio', '16:9')} scientific figure. "
        f"Figure type: {plan.get('figure_type')}. Title: {plan.get('title', prompt)}. "
        f"Required readable labels: {'; '.join(str(x) for x in plan.get('required_labels', []))}. "
        f"Relationships/arrows: {'; '.join(str(x) for x in plan.get('relationships', []))}. "
        f"Style: {plan.get('style_brief', '')}."
    )
