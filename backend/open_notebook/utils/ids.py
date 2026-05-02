from __future__ import annotations

import re
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def slugify(value: str, fallback: str = "task") -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", (value or "").strip(), flags=re.UNICODE)
    text = text.strip("._-")
    return text[:60] or fallback
