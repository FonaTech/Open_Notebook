#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DEFAULT_MODEL_DIR = ROOT / "models" / "Full"


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Open_Notebook Web UI.")
    parser.add_argument("--host", default=os.getenv("OPEN_NOTEBOOK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OPEN_NOTEBOOK_PORT", "8017")))
    parser.add_argument("--data-dir", default=os.getenv("OPEN_NOTEBOOK_DATA_DIR", "data"))
    parser.add_argument("--fake-image", action="store_true", help="Use a local fake image driver for smoke tests.")
    parser.add_argument(
        "--local-u1",
        action="store_true",
        help="Use the local SenseNova-U1 driver. The model path defaults to models/Full.",
    )
    parser.add_argument(
        "--api-image",
        action="store_true",
        help="Use the SenseNova image API driver even if local model files exist.",
    )
    parser.add_argument(
        "--build-frontend",
        action="store_true",
        help="Rebuild frontend/dist if Node.js and npm are installed. Runtime does not require Node.js.",
    )
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()

    if args.build_frontend:
        build_frontend()
    elif not FRONTEND_DIST.exists():
        print(
            "[warn] frontend/dist is missing. The API will still run, but the browser UI needs "
            "prebuilt assets. Run with --build-frontend on a machine with Node.js, or use the "
            "committed frontend/dist files from the release archive.",
            file=sys.stderr,
        )

    os.environ.setdefault("OPEN_NOTEBOOK_HOST", args.host)
    os.environ.setdefault("OPEN_NOTEBOOK_PORT", str(args.port))
    os.environ.setdefault("OPEN_NOTEBOOK_DATA_DIR", args.data_dir)
    if args.fake_image:
        os.environ["OPEN_NOTEBOOK_FAKE_IMAGE"] = "1"
    if args.api_image:
        os.environ["OPEN_NOTEBOOK_IMAGE_BACKEND"] = "api"
    elif args.local_u1 or _local_model_ready():
        os.environ["OPEN_NOTEBOOK_IMAGE_BACKEND"] = "local_u1"
        os.environ.setdefault("SENSENOVA_U1_MODEL_PATH", "models/Full")
        os.environ.setdefault("SENSENOVA_U1_SOURCE_ROOT", "../SenseNova-U1-main/src")

    sys.path.insert(0, str(BACKEND))
    url = f"http://{args.host}:{args.port}"
    print(f"Open_Notebook Web UI: {url}")
    print("Runtime does not require Node.js when frontend/dist is present.")
    print(f"Image backend: {_image_backend_label()}")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    import uvicorn

    uvicorn.run("open_notebook.main:app", host=args.host, port=args.port, reload=False)


def _local_model_ready() -> bool:
    return (
        (DEFAULT_MODEL_DIR / "config.json").exists()
        and (DEFAULT_MODEL_DIR / "model.safetensors.index.json").exists()
        and len(list(DEFAULT_MODEL_DIR.glob("*.safetensors"))) >= 8
    )


def _image_backend_label() -> str:
    if os.getenv("OPEN_NOTEBOOK_FAKE_IMAGE", "0").lower() in {"1", "true", "yes", "on"}:
        return "fake-image"
    backend = os.getenv("OPEN_NOTEBOOK_IMAGE_BACKEND", "").strip() or "api"
    if backend == "local_u1":
        return "local_u1 (models/Full)"
    return backend


def build_frontend() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm was not found. Runtime does not require Node.js, but rebuilding does.")
    frontend = ROOT / "frontend"
    subprocess.run([npm, "install"], cwd=frontend, check=True)
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)


if __name__ == "__main__":
    main()
