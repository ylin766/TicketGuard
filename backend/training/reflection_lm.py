"""Reflection LM for GEPA — a Gemini-on-Vertex callable.

GEPA's ``reflection_lm`` is the model that reads the reflective dataset and
proposes improved prompts. It accepts a ``Callable[[str], str]`` (prompt in,
text out). We back it with ``google-genai`` so reflection runs on Vertex AI
(honoring ``GOOGLE_GENAI_USE_VERTEXAI`` / ADC) — the same path the rest of the
system bills against — rather than GEPA's default litellm/OpenAI route.

A stronger model than the task model is usually worth it for reflection (the
paper uses a large reflector), so the model is configurable; it defaults to the
project's ``GEMINI_MODEL``.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)


def make_reflection_lm(model: str | None = None) -> Callable[[str], str]:
    """Return a ``prompt -> text`` callable backed by Gemini on Vertex.

    Lazily constructs the google-genai client on first call so importing this
    module never requires credentials. Raises only if invoked without a working
    client (GEPA needs a real reflector to make progress — there's no safe
    no-op).
    """
    model_name = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    _client = {}

    def _get_client():
        if "c" not in _client:
            from ..core.config import build_genai_client

            _client["c"] = build_genai_client()
        return _client["c"]

    def reflect(prompt: str) -> str:
        client = _get_client()
        resp = client.models.generate_content(model=model_name, contents=prompt)
        return getattr(resp, "text", "") or ""

    return reflect
