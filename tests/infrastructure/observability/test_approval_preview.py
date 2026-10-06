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
    assert preview.truncated
    full = json.loads(preview.full_text)
    assert full["arguments"]["padding"] == arguments["arguments"]["padding"]
    assert "sample-token" not in preview.full_text
    assert arguments["arguments"]["padding"] == "x" * 10000


def test_structure_that_cannot_fit_is_explicitly_unreviewable() -> None:
    preview = format_approval_preview({f"field_{i}": i for i in range(100)}, max_chars=400)
    assert not preview.fields_visible
    assert len(preview.text) <= 400
    assert "fields" in preview.text


def test_review_limit_and_non_json_values_never_authorize_partial_evidence() -> None:
    for value in ({"query": "x" * 64000}, {"code": object()}):
        preview = format_approval_preview(value, max_chars=400)
        assert not preview.fields_visible
        assert not preview.full_text
