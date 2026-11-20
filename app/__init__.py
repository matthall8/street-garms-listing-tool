"""FastAPI app factory for the label capture UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    from dotenv import load_dotenv

    load_dotenv()

    app = FastAPI()

    from app.errors import LogUnhandledErrors
    from app.routes import invalid_request, router

    app.include_router(router)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_middleware(LogUnhandledErrors)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"))
    return app
