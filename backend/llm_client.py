"""Direct OpenAI Chat Completions client (replaces OpenRouter)."""
from __future__ import annotations

import os
from typing import Any, Optional

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"


def openai_model() -> str:
    raw = (
        os.environ.get("OPENAI_MODEL")
        or os.environ.get("SEED_AI_MODEL")
        or _DEFAULT_MODEL
    ).strip()
    # Old OpenRouter-style ids: openai/gpt-4o-mini → gpt-4o-mini
    if raw.startswith("openai/"):
        raw = raw.split("/", 1)[1]
    return raw or _DEFAULT_MODEL


# Import-time alias used by call sites; env is loaded before these modules in server.py
OPENAI_MODEL = openai_model()


def openai_api_key() -> Optional[str]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return key or None


def openai_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {openai_api_key()}",
        "Content-Type": "application/json",
    }


def openai_message_content(data: dict[str, Any]) -> str:
    """Pull assistant text from an OpenAI chat.completions JSON body."""
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("OpenAI response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenAI response missing message content")
    return content
