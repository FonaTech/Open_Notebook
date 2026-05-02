from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from open_notebook.models import LLMProfile

DEFAULT_REQUEST_TIMEOUT = 120
MIN_TIMEOUT_SECONDS = 10
MAX_TIMEOUT_SECONDS = 1800

MEDIA_CAPABILITY_KEYS = {
    "image_input",
    "audio_input",
    "video_input",
    "image_output",
    "audio_output",
    "video_output",
}

OPENAI_COMPAT_PROVIDER_NAMES = {
    "openai_compat",
    "siliconflow",
    "vllm",
    "lmstudio",
    "glm",
    "kimi",
    "openrouter",
}
OPENAI_LIKE_PROVIDER_NAMES = OPENAI_COMPAT_PROVIDER_NAMES | {"custom_http"}


def sanitize_profile_id(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw or "").strip())
    text = text.strip(".-")
    return text or "profile"


def normalize_timeout_seconds(
    value: object,
    *,
    minimum: int = MIN_TIMEOUT_SECONDS,
    maximum: int = MAX_TIMEOUT_SECONDS,
    fallback: int = DEFAULT_REQUEST_TIMEOUT,
) -> int:
    try:
        n = int(float(str(value)))
    except Exception:
        n = fallback
    return max(minimum, min(maximum, n))


def normalize_openai_compat_provider_name(raw: str) -> str:
    value = str(raw or "").strip().lower().replace("-", "_")
    aliases = {
        "openai": "openai_compat",
        "openai_compat": "openai_compat",
        "siliconflow": "siliconflow",
        "vllm": "vllm",
        "lmstudio": "lmstudio",
        "glm": "glm",
        "kimi": "kimi",
        "moonshot": "kimi",
        "openrouter": "openrouter",
        "custom": "custom_http",
        "custom_http": "custom_http",
    }
    return aliases.get(value, value or "openai_compat")


def is_openai_compat_provider(provider: str) -> bool:
    return normalize_openai_compat_provider_name(provider) in OPENAI_COMPAT_PROVIDER_NAMES


def is_openai_like_provider(provider: str) -> bool:
    return normalize_openai_compat_provider_name(provider) in OPENAI_LIKE_PROVIDER_NAMES


def extract_base_url(endpoint_or_base: str) -> str:
    s = (endpoint_or_base or "").strip()
    if not s:
        return ""
    low = s.lower().rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if low.endswith(suffix):
            return s[: -len(suffix)].rstrip("/")
    return s.rstrip("/")


def complete_chat_endpoint(endpoint_or_base: str) -> str:
    s = (endpoint_or_base or "").strip()
    if not s:
        return ""
    low = s.lower().rstrip("/")
    if low.endswith("/chat/completions") or low.endswith("/v1/chat/completions"):
        return s.rstrip("/")
    if low.endswith("/v1") or "/v1beta/openai" in low:
        return s.rstrip("/") + "/chat/completions"
    return s.rstrip("/") + "/v1/chat/completions"


def default_multimodal_capabilities() -> dict[str, bool]:
    return {
        "image_input": False,
        "audio_input": False,
        "video_input": False,
        "image_output": False,
        "audio_output": False,
        "video_output": False,
    }


def _to_bool_like(raw: object, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def infer_model_multimodal_capabilities(provider: str, model: str) -> dict[str, bool]:
    caps = default_multimodal_capabilities()
    p = str(provider or "").strip().lower()
    m = str(model or "").strip().lower()
    if p == "ollama":
        if any(x in m for x in ("llava", "vision", "vl", "qwen2.5vl", "qwen-vl")):
            caps["image_input"] = True
        return caps
    if p == "anthropic":
        caps["image_input"] = True
        return caps
    if is_openai_like_provider(p):
        if any(x in m for x in ("gpt-4o", "vision", "vl", "gemini", "qwen-vl", "glm-4v")):
            caps["image_input"] = True
        if any(x in m for x in ("image", "dall-e", "gpt-image")):
            caps["image_output"] = True
    return caps


def parse_capability_overrides(raw: object) -> dict[str, bool]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, bool] = {}
    aliases = {
        "vision": "image_input",
        "images": "image_input",
        "image": "image_input",
        "image_generation": "image_output",
        "t2i": "image_output",
    }
    for key, value in raw.items():
        k = aliases.get(str(key).strip().lower(), str(key).strip().lower())
        if k in MEDIA_CAPABILITY_KEYS:
            out[k] = _to_bool_like(value)
    return out


def merge_multimodal_capabilities(
    base: dict[str, bool], override: dict[str, bool]
) -> dict[str, bool]:
    out = default_multimodal_capabilities()
    out.update(base or {})
    out.update(override or {})
    return out


def parse_media_endpoints(raw: object) -> dict[str, str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("image", "audio", "video"):
        value = str(raw.get(key, "") or "").strip()
        if value:
            out[key] = value
    return out


def looks_like_llm_config(config: dict) -> bool:
    if not isinstance(config, dict) or not config:
        return False
    keys = {str(k).strip().lower() for k in config.keys()}
    markers = {
        "provider",
        "profiles",
        "model_profiles",
        "llm_profiles",
        "llms",
        "default_profile_id",
        "active_profile_id",
        "selected_profile_id",
        "ollama_url",
        "ollama_model",
        "openai_url",
        "openai_model",
        "openai_key",
        "siliconflow_url",
        "siliconflow_model",
        "siliconflow_key",
        "vllm_url",
        "vllm_model",
        "lmstudio_url",
        "lmstudio_model",
        "anthropic_url",
        "anthropic_model",
        "anthropic_key",
        "glm_url",
        "glm_model",
        "glm_key",
        "kimi_url",
        "kimi_model",
        "kimi_key",
        "openrouter_url",
        "openrouter_model",
        "openrouter_key",
        "custom_url",
        "custom_model",
        "custom_key",
        "custom_headers",
        "custom_payload",
        "capabilities",
        "multimodal_capabilities",
        "model_capabilities",
        "media_endpoints",
        "temperature",
        "request_timeout",
    }
    return bool(keys & markers)


def _parse_json_dict(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def parse_llm_config_profiles(
    config: dict,
    default_ollama_url: str = "http://localhost:11434",
    default_ollama_model: str = "qwen2.5:7b",
) -> dict:
    config = config if isinstance(config, dict) else {}
    model_caps_map = _parse_json_dict(config.get("model_capabilities", {}))
    raw_global_caps = _parse_json_dict(config.get("multimodal_capabilities", config.get("capabilities", {})))
    raw_global_media_endpoints = _parse_json_dict(config.get("media_endpoints", {}))

    def provider_aliases(provider_key: str, provider: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in (
            provider_key,
            str(provider_key or "").replace("-", "_"),
            provider,
            str(provider or "").replace("-", "_"),
            normalize_openai_compat_provider_name(provider),
        ):
            key = str(raw or "").strip()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
        return out

    def build_profile_capabilities(provider_key: str, provider: str, model: str) -> dict[str, bool]:
        caps = infer_model_multimodal_capabilities(provider, model)
        if any(k in raw_global_caps for k in MEDIA_CAPABILITY_KEYS):
            caps = merge_multimodal_capabilities(caps, parse_capability_overrides(raw_global_caps))
        for alias in provider_aliases(provider_key, provider):
            if raw_global_caps.get(alias) is not None:
                caps = merge_multimodal_capabilities(
                    caps, parse_capability_overrides(raw_global_caps.get(alias))
                )
            if config.get(f"{alias}_capabilities") is not None:
                caps = merge_multimodal_capabilities(
                    caps, parse_capability_overrides(config.get(f"{alias}_capabilities"))
                )
        model_override = model_caps_map.get(model) or model_caps_map.get(str(model or "").lower())
        if model_override is not None:
            caps = merge_multimodal_capabilities(caps, parse_capability_overrides(model_override))
        return caps

    def build_profile_media_endpoints(provider_key: str) -> dict[str, str]:
        out: dict[str, str] = {}
        if any(k in raw_global_media_endpoints for k in ("image", "audio", "video")):
            out.update(parse_media_endpoints(raw_global_media_endpoints))
        for alias in provider_aliases(provider_key, provider_key):
            out.update(parse_media_endpoints(raw_global_media_endpoints.get(alias)))
            out.update(parse_media_endpoints(config.get(f"{alias}_media_endpoints")))
            for media_type in ("image", "audio", "video"):
                specific = str(config.get(f"{alias}_{media_type}_endpoint", "") or "").strip()
                if specific:
                    out[media_type] = specific
        return out

    def default_model_for_provider(provider: str) -> str:
        defaults = {
            "ollama": default_ollama_model,
            "openai_compat": "gpt-4o-mini",
            "siliconflow": "Qwen/Qwen3-Next-80B-A3B-Instruct",
            "vllm": "auto",
            "lmstudio": "auto",
            "anthropic": "claude-sonnet-4-20250514",
            "glm": "glm-4-flash",
            "kimi": "moonshot-v1-8k",
            "openrouter": "meta-llama/llama-3.1-8b-instruct",
            "custom_http": "custom-model",
        }
        return defaults.get(str(provider or "").lower(), "model")

    def normalize_profile_provider(raw: str) -> str:
        value = str(raw or "").strip().lower().replace("-", "_")
        if not value:
            return ""
        if value in {"ollama", "anthropic"}:
            return value
        if is_openai_like_provider(value):
            return normalize_openai_compat_provider_name(value)
        return value

    def parse_profile_headers(raw: object) -> dict[str, str]:
        obj = _parse_json_dict(raw)
        return {str(k): str(v) for k, v in obj.items()}

    profiles: list[LLMProfile] = []
    provider = str(config.get("provider", "")).strip().lower()
    temperature = float(config.get("temperature", 0.2) or 0.2)
    timeout = normalize_timeout_seconds(config.get("request_timeout", DEFAULT_REQUEST_TIMEOUT))
    thinking_stream_default = bool(config.get("thinking_stream", config.get("stream_thinking", False)))
    explicit_default_profile_id = sanitize_profile_id(
        str(
            config.get("default_profile_id")
            or config.get("active_profile_id")
            or config.get("selected_profile_id")
            or ""
        )
    )
    explicit_default_candidates: list[str] = []

    raw_profiles = (
        config.get("profiles")
        if config.get("profiles") is not None
        else config.get("model_profiles")
        if config.get("model_profiles") is not None
        else config.get("llm_profiles")
        if config.get("llm_profiles") is not None
        else config.get("llms")
    )
    explicit_rows: list[dict] = []
    if isinstance(raw_profiles, dict):
        for key, value in raw_profiles.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("id", key)
                explicit_rows.append(row)
    elif isinstance(raw_profiles, list):
        explicit_rows.extend([dict(x) for x in raw_profiles if isinstance(x, dict)])

    def add_profile(**kwargs: object) -> None:
        profiles.append(LLMProfile(**kwargs))

    for idx, raw_profile in enumerate(explicit_rows):
        provider_hint = (
            raw_profile.get("provider")
            or raw_profile.get("vendor")
            or raw_profile.get("type")
            or raw_profile.get("kind")
            or ""
        )
        p = normalize_profile_provider(str(provider_hint or ""))
        if not p:
            inferred = raw_profile.get("id") or raw_profile.get("profile_id") or raw_profile.get("name") or ""
            p = normalize_profile_provider(str(inferred or ""))
        base_hint = str(
            raw_profile.get("base_url")
            or raw_profile.get("url")
            or raw_profile.get("api_base")
            or raw_profile.get("api_url")
            or raw_profile.get("host")
            or raw_profile.get("endpoint")
            or ""
        ).strip()
        endpoint = str(
            raw_profile.get("endpoint")
            or raw_profile.get("chat_endpoint")
            or raw_profile.get("completion_endpoint")
            or ""
        ).strip()
        if not p and (base_hint or endpoint):
            p = "openai_compat"
        if not p:
            continue
        profile_id = sanitize_profile_id(
            str(
                raw_profile.get("id")
                or raw_profile.get("profile_id")
                or raw_profile.get("name")
                or raw_profile.get("label")
                or f"profile-{idx + 1}"
            )
        )
        label = str(raw_profile.get("label") or raw_profile.get("name") or profile_id).strip()
        model = str(
            raw_profile.get("model") or raw_profile.get("model_name") or raw_profile.get("default_model") or ""
        ).strip() or default_model_for_provider(p)
        base_url = extract_base_url(base_hint or endpoint)
        if p == "ollama" and not base_url:
            base_url = extract_base_url(default_ollama_url)
        api_key = str(raw_profile.get("api_key") or raw_profile.get("key") or raw_profile.get("token") or "").strip()
        headers = parse_profile_headers(raw_profile.get("headers"))
        payload_template = str(raw_profile.get("payload_template") or raw_profile.get("payload") or raw_profile.get("template") or "").strip()
        if p == "anthropic":
            anth_base = base_url or "https://api.anthropic.com"
            endpoint = endpoint or anth_base.rstrip("/") + "/v1/messages"
            base_url = extract_base_url(anth_base)
        elif is_openai_like_provider(p):
            endpoint = endpoint or complete_chat_endpoint(base_url)
        caps_key = str(raw_profile.get("capabilities_key") or profile_id or p)
        capabilities = build_profile_capabilities(caps_key, p, model)
        if raw_profile.get("capabilities") is not None:
            capabilities = merge_multimodal_capabilities(
                capabilities, parse_capability_overrides(raw_profile.get("capabilities"))
            )
        media_endpoints = build_profile_media_endpoints(caps_key)
        media_endpoints.update(parse_media_endpoints(raw_profile.get("media_endpoints")))
        add_profile(
            id=profile_id,
            provider=p,
            label=label or profile_id,
            model=model,
            base_url=base_url,
            endpoint=endpoint,
            api_key=api_key,
            headers=headers,
            payload_template=payload_template,
            thinking_stream=bool(
                raw_profile.get(
                    "thinking_stream",
                    raw_profile.get("stream_thinking", raw_profile.get("thinking", thinking_stream_default)),
                )
            ),
            temperature=float(raw_profile.get("temperature", temperature) or temperature),
            request_timeout=normalize_timeout_seconds(raw_profile.get("request_timeout", timeout)),
            capabilities=capabilities,
            media_endpoints=media_endpoints,
            source=str(raw_profile.get("source", "profiles") or "profiles"),
        )
        if raw_profile.get("default") or raw_profile.get("active") or raw_profile.get("selected"):
            explicit_default_candidates.append(profile_id)

    def env_or_config(name: str, fallback: str = "") -> str:
        return str(config.get(name, os.getenv(name.upper(), fallback)) or "").strip()

    if provider == "ollama" or config.get("ollama_url") or config.get("ollama_model"):
        model = str(config.get("ollama_model", default_ollama_model) or default_ollama_model)
        add_profile(
            id="ollama",
            provider="ollama",
            label="Ollama",
            model=model,
            base_url=extract_base_url(str(config.get("ollama_url", default_ollama_url))),
            temperature=temperature,
            request_timeout=timeout,
            capabilities=build_profile_capabilities("ollama", "ollama", model),
            media_endpoints=build_profile_media_endpoints("ollama"),
        )

    flat_defs = [
        ("openai", "openai_compat", "OpenAI Compatible", "openai", "gpt-4o-mini", ""),
        ("siliconflow", "siliconflow", "SiliconFlow", "siliconflow", "Qwen/Qwen3-Next-80B-A3B-Instruct", ""),
        ("vllm", "vllm", "vLLM", "vllm", "auto", "http://localhost:8000/v1"),
        ("lmstudio", "lmstudio", "LM Studio", "lmstudio", "auto", "http://localhost:1234/v1"),
        ("anthropic", "anthropic", "Anthropic", "anthropic", "claude-sonnet-4-20250514", "https://api.anthropic.com"),
        ("glm", "glm", "GLM", "glm", "glm-4-flash", "https://open.bigmodel.cn/api/paas/v4"),
        ("kimi", "kimi", "KIMI (Moonshot)", "kimi", "moonshot-v1-8k", "https://api.moonshot.cn/v1"),
        ("openrouter", "openrouter", "OpenRouter", "openrouter", "meta-llama/llama-3.1-8b-instruct", "https://openrouter.ai/api/v1"),
    ]
    for pid, p, label, prefix, default_model, default_base in flat_defs:
        url = str(config.get(f"{prefix}_url", "") or "").strip()
        model = str(config.get(f"{prefix}_model", "") or "").strip()
        key = str(config.get(f"{prefix}_key", "") or "").strip()
        if not (url or model or key):
            continue
        base = extract_base_url(url or default_base)
        endpoint = base.rstrip("/") + "/v1/messages" if p == "anthropic" else complete_chat_endpoint(base)
        add_profile(
            id=pid,
            provider=p,
            label=label,
            model=model or default_model,
            base_url=base,
            endpoint=endpoint,
            api_key=key,
            temperature=temperature,
            request_timeout=timeout,
            capabilities=build_profile_capabilities(pid, p, model or default_model),
            media_endpoints=build_profile_media_endpoints(pid),
        )

    custom_url = str(config.get("custom_url", "") or "").strip()
    if custom_url:
        add_profile(
            id="custom",
            provider="custom_http",
            label="Custom HTTP",
            model=str(config.get("custom_model", "") or config.get("openai_model", "") or "custom-model"),
            base_url=extract_base_url(custom_url),
            endpoint=custom_url,
            api_key=str(config.get("custom_key", "") or "").strip(),
            headers=_parse_json_dict(config.get("custom_headers", {})),
            payload_template=str(config.get("custom_payload", "") or "").strip(),
            temperature=temperature,
            request_timeout=timeout,
            capabilities=build_profile_capabilities("custom", "custom_http", str(config.get("custom_model", "") or "custom-model")),
            media_endpoints=build_profile_media_endpoints("custom"),
        )

    if not profiles:
        add_profile(
            id="default",
            provider="openai_compat",
            label="SenseNova Chat",
            model=env_or_config("sn_chat_model", os.getenv("SN_CHAT_MODEL", "sensenova-6.7-flash-lite")),
            base_url=extract_base_url(env_or_config("sn_chat_base_url", os.getenv("SN_CHAT_BASE_URL", "https://token.sensenova.cn/v1"))),
            endpoint=complete_chat_endpoint(env_or_config("sn_chat_base_url", os.getenv("SN_CHAT_BASE_URL", "https://token.sensenova.cn/v1"))),
            api_key=env_or_config("sn_chat_api_key", os.getenv("SN_CHAT_API_KEY", "")),
            temperature=temperature,
            request_timeout=timeout,
            capabilities=infer_model_multimodal_capabilities("openai_compat", os.getenv("SN_CHAT_MODEL", "sensenova-6.7-flash-lite")),
            source="environment",
        )

    ids = {p.id for p in profiles}
    default_profile_id = explicit_default_profile_id if explicit_default_profile_id in ids else ""
    if not default_profile_id:
        default_profile_id = next((x for x in explicit_default_candidates if x in ids), "")
    if not default_profile_id:
        default_profile_id = next(
            (p.id for p in profiles if p.id == provider or p.provider == normalize_openai_compat_provider_name(provider)),
            profiles[0].id,
        )
    return {"profiles": profiles, "default_profile_id": default_profile_id}


def _resolve_local_path(raw: str, base_dir: Path) -> Path:
    src = str(raw or "").strip()
    if not src:
        raise ValueError("empty path")
    parsed = urlparse(src)
    if parsed.scheme.lower() == "file":
        file_part = unquote(parsed.path or "")
        if parsed.netloc:
            file_part = f"/{parsed.netloc}{file_part}"
        path = Path(file_part)
    else:
        path = Path(src).expanduser()
    return (base_dir / path).resolve() if not path.is_absolute() else path.resolve()
