from __future__ import annotations

import json
import re
from typing import Any


def json_dumps(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent)


def parse_json_object(text: str, default: dict | None = None) -> dict:
    if default is None:
        default = {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default


def extract_json_object(text: str, default: dict | None = None) -> dict:
    if default is None:
        default = {}
    raw = (text or "").strip()
    if not raw:
        return default
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    parsed = parse_json_object(raw, {})
    if parsed:
        return parsed
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return default
    return parse_json_object(match.group(0), default)
