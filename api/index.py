"""Vercel serverless entry-point — exposes the FastAPI app as a handler.

Vercel's Python runtime looks for a variable named ``app`` (ASGI) or
``handler`` (WSGI) in api/*.py files.  We import the existing FastAPI
instance so every route defined in backend.server.app is available at
``/api/*`` in production.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``backend.*`` imports resolve.
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from backend.server.app import app  # noqa: E402, F401 — re-exported for Vercel
