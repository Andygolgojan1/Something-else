"""Security and field visibility contracts for approval previews."""

from __future__ import annotations

import json

from infrastructure.observability.trace.approval_preview import format_approval_preview


def test_large_values_cannot_hide_later_nested_fields_or_list_targets() -> None:
    arguments = {
        "tool_name": "restart_service",
        "arguments": {
            "padding": "x" * 10000,
            "targets": [{"service": "api"}, {"service": "prod"}],
            "message": "Bearer sample-token",
        },
    }
    preview = format_approval_preview(arguments, max_chars=400)
    assert preview.fields_visible and len(preview.text) <= 400
    shown = json.loads(preview.text)
    assert shown["arguments"]["targets"] == arguments["arguments"]["targets"]
    assert set(shown["arguments"]) == set(arguments["arguments"])
    assert "sample-token" not in preview.text
    assert "[truncated]" in shown["arguments"]["padding"]
    assert arguments["arguments"]["padding"] == "x" * 10000


def test_structure_that_cannot_fit_is_explicitly_unreviewable() -> None:
    preview = format_approval_preview({f"field_{i}": i for i in range(100)}, max_chars=400)
    assert not preview.fields_visible
    assert len(preview.text) <= 400
    assert "fields" in preview.text
