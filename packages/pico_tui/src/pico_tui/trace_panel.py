"""Tracing tab: live projection formatting over session nodes."""

from __future__ import annotations

from pico_core.session import (
    KbHitPayload,
    OcrPagePayload,
    RouterDecisionPayload,
    Session,
    ToolRequestPayload,
    ToolResultPayload,
)


def format_trace(session: Session) -> str:
    """Render router/kb/ocr/tool events on the active branch as text lines."""
    lines: list[str] = []
    for node in session.active_branch():
        payload = node.payload
        if isinstance(payload, RouterDecisionPayload):
            lines.append(f"router {payload.capability} -> {payload.model_id} ({payload.reason})")
        elif isinstance(payload, KbHitPayload):
            lines.append(f"kb {payload.doc} {payload.chunk} {payload.page}")
        elif isinstance(payload, OcrPagePayload):
            lines.append(f"ocr p{payload.page} {payload.png}")
        elif isinstance(payload, ToolRequestPayload):
            lines.append(f"call {payload.tool_call.name}")
        elif isinstance(payload, ToolResultPayload):
            status = "error" if payload.is_error else "ok"
            lines.append(f"result {payload.name}: {status}")
    return "\n".join(lines)
