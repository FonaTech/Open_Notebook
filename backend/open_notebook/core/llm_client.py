from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

from open_notebook.core.json_utils import json_dumps
from open_notebook.core.llm_config import (
    complete_chat_endpoint,
    extract_base_url,
    is_openai_compat_provider,
)
from open_notebook.models import LLMProfile


class LLMClientError(RuntimeError):
    pass


def default_chat_profile() -> LLMProfile:
    base = os.getenv("SN_CHAT_BASE_URL", "https://token.sensenova.cn/v1")
    return LLMProfile(
        id="default",
        provider="openai_compat",
        label="SenseNova Chat",
        model=os.getenv("SN_CHAT_MODEL", "sensenova-6.7-flash-lite"),
        base_url=extract_base_url(base),
        endpoint=complete_chat_endpoint(base),
        api_key=os.getenv("SN_CHAT_API_KEY", ""),
        source="environment",
    )


class LLMClient:
    def __init__(self, profile: LLMProfile | None = None):
        self.profile = profile or default_chat_profile()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4000,
        media_paths: list[Path] | None = None,
    ) -> str:
        profile = self.profile
        req_messages = list(messages)
        if system:
            req_messages = [{"role": "system", "content": system}] + req_messages
        if media_paths:
            req_messages = self._attach_images(req_messages, media_paths)

        provider = profile.provider.lower()
        if provider == "anthropic":
            return await self._chat_anthropic(req_messages, temperature, max_tokens)
        if provider == "custom_http":
            return await self._chat_custom(req_messages, temperature, max_tokens)
        if is_openai_compat_provider(provider):
            return await self._chat_openai(req_messages, temperature, max_tokens)
        if provider == "ollama":
            return await self._chat_ollama(req_messages, temperature, max_tokens)
        raise LLMClientError(f"Unsupported provider: {profile.provider}")

    async def complete_json(
        self,
        system: str,
        user: dict[str, Any] | str,
        *,
        max_tokens: int = 5000,
    ) -> dict[str, Any]:
        user_text = user if isinstance(user, str) else json_dumps(user, indent=2)
        text = await self.chat(
            [{"role": "user", "content": user_text}],
            system=system,
            max_tokens=max_tokens,
        )
        from open_notebook.core.json_utils import extract_json_object

        data = extract_json_object(text, {})
        if not data:
            raise LLMClientError("LLM did not return a JSON object")
        return data

    async def _chat_openai(
        self, messages: list[dict[str, Any]], temperature: float | None, max_tokens: int
    ) -> str:
        profile = self.profile
        endpoint = profile.endpoint or complete_chat_endpoint(profile.base_url)
        payload = {
            "model": profile.model,
            "messages": messages,
            "temperature": profile.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = self._headers()
        raw = await self._post_json(endpoint, payload, headers)
        return self._extract_openai_text(raw)

    async def _chat_ollama(
        self, messages: list[dict[str, Any]], temperature: float | None, max_tokens: int
    ) -> str:
        profile = self.profile
        base = profile.base_url.rstrip("/")
        payload = {
            "model": profile.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": profile.temperature if temperature is None else temperature,
                "num_predict": max_tokens,
            },
        }
        raw = await self._post_json(f"{base}/api/chat", payload, {"Content-Type": "application/json"})
        msg = raw.get("message") if isinstance(raw, dict) else {}
        if isinstance(msg, dict):
            content = str(msg.get("content") or "").strip()
            if content:
                return content
            for key in ("thinking", "reasoning", "reasoning_content"):
                value = str(msg.get(key) or "").strip()
                if value:
                    return value
        for key in ("response", "content", "output"):
            value = str(raw.get(key) or "").strip()
            if value:
                return value
        return ""

    async def _chat_anthropic(
        self, messages: list[dict[str, Any]], temperature: float | None, max_tokens: int
    ) -> str:
        profile = self.profile
        endpoint = profile.endpoint or profile.base_url.rstrip("/") + "/v1/messages"
        system_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
        user_messages = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("role") != "system"
        ]
        payload: dict[str, Any] = {
            "model": profile.model,
            "messages": user_messages,
            "temperature": profile.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        headers = {
            "x-api-key": profile.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        raw = await self._post_json(endpoint, payload, headers)
        blocks = raw.get("content", []) if isinstance(raw, dict) else []
        if isinstance(blocks, list):
            return "\n".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict)).strip()
        return str(blocks or "").strip()

    async def _chat_custom(
        self, messages: list[dict[str, Any]], temperature: float | None, max_tokens: int
    ) -> str:
        profile = self.profile
        if not profile.endpoint:
            raise LLMClientError("custom_http endpoint is empty")
        if profile.payload_template:
            rendered = (
                profile.payload_template.replace("${model}", profile.model)
                .replace("${messages_json}", json_dumps(messages))
                .replace("${temperature}", str(profile.temperature if temperature is None else temperature))
                .replace("${max_tokens}", str(max_tokens))
                .replace("${api_key}", profile.api_key)
            )
            payload = json.loads(rendered)
        else:
            payload = {
                "model": profile.model,
                "messages": messages,
                "temperature": profile.temperature if temperature is None else temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
        raw = await self._post_json(profile.endpoint, payload, self._headers())
        if isinstance(raw, dict) and "choices" in raw:
            return self._extract_openai_text(raw)
        return str(raw.get("content") or raw.get("output") or "").strip()

    async def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict:
        timeout = httpx.Timeout(float(self.profile.request_timeout), connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMClientError(f"HTTP {response.status_code}: {response.text[:500]}") from exc
            return response.json()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self.profile.headers or {})
        if self.profile.api_key and not any(k.lower() == "authorization" for k in headers):
            headers["Authorization"] = f"Bearer {self.profile.api_key}"
        return {k: v.replace("${api_key}", self.profile.api_key) for k, v in headers.items()}

    @staticmethod
    def _extract_openai_text(raw: dict[str, Any]) -> str:
        choices = raw.get("choices", []) if isinstance(raw, dict) else []
        if not choices:
            return ""
        msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return "\n".join(x for x in parts if x).strip()
        return str(content or "").strip()

    @staticmethod
    def _attach_images(messages: list[dict[str, Any]], media_paths: list[Path]) -> list[dict[str, Any]]:
        out = [dict(m) for m in messages]
        user_index = next((i for i in range(len(out) - 1, -1, -1) if out[i].get("role") == "user"), -1)
        if user_index < 0:
            out.append({"role": "user", "content": ""})
            user_index = len(out) - 1
        base_text = str(out[user_index].get("content") or "")
        parts: list[dict[str, Any]] = [{"type": "text", "text": base_text}]
        for path in media_paths:
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        out[user_index]["content"] = parts
        return out
