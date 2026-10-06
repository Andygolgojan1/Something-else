"""Credential-safe, bounded copies of model-visible gateway tool results."""

from __future__ import annotations

import json
from typing import Any

from infrastructure.observability.trace.redaction import redact_sensitive
from integrations.mcp_gateway.redaction import scrub_configured_token

_MAX_RESULT_CHARS = 60_000
_TEXT_PREVIEW_CHARS = 4_000


def _result_preview(safe: dict[str, Any]) -> str:
    """Keep text or a bounded, explicitly incomplete preview of structured data."""
    text = safe.get("text")
    if isinstance(text, str) and text.strip():
        return text[:_TEXT_PREVIEW_CHARS]
    structured = safe.get("structured_content") or safe.get("content")
    if not structured:
        return ""
    parts: list[str] = []
    remaining = _TEXT_PREVIEW_CHARS
    try:
        for chunk in json.JSONEncoder(ensure_ascii=True).iterencode(structured):
            part = chunk[:remaining]
            parts.append(part)
            remaining -= len(part)
            if not remaining:
                break
    except (TypeError, ValueError, RecursionError):
        return ""
    return "Structured data preview (incomplete):\n" + "".join(parts)


def safe_tool_result(payload: dict[str, object], *, auth_token: str) -> dict[str, Any]:
    """Redact every output path, preserving small results and marking omitted data."""
    safe: dict[str, Any] = redact_sensitive(scrub_configured_token(payload, auth_token))
    try:
        size = len(json.dumps(safe, ensure_ascii=True))
    except (TypeError, ValueError, RecursionError):
        size = None
    if size is not None and size <= _MAX_RESULT_CHARS:
        return safe
    summary = _result_preview(safe)
    result = {
        "source": "mcp_gateway",
        "available": safe.get("available", True),
        "tool": str(safe.get("tool", ""))[:256],
        "arguments": {},
        "text": summary + "\n[truncated: complete remote result omitted]",
        "structured_content": None,
        "content": [],
        "truncated": True,
        "original_serialized_chars": size,
        "notes": "Do not repeat a completed mutation to retrieve its full result. Narrow read queries instead.",
    }
    for key in ("error", "error_kind"):
        value = safe.get(key)
        if isinstance(value, str):
            result[key] = value[:3_000]
    return result
