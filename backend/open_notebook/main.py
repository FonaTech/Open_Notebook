from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from open_notebook.api.routes import router
from open_notebook.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Open_Notebook", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    frontend_dist = __import__("pathlib").Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run("open_notebook.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
