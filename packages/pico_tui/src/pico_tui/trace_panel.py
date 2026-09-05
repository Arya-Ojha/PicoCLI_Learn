"""Tracing tab: live projection formatting over session nodes."""

from __future__ import annotations

from pico_core.session import (
    Session,
    ToolRequestPayload,
    ToolResultPayload,
)


def format_trace(session: Session) -> str:
    """Render router/kb/ocr/tool events on the active branch as text lines."""
    lines: list[str] = []
    for node in session.active_branch():
        payload = node.payload
        if isinstance(payload, ToolRequestPayload):
            if payload.subtype == "router_decision":
                d = payload.detail
                lines.append(
                    f"router {d.get('capability', '')} -> {d.get('model_id', '')} ({d.get('reason', '')})"
                )
            elif payload.subtype == "kb_hit":
                d = payload.detail
                lines.append(f"kb {d.get('doc', '')} {d.get('chunk', '')} {d.get('page', '')}")
            elif payload.subtype == "ocr_page":
                d = payload.detail
                lines.append(f"ocr p{d.get('page', '')} {d.get('png', '')}")
            else:
                lines.append(f"call {payload.tool_call.name}")
        elif isinstance(payload, ToolResultPayload):
            status = "error" if payload.is_error else "ok"
            lines.append(f"result {payload.name}: {status}")
    return "\n".join(lines)
