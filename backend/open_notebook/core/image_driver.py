from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from open_notebook.core.generation_profiles import (
    SenseNovaGenerationProfile,
    sensenova_profile_for_task,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_U1_MODEL_PATH = "models/Full"
DEFAULT_U1_SOURCE_REPO = "https://github.com/OpenSenseNova/SenseNova-U1.git"
DEFAULT_U1_SOURCE_ROOT = "../SenseNova-U1-main/src"
LOCAL_U1_SOURCE_CANDIDATES = (
    DEFAULT_U1_SOURCE_ROOT,
    "SenseNova-U1-main/src",
)


BUCKETS_1K: dict[str, tuple[int, int]] = {
    "2:3": (1088, 1632),
    "3:2": (1632, 1088),
    "3:4": (1152, 1536),
    "4:3": (1536, 1152),
    "4:5": (1184, 1472),
    "5:4": (1472, 1184),
    "1:1": (1344, 1344),
    "16:9": (1792, 992),
    "9:16": (992, 1792),
    "9:21": (864, 2048),
}
BUCKETS_2K: dict[str, tuple[int, int]] = {
    "2:3": (1664, 2496),
    "3:2": (2496, 1664),
    "3:4": (1760, 2368),
    "4:3": (2368, 1760),
    "4:5": (1824, 2272),
    "5:4": (2272, 1824),
    "1:1": (2048, 2048),
    "16:9": (2752, 1536),
    "9:16": (1536, 2752),
    "9:21": (1344, 3136),
}


@dataclass
class ImageGenerationResult:
    status: str
    output_path: Path
    model: str
    prompt: str
    metadata: dict[str, Any]


class ImageDriverError(RuntimeError):
    pass


def resolve_size(image_size: str = "2K", aspect_ratio: str = "16:9") -> str:
    buckets = BUCKETS_1K if image_size.upper() == "1K" else BUCKETS_2K
    if aspect_ratio in buckets:
        w, h = buckets[aspect_ratio]
        return f"{w}x{h}"
    try:
        ws, hs = aspect_ratio.split(":", 1)
        ratio = int(ws) / int(hs)
    except Exception as exc:
        raise ValueError(f"Invalid aspect ratio: {aspect_ratio}") from exc
    w, h = sorted(buckets.values(), key=lambda wh: abs(wh[0] / wh[1] - ratio))[0]
    return f"{w}x{h}"


class SenseNovaApiImageDriver:
    endpoint_path = "/images/generations"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 600.0,
    ):
        self.api_key = api_key or os.getenv("SN_IMAGE_GEN_API_KEY", "")
        self.base_url = (base_url or os.getenv("SN_IMAGE_GEN_BASE_URL", "https://token.sensenova.cn/v1")).rstrip("/")
        self.model = model or os.getenv("SN_IMAGE_GEN_MODEL", "sensenova-u1-fast")
        self.timeout = timeout

    async def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        if not self.api_key:
            raise ImageDriverError("SN_IMAGE_GEN_API_KEY is not set")
        size = resolve_size(image_size, aspect_ratio)
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "response_format": "url",
            "output_format": "png",
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        api_url = self.base_url + self.endpoint_path
        timeout = httpx.Timeout(self.timeout, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ImageDriverError(f"SenseNova image HTTP {response.status_code}: {response.text[:800]}") from exc
            raw = response.json()
            urls = [item.get("url") for item in raw.get("data", []) if isinstance(item, dict) and item.get("url")]
            if not urls:
                b64_items = [
                    item.get("b64_json") or item.get("base64")
                    for item in raw.get("data", [])
                    if isinstance(item, dict)
                ]
                b64_items = [x for x in b64_items if x]
                if not b64_items:
                    raise ImageDriverError(f"SenseNova image response did not include a URL: {raw}")
                await self._save_base64(b64_items[-1], output_path)
            else:
                await self._download(client, urls[-1], output_path)
        return ImageGenerationResult(
            status="ok",
            output_path=output_path,
            model=self.model,
            prompt=prompt,
            metadata={"size": size, "aspect_ratio": aspect_ratio, "image_size": image_size},
        )

    async def edit(
        self,
        *,
        prompt: str,
        images: list[Path],
        output_path: Path,
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        reference_note = "\n\nReference image paths supplied to Open_Notebook: " + ", ".join(
            p.name for p in images
        )
        return await self.generate(
            prompt=prompt + reference_note,
            output_path=output_path,
            image_size=image_size,
            aspect_ratio=aspect_ratio,
            profile=profile,
        )

    async def _download(self, client: httpx.AsyncClient, url: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    tmp.write(chunk)
            tmp.flush()
            os.fsync(tmp.fileno())
        self._validate(tmp_path)
        tmp_path.replace(output_path)

    async def _save_base64(self, raw: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = raw.split(",", 1)[1] if raw.startswith("data:") and "," in raw else raw
        output_path.write_bytes(base64.b64decode(text))
        self._validate(output_path)

    @staticmethod
    def _validate(path: Path) -> None:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()


class FakeImageDriver:
    def __init__(self, model: str = "fake-sensenova"):
        self.model = model

    async def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        size = resolve_size(image_size, aspect_ratio)
        w, h = [int(x) for x in size.split("x")]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (w, h), (245, 247, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, w, int(h * 0.18)), fill=(38, 70, 83))
        draw.rectangle((int(w * 0.04), int(h * 0.25), int(w * 0.96), int(h * 0.9)), outline=(42, 157, 143), width=max(4, w // 300))
        try:
            font_big = ImageFont.truetype("Arial Unicode.ttf", max(28, w // 32))
            font_small = ImageFont.truetype("Arial Unicode.ttf", max(18, w // 68))
        except Exception:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()
        draw.text((int(w * 0.06), int(h * 0.055)), "Open_Notebook Preview", fill=(255, 255, 255), font=font_big)
        snippet = prompt[:900]
        y = int(h * 0.28)
        for line in _wrap_text(snippet, 48):
            draw.text((int(w * 0.08), y), line, fill=(30, 38, 48), font=font_small)
            y += max(24, h // 42)
            if y > int(h * 0.86):
                break
        draw.text((int(w * 0.06), int(h * 0.93)), f"{aspect_ratio} | {image_size} | fake driver", fill=(85, 95, 110), font=font_small)
        img.save(output_path)
        return ImageGenerationResult(
            status="ok",
            output_path=output_path,
            model=self.model,
            prompt=prompt,
            metadata={"size": size, "aspect_ratio": aspect_ratio, "image_size": image_size, "fake": True},
        )

    async def edit(
        self,
        *,
        prompt: str,
        images: list[Path],
        output_path: Path,
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        return await self.generate(
            prompt=f"EDIT TASK using {len(images)} reference images:\n{prompt}",
            output_path=output_path,
            image_size=image_size,
            aspect_ratio=aspect_ratio,
            profile=profile,
        )


def get_image_driver(fake: bool = False):
    if fake or os.getenv("OPEN_NOTEBOOK_FAKE_IMAGE", "0").lower() in {"1", "true", "yes"}:
        return FakeImageDriver()
    backend = os.getenv("OPEN_NOTEBOOK_IMAGE_BACKEND", "").strip().lower()
    if backend in {"local_u1", "local", "full"}:
        return LocalU1ImageDriver()
    return SenseNovaApiImageDriver()


def _wrap_text(text: str, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text.replace("\r", "").replace("\n", " "):
        cur += ch
        if len(cur) >= width:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


class LocalU1ImageDriver:
    """Local SenseNova-U1 driver.

    This intentionally imports heavy ML dependencies lazily so the web app can
    start even when the local inference environment is not installed.
    """

    SUPPORTED_RESOLUTIONS: dict[str, tuple[int, int]] = {
        "1:1": (2048, 2048),
        "16:9": (2720, 1536),
        "9:16": (1536, 2720),
        "3:2": (2496, 1664),
        "2:3": (1664, 2496),
        "4:3": (2368, 1760),
        "3:4": (1760, 2368),
        "1:2": (1440, 2880),
        "2:1": (2880, 1440),
        "1:3": (1152, 3456),
        "3:1": (3456, 1152),
    }

    def __init__(
        self,
        *,
        model_path: str | None = None,
        source_root: str | None = None,
        device: str | None = None,
        dtype: str | None = None,
        num_steps: int | None = None,
    ):
        self.model_path = str(_resolve_repo_path(model_path or os.getenv("SENSENOVA_U1_MODEL_PATH", DEFAULT_U1_MODEL_PATH)))
        self.source_root = str(resolve_local_u1_source_root(source_root, auto_download=True))
        default_profile = sensenova_profile_for_task("image")
        self.device = device or default_profile.device
        self.dtype_name = dtype or default_profile.dtype
        self.num_steps = int(num_steps or default_profile.num_steps)
        self._engine: Any | None = None

    async def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        active_profile = profile or sensenova_profile_for_task(
            "image", image_size=image_size, aspect_ratio=aspect_ratio, seed=seed
        )
        return await _run_blocking(
            self._generate_sync,
            prompt=prompt,
            output_path=output_path,
            profile=active_profile,
        )

    async def edit(
        self,
        *,
        prompt: str,
        images: list[Path],
        output_path: Path,
        image_size: str = "2K",
        aspect_ratio: str = "16:9",
        profile: SenseNovaGenerationProfile | None = None,
    ) -> ImageGenerationResult:
        refs = "\n".join(f"Reference image: {p}" for p in images)
        return await self.generate(
            prompt=f"{prompt}\n{refs}",
            output_path=output_path,
            image_size=image_size,
            aspect_ratio=aspect_ratio,
            profile=profile,
        )

    def smoke_check(self) -> dict[str, Any]:
        self._ensure_imports()
        model_path = Path(self.model_path)
        return {
            "status": "ok",
            "model_path": str(model_path),
            "config": (model_path / "config.json").exists(),
            "index": (model_path / "model.safetensors.index.json").exists(),
            "safetensors": len(list(model_path.glob("*.safetensors"))),
            "device": self.device,
            "dtype": self.dtype_name,
        }

    def _ensure_imports(self) -> None:
        if self.source_root and self.source_root not in sys.path:
            sys.path.insert(0, self.source_root)
        try:
            import sensenova_u1  # noqa: F401
            import torch  # noqa: F401
            from transformers import AutoConfig, AutoModel, AutoTokenizer  # noqa: F401
        except Exception as exc:
            raise ImageDriverError(f"Local SenseNova-U1 imports failed: {exc}") from exc

    def _load_engine(self):
        if self._engine is not None:
            return self._engine
        self._ensure_imports()
        import numpy as np
        import torch
        from PIL import Image
        from transformers import AutoConfig, AutoModel, AutoTokenizer

        import sensenova_u1
        from sensenova_u1 import check_checkpoint_compatibility

        _patch_sensenova_u1_model_classes()
        if hasattr(sensenova_u1, "set_attn_backend"):
            sensenova_u1.set_attn_backend(os.getenv("SENSENOVA_U1_ATTN_BACKEND", "sdpa"))
        dtype = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }.get(self.dtype_name, torch.float16)

        config = AutoConfig.from_pretrained(self.model_path)
        _patch_sensenova_u1_config(config)
        check_checkpoint_compatibility(config)
        tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        model = AutoModel.from_pretrained(self.model_path, config=config, torch_dtype=dtype)
        model = model.to(self.device).eval()

        class Engine:
            def __init__(self, model, tokenizer):
                self.model = model
                self.tokenizer = tokenizer

            @staticmethod
            def to_pil(batch):
                if not torch.isfinite(batch).all():
                    finite = batch[torch.isfinite(batch)]
                    detail = "no finite values"
                    if finite.numel():
                        detail = f"finite min={finite.min().item():.4f}, max={finite.max().item():.4f}"
                    raise ImageDriverError(f"Local SenseNova-U1 produced non-finite image tensor ({detail})")
                mean = torch.tensor((0.5, 0.5, 0.5), device=batch.device, dtype=batch.dtype).view(1, 3, 1, 1)
                std = torch.tensor((0.5, 0.5, 0.5), device=batch.device, dtype=batch.dtype).view(1, 3, 1, 1)
                arr = ((batch.float() * std + mean).clamp(0, 1)).permute(0, 2, 3, 1).cpu().numpy()
                arr = (arr * 255.0).round().astype(np.uint8)
                if arr.max() == arr.min():
                    raise ImageDriverError(f"Local SenseNova-U1 produced a flat image value={int(arr.max())}")
                return [Image.fromarray(a) for a in arr]

            @torch.inference_mode()
            def generate(self, prompt, image_size, profile: SenseNovaGenerationProfile):
                out = self.model.t2i_generate(
                    self.tokenizer,
                    prompt,
                    image_size=image_size,
                    cfg_scale=profile.cfg_scale,
                    cfg_norm=profile.cfg_norm,
                    timestep_shift=profile.timestep_shift,
                    cfg_interval=profile.cfg_interval,
                    num_steps=profile.num_steps,
                    batch_size=profile.batch_size,
                    seed=profile.seed,
                    think_mode=profile.think_mode,
                )
                if profile.think_mode and isinstance(out, tuple):
                    out = out[0]
                return self.to_pil(out)

        self._engine = Engine(model, tokenizer)
        return self._engine

    def _generate_sync(
        self,
        *,
        prompt: str,
        output_path: Path,
        profile: SenseNovaGenerationProfile,
    ) -> ImageGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        size = self.SUPPORTED_RESOLUTIONS.get(profile.aspect_ratio, self.SUPPORTED_RESOLUTIONS["16:9"])
        engine = self._load_engine()
        images = engine.generate(prompt, size, profile)
        images[0].save(output_path)
        quality = inspect_image_quality(output_path)
        if not quality["ok"]:
            output_path.unlink(missing_ok=True)
            raise ImageDriverError(f"Local SenseNova-U1 output failed quality gate: {quality['reason']}")
        metadata = profile.to_metadata()
        metadata.update(quality)
        metadata.update({"size": f"{size[0]}x{size[1]}", "local_u1": True})
        return ImageGenerationResult(
            status="ok",
            output_path=output_path,
            model=f"local-u1:{self.model_path}",
            prompt=prompt,
            metadata=metadata,
        )


async def _run_blocking(func, **kwargs):
    import asyncio

    return await asyncio.to_thread(func, **kwargs)


def _resolve_repo_path(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def resolve_local_u1_source_root(
    source_root: str | Path | None = None,
    *,
    auto_download: bool = False,
) -> Path:
    return resolve_local_u1_source(source_root, auto_download=auto_download)["source_root"]


def resolve_local_u1_source(
    source_root: str | Path | None = None,
    *,
    auto_download: bool = False,
) -> dict[str, Any]:
    configured = str(source_root or os.getenv("SENSENOVA_U1_SOURCE_ROOT", "")).strip()
    if configured:
        resolved = _resolve_repo_path(configured)
        if _looks_like_u1_source_root(resolved) or configured.rstrip("/") != DEFAULT_U1_SOURCE_ROOT:
            return _source_info(resolved, configured=configured, downloaded=False)

    for candidate in LOCAL_U1_SOURCE_CANDIDATES:
        resolved = _resolve_repo_path(candidate)
        if _looks_like_u1_source_root(resolved):
            return _source_info(resolved, configured=configured or DEFAULT_U1_SOURCE_ROOT, downloaded=False)

    target_root = _resolve_repo_path(DEFAULT_U1_SOURCE_ROOT)
    if auto_download:
        downloaded = ensure_local_u1_source_repo(target_root.parent)
        if _looks_like_u1_source_root(target_root):
            return _source_info(target_root, configured=configured or DEFAULT_U1_SOURCE_ROOT, downloaded=downloaded)

    return _source_info(target_root, configured=configured or DEFAULT_U1_SOURCE_ROOT, downloaded=False)


def ensure_local_u1_source_repo(target_dir: Path | None = None) -> bool:
    target = (target_dir or _resolve_repo_path(DEFAULT_U1_SOURCE_ROOT).parent).resolve()
    source_root = target / "src"
    if _looks_like_u1_source_root(source_root):
        return False
    if target.exists() and any(target.iterdir()):
        raise ImageDriverError(
            f"Local SenseNova-U1 source directory exists but is incomplete: {target}. "
            "Remove it or set SENSENOVA_U1_SOURCE_ROOT to a valid checkout."
        )
    git = shutil.which("git")
    if not git:
        raise ImageDriverError("git is required to download SenseNova-U1 source automatically")
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [git, "clone", "--depth", "1", DEFAULT_U1_SOURCE_REPO, str(target)]
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True, text=True, capture_output=True, timeout=1800)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        raise ImageDriverError(f"Failed to clone SenseNova-U1 source: {stderr[-1200:]}") from exc
    if not _looks_like_u1_source_root(source_root):
        raise ImageDriverError(f"Downloaded SenseNova-U1 source is missing package files: {source_root}")
    return True


def _source_info(source_root: Path, *, configured: str, downloaded: bool) -> dict[str, Any]:
    return {
        "source_root": source_root,
        "configured": configured,
        "exists": _looks_like_u1_source_root(source_root),
        "downloaded": downloaded,
        "repo": DEFAULT_U1_SOURCE_REPO,
    }


def _looks_like_u1_source_root(path: Path) -> bool:
    return (path / "sensenova_u1" / "__init__.py").exists()


def inspect_image_quality(path: Path) -> dict[str, Any]:
    import numpy as np

    with Image.open(path) as image:
        arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    mean = float(arr.mean())
    std = float(arr.std())
    min_value = int(arr.min())
    max_value = int(arr.max())
    if w < 512 or h < 512:
        return _quality(False, "image too small", w, h, mean, std, min_value, max_value)
    if std < 8.0:
        return _quality(False, "near-flat image", w, h, mean, std, min_value, max_value)

    gray = arr.mean(axis=2)
    edge_h = np.abs(np.diff(gray, axis=1))
    edge_v = np.abs(np.diff(gray, axis=0))
    high_edge_ratio = float(((edge_h > 80).mean() + (edge_v > 80).mean()) / 2.0)
    if high_edge_ratio > 0.38:
        return _quality(False, "excessive high-frequency noise", w, h, mean, std, min_value, max_value)

    # Degenerate MPS outputs often look like repeated patch mosaics. Compare
    # adjacent 16x16 patch means and reject very blocky, high-contrast grids.
    patch = 16
    hh, ww = h // patch, w // patch
    if hh > 4 and ww > 4:
        cropped = gray[: hh * patch, : ww * patch]
        patch_means = cropped.reshape(hh, patch, ww, patch).mean(axis=(1, 3))
        patch_jump = float(
            (np.abs(np.diff(patch_means, axis=0)).mean() + np.abs(np.diff(patch_means, axis=1)).mean()) / 2.0
        )
        if patch_jump > 34.0 and high_edge_ratio > 0.22:
            return _quality(False, "blocky patch-noise mosaic", w, h, mean, std, min_value, max_value)

    return _quality(True, "ok", w, h, mean, std, min_value, max_value)


def local_u1_environment_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "recommended": {
            "python": ">=3.11,<3.12",
            "torch": "2.8.0",
            "transformers": "4.57.1",
            "dtype": "bfloat16",
            "num_steps": 50,
            "cfg_scale": 4.0,
            "cfg_norm": "none",
            "timestep_shift": 3.0,
            "device": "cuda recommended; mps is experimental",
        },
        "current": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "device": os.getenv("SENSENOVA_U1_DEVICE", "mps"),
            "dtype": os.getenv("SENSENOVA_U1_DTYPE", "bfloat16"),
            "num_steps": int(os.getenv("SENSENOVA_U1_NUM_STEPS", "50")),
            "cfg_scale": float(os.getenv("SENSENOVA_U1_CFG_SCALE", "4.0")),
            "cfg_norm": os.getenv("SENSENOVA_U1_CFG_NORM", "none"),
            "timestep_shift": float(os.getenv("SENSENOVA_U1_TIMESTEP_SHIFT", "3.0")),
        },
        "warnings": [],
    }
    try:
        import torch

        report["current"]["torch"] = torch.__version__
        report["current"]["mps_available"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        report["current"]["cuda_available"] = bool(torch.cuda.is_available())
    except Exception as exc:
        report["warnings"].append(f"torch import failed: {exc}")
    try:
        import transformers

        report["current"]["transformers"] = transformers.__version__
    except Exception as exc:
        report["warnings"].append(f"transformers import failed: {exc}")

    if sys.version_info < (3, 11) or sys.version_info >= (3, 12):
        report["warnings"].append("SenseNova-U1 upstream recommends Python >=3.11,<3.12 for local inference")
    transformers_version = str(report["current"].get("transformers", ""))
    if transformers_version and not transformers_version.startswith("4.57."):
        report["warnings"].append(
            f"Current transformers={transformers_version}; upstream reference is transformers==4.57.1"
        )
    torch_version = str(report["current"].get("torch", ""))
    if torch_version and not torch_version.startswith("2.8."):
        report["warnings"].append(f"Current torch={torch_version}; upstream reference is torch==2.8.0")
    if report["current"]["device"] == "mps":
        report["warnings"].append("MPS local U1 inference is experimental; CUDA is the upstream validated path")
    return report


def _quality(
    ok: bool,
    reason: str,
    width: int,
    height: int,
    mean: float,
    std: float,
    min_value: int,
    max_value: int,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "quality": {
            "width": width,
            "height": height,
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": min_value,
            "max": max_value,
        },
    }


def _patch_sensenova_u1_config(config: Any) -> None:
    """Bridge SenseNova-U1's Qwen3 code across transformers config changes.

    Newer transformers versions store Qwen3 RoPE fields under
    ``rope_parameters``/``rope_scaling`` and no longer expose ``rope_theta`` as
    a direct attribute. SenseNova-U1's local modeling code still reads
    ``config.rope_theta`` during image generation, so restore the attribute at
    runtime without modifying the external upstream checkout.
    """
    llm_config = getattr(config, "llm_config", None)
    if llm_config is None or hasattr(llm_config, "rope_theta"):
        return
    rope_theta = None
    for attr in ("rope_parameters", "rope_scaling"):
        value = getattr(llm_config, attr, None)
        if isinstance(value, dict) and value.get("rope_theta") is not None:
            rope_theta = value["rope_theta"]
            break
    if rope_theta is None:
        raw = config.to_dict() if hasattr(config, "to_dict") else {}
        raw_llm = raw.get("llm_config", {}) if isinstance(raw, dict) else {}
        if isinstance(raw_llm, dict):
            rope_theta = raw_llm.get("rope_theta")
    if rope_theta is not None:
        setattr(llm_config, "rope_theta", rope_theta)


def _patch_sensenova_u1_model_classes() -> None:
    """Patch small transformers 5.x API expectations onto SenseNova-U1 classes."""
    try:
        from sensenova_u1.models.neo_unify.modeling_neo_chat import NEOChatModel
        from sensenova_u1.models.neo_unify import modeling_qwen3
    except Exception:
        return
    if not hasattr(NEOChatModel, "all_tied_weights_keys"):
        NEOChatModel.all_tied_weights_keys = {}
    rotary_cls = getattr(modeling_qwen3, "Qwen3RotaryEmbedding", None)
    rope_fn = getattr(modeling_qwen3, "_compute_default_rope_parameters", None)
    if rotary_cls is not None and rope_fn is not None and not hasattr(rotary_cls, "compute_default_rope_parameters"):
        rotary_cls.compute_default_rope_parameters = staticmethod(rope_fn)
