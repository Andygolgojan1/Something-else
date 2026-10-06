"""Remove the configured credential from server-controlled payloads."""

from __future__ import annotations

import hashlib
from typing import Any


def scrub_configured_token(value: Any, auth_token: str) -> Any:
    """Copy JSON payloads with exact configured-token occurrences replaced."""
    if not auth_token:
        return value
    if isinstance(value, str):
        return value.replace(auth_token, "[redacted]")
    if isinstance(value, dict):
        return {
            scrub_configured_token(key, auth_token): scrub_configured_token(item, auth_token)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_configured_token(item, auth_token) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_configured_token(item, auth_token) for item in value)
    return value


def public_tool_name(name: str, auth_token: str) -> str:
    """Return a stable callable alias when an advertised name contains the credential."""
    if not auth_token or auth_token not in name:
        return name
    alias = "mcp_tool_" + hashlib.sha256(name.encode()).hexdigest()
    replacement = "-" if auth_token[0] != "-" else "_"
    while auth_token in alias:
        alias = alias.replace(auth_token, replacement)
    return alias
