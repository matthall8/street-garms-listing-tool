"""FastAPI app factory for the label capture UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    from dotenv import load_dotenv

    load_dotenv()

    app = FastAPI()

    from app.routes import router

    app.include_router(router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"))
    return app
