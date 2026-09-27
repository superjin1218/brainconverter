"""Vercel's FastAPI entry point; local development uses the same application."""

from backend.app.main import app

__all__ = ["app"]
