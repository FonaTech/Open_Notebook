from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SenseNovaGenerationProfile:
    name: str
    image_size: str
    aspect_ratio: str
    cfg_scale: float
    cfg_norm: str
    timestep_shift: float
    cfg_interval: tuple[float, float]
    num_steps: int
    batch_size: int
    dtype: str
    device: str
    attn_backend: str
    think_mode: bool
    seed: int

    def to_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["cfg_interval"] = list(self.cfg_interval)
        return data


TASK_DEFAULT_ASPECTS = {
    "ppt": "16:9",
    "poster": "9:16",
    "research_figure": "16:9",
    "edit": "16:9",
}


def sensenova_profile_for_task(
    task: str,
    *,
    image_size: str = "2K",
    aspect_ratio: str | None = None,
    seed: int | None = None,
) -> SenseNovaGenerationProfile:
    """Return stable SenseNova-U1 generation parameters for an Open_Notebook task.

    Defaults intentionally mirror the official SenseNova-U1 transformers T2I
    example: cfg_scale=4.0, cfg_norm=none, timestep_shift=3.0, num_steps=50,
    dtype=bfloat16. Environment variables can override these for local
    experiments, but generated artifacts record the effective profile.
    """
    default_aspect = TASK_DEFAULT_ASPECTS.get(task, "16:9")
    return SenseNovaGenerationProfile(
        name=os.getenv("SENSENOVA_U1_PROFILE", f"official-u1-{task}"),
        image_size=image_size,
        aspect_ratio=aspect_ratio or default_aspect,
        cfg_scale=float(os.getenv("SENSENOVA_U1_CFG_SCALE", "4.0")),
        cfg_norm=os.getenv("SENSENOVA_U1_CFG_NORM", "none"),
        timestep_shift=float(os.getenv("SENSENOVA_U1_TIMESTEP_SHIFT", "3.0")),
        cfg_interval=_parse_interval(os.getenv("SENSENOVA_U1_CFG_INTERVAL", "0.0,1.0")),
        num_steps=int(os.getenv("SENSENOVA_U1_NUM_STEPS", "50")),
        batch_size=int(os.getenv("SENSENOVA_U1_BATCH_SIZE", "1")),
        dtype=os.getenv("SENSENOVA_U1_DTYPE", "bfloat16"),
        device=os.getenv("SENSENOVA_U1_DEVICE", "mps"),
        attn_backend=os.getenv("SENSENOVA_U1_ATTN_BACKEND", "sdpa"),
        think_mode=os.getenv("SENSENOVA_U1_THINK_MODE", "0").lower() in {"1", "true", "yes", "on"},
        seed=int(seed if seed is not None else os.getenv("SENSENOVA_U1_SEED", "42")),
    )


def _parse_interval(raw: str) -> tuple[float, float]:
    parts = [p.strip() for p in raw.replace(":", ",").split(",") if p.strip()]
    if len(parts) != 2:
        return (0.0, 1.0)
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return (0.0, 1.0)
    return (lo, hi)
