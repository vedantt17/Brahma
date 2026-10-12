"""Vercel's FastAPI entrypoint; the local uvicorn target remains app.main:app."""

from app.main import app

__all__ = ["app"]
