from __future__ import annotations

import os
from typing import Any

from open_notebook.config import get_settings
from open_notebook.core.llm_config import (
    complete_chat_endpoint,
    extract_base_url,
    parse_llm_config_profiles,
)
from open_notebook.models import LLMProfile, ModelCatalog
from open_notebook.services.storage import Storage

SETTING_KEY = "llm_config"


class LLMSettingsService:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.settings = get_settings()

    def load(self) -> dict[str, Any]:
        saved = self.storage.get_setting(SETTING_KEY, {})
        if saved:
            return saved
        env_config = {
            "profiles": [
                {
                    "id": "sensenova-chat",
                    "provider": "openai_compat",
                    "label": "SenseNova Chat",
                    "model": os.getenv("SN_CHAT_MODEL", "sensenova-6.7-flash-lite"),
                    "base_url": os.getenv("SN_CHAT_BASE_URL", "https://token.sensenova.cn/v1"),
                    "api_key": os.getenv("SN_CHAT_API_KEY", ""),
                    "capabilities": {"image_input": True},
                }
            ],
            "default_profile_id": "sensenova-chat",
        }
        parsed = parse_llm_config_profiles(
            env_config, self.settings.default_ollama_url, self.settings.default_ollama_model
        )
        data = {
            "profiles": [p.model_dump() for p in parsed["profiles"]],
            "active_profile_id": parsed["default_profile_id"],
        }
        self.storage.set_setting(SETTING_KEY, data)
        return data

    def import_config(self, config: dict[str, Any]) -> ModelCatalog:
        parsed = parse_llm_config_profiles(
            config, self.settings.default_ollama_url, self.settings.default_ollama_model
        )
        data = {
            "profiles": [p.model_dump() for p in parsed["profiles"]],
            "active_profile_id": parsed["default_profile_id"],
        }
        self.storage.set_setting(SETTING_KEY, data)
        return self.catalog()

    def export_config(self) -> dict[str, Any]:
        data = self.load()
        return {
            "profiles": data.get("profiles", []),
            "default_profile_id": data.get("active_profile_id", ""),
        }

    def active_profile(self) -> LLMProfile:
        data = self.load()
        active = data.get("active_profile_id")
        profiles = [LLMProfile(**p) for p in data.get("profiles", [])]
        for profile in profiles:
            if profile.id == active:
                return profile
        if profiles:
            return profiles[0]
        raise RuntimeError("no LLM profiles configured")

    def select(self, selection: str) -> ModelCatalog:
        raw = str(selection or "").strip()
        if "::" in raw:
            pid, model = raw.split("::", 1)
        else:
            pid, model = raw, ""
        data = self.load()
        profiles = data.get("profiles", [])
        for profile in profiles:
            if profile.get("id") == pid:
                if model:
                    profile["model"] = model
                    profile["selection"] = f"{pid}::{model}"
                data["active_profile_id"] = pid
                self.storage.set_setting(SETTING_KEY, data)
                return self.catalog()
        raise KeyError(f"profile not found: {pid}")

    def catalog(self) -> ModelCatalog:
        data = self.load()
        active_id = data.get("active_profile_id", "")
        profiles = [LLMProfile(**p) for p in data.get("profiles", [])]
        options = []
        for profile in profiles:
            selection = f"{profile.id}::{profile.model}"
            options.append(
                {
                    "selection": selection,
                    "profile_id": profile.id,
                    "provider": profile.provider,
                    "model": profile.model,
                    "label": f"{profile.label} | {profile.model or '(no-model)'}",
                    "source": profile.source,
                    "capabilities": profile.capabilities,
                    "thinking_stream": profile.thinking_stream,
                }
            )
        active = next((p for p in profiles if p.id == active_id), profiles[0] if profiles else None)
        selected = f"{active.id}::{active.model}" if active else ""
        return ModelCatalog(
            selected=selected,
            provider=active.provider if active else "",
            options=options,
            active_capabilities=active.capabilities if active else {},
        )

    async def probe(self) -> dict[str, Any]:
        active = self.active_profile()
        if active.provider == "ollama":
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(active.base_url.rstrip("/") + "/api/tags")
                response.raise_for_status()
                return {"status": "ok", "provider": "ollama", "models": response.json().get("models", [])}
        if active.provider in {"openai_compat", "siliconflow", "vllm", "lmstudio", "glm", "kimi", "openrouter"}:
            import httpx

            base = extract_base_url(active.base_url or active.endpoint)
            headers = {}
            if active.api_key:
                headers["Authorization"] = f"Bearer {active.api_key}"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(base.rstrip("/") + "/models", headers=headers)
                if response.status_code == 404:
                    response = await client.get(base.rstrip("/") + "/v1/models", headers=headers)
                response.raise_for_status()
                return {"status": "ok", "provider": active.provider, "raw": response.json()}
        return {"status": "ok", "provider": active.provider, "message": "probe not implemented"}
