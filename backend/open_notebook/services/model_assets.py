from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from open_notebook.core.image_driver import (
    DEFAULT_U1_MODEL_PATH,
    DEFAULT_U1_SOURCE_REPO,
    DEFAULT_U1_SOURCE_ROOT,
    ImageDriverError,
    REPO_ROOT,
    local_u1_environment_report,
    resolve_local_u1_source,
)

SENSENOVA_HF_REPO = "sensenova/SenseNova-U1-8B-MoT"
DEFAULT_MODEL_DIR = REPO_ROOT / "models" / "Full"


def model_status() -> dict[str, Any]:
    model_dir = DEFAULT_MODEL_DIR
    source_error = ""
    try:
        source_info = resolve_local_u1_source(auto_download=True)
    except ImageDriverError as exc:
        source_error = str(exc)
        source_info = resolve_local_u1_source(auto_download=False)
    source_dir = source_info["source_root"]
    configured_source = str(source_info["configured"])
    try:
        source_dir_display = str(source_dir.relative_to(REPO_ROOT))
    except ValueError:
        source_dir_display = os.path.relpath(source_dir, REPO_ROOT)
    return {
        "repo": SENSENOVA_HF_REPO,
        "huggingface_url": f"https://huggingface.co/{SENSENOVA_HF_REPO}",
        "model_dir": str(model_dir.relative_to(REPO_ROOT)),
        "source_dir": source_dir_display,
        "model_dir_abs": str(model_dir),
        "source_dir_abs": str(source_dir),
        "source_repo": DEFAULT_U1_SOURCE_REPO,
        "source_downloaded": bool(source_info["downloaded"]),
        "source_error": source_error,
        "exists": model_dir.exists(),
        "config": (model_dir / "config.json").exists(),
        "index": (model_dir / "model.safetensors.index.json").exists(),
        "safetensors": len(list(model_dir.glob("*.safetensors"))) if model_dir.exists() else 0,
        "source_exists": bool(source_info["exists"]),
        "local_u1_environment": local_u1_environment_report(),
        "env": {
            "OPEN_NOTEBOOK_IMAGE_BACKEND": os.getenv("OPEN_NOTEBOOK_IMAGE_BACKEND", ""),
            "SENSENOVA_U1_MODEL_PATH": os.getenv("SENSENOVA_U1_MODEL_PATH", DEFAULT_U1_MODEL_PATH),
            "SENSENOVA_U1_SOURCE_ROOT": configured_source,
            "SENSENOVA_U1_DTYPE": os.getenv("SENSENOVA_U1_DTYPE", "bfloat16"),
            "SENSENOVA_U1_NUM_STEPS": os.getenv("SENSENOVA_U1_NUM_STEPS", "50"),
            "SENSENOVA_U1_CFG_SCALE": os.getenv("SENSENOVA_U1_CFG_SCALE", "4.0"),
            "SENSENOVA_U1_CFG_NORM": os.getenv("SENSENOVA_U1_CFG_NORM", "none"),
            "SENSENOVA_U1_TIMESTEP_SHIFT": os.getenv("SENSENOVA_U1_TIMESTEP_SHIFT", "3.0"),
        },
    }


def download_model() -> dict[str, Any]:
    """Start a foreground HuggingFace download into models/Full.

    This endpoint is intentionally explicit. It does not run at startup and it
    writes only to gitignored relative directories.
    """
    DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    hf = shutil.which("huggingface-cli")
    if hf:
        cmd = [
            hf,
            "download",
            SENSENOVA_HF_REPO,
            "--local-dir",
            str(DEFAULT_MODEL_DIR),
            "--local-dir-use-symlinks",
            "False",
        ]
    else:
        py = shutil.which("python") or "python"
        cmd = [
            py,
            "-m",
            "huggingface_hub.commands.huggingface_cli",
            "download",
            SENSENOVA_HF_REPO,
            "--local-dir",
            str(DEFAULT_MODEL_DIR),
            "--local-dir-use-symlinks",
            "False",
        ]
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, timeout=24 * 3600)
    except Exception as exc:
        return {"status": "failed", "command": cmd, "error": str(exc), "model_dir": "models/Full"}
    status = "ok" if proc.returncode == 0 else "failed"
    return {
        "status": status,
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "model_dir": "models/Full",
        "next_env": {
            "OPEN_NOTEBOOK_IMAGE_BACKEND": "local_u1",
            "SENSENOVA_U1_MODEL_PATH": DEFAULT_U1_MODEL_PATH,
            "SENSENOVA_U1_SOURCE_ROOT": DEFAULT_U1_SOURCE_ROOT,
        },
    }
