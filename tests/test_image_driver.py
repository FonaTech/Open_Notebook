from pathlib import Path

import asyncio

from PIL import Image

from open_notebook.core.generation_profiles import sensenova_profile_for_task
from open_notebook.core.image_driver import FakeImageDriver, inspect_image_quality, resolve_size


def test_resolve_size():
    assert resolve_size("2K", "16:9") == "2752x1536"
    assert resolve_size("1K", "1:1") == "1344x1344"


def test_fake_driver(tmp_path: Path):
    out = tmp_path / "image.png"
    result = asyncio.run(
        FakeImageDriver().generate(prompt="测试海报", output_path=out, aspect_ratio="16:9")
    )
    assert result.status == "ok"
    assert out.exists()
    assert out.stat().st_size > 1000


def test_official_u1_profile_defaults():
    profile = sensenova_profile_for_task("ppt", image_size="2K", aspect_ratio="16:9")
    assert profile.num_steps == 50
    assert profile.cfg_scale == 4.0
    assert profile.cfg_norm == "none"
    assert profile.timestep_shift == 3.0
    assert profile.dtype == "bfloat16"
    assert profile.aspect_ratio == "16:9"


def test_quality_gate_rejects_flat_image(tmp_path: Path):
    out = tmp_path / "flat.png"
    Image.new("RGB", (2720, 1536), (0, 0, 0)).save(out)
    quality = inspect_image_quality(out)
    assert quality["ok"] is False
    assert "flat" in quality["reason"]
