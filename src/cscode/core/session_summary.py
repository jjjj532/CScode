from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cscode.core.session import SessionV2


_PREVIEW_MAX_CHARS = 200


class SessionSummary:
    """Generates a statistical summary of a session's activity.

    Operates on an already-loaded SessionV2 (state already projected).
    For LLM-generated abstract summaries, call .generate() and pass
    the result to an LLM for further enrichment.
    """

    def __init__(self, session: SessionV2) -> None:
        self._session = session

    def generate(self) -> dict:
        """Produce a summary dict from the session state."""
        state = self._session.state
        messages = state.messages

        user_count = sum(1 for m in messages if m.role == "user")
        assistant_count = sum(1 for m in messages if m.role == "assistant")

        # Character and word counts across all message text parts
        char_count = 0
        word_count = 0
        for msg in messages:
            for part in msg.parts:
                text = getattr(part, "text", None)
                if isinstance(text, str):
                    char_count += len(text)
                    word_count += len(text.split())

        # Tool call count from parts
        tool_call_count = sum(
            1 for msg in messages for part in msg.parts
            if getattr(part, "type", None) == "tool-call"
        )

        # First and last message previews
        first_preview = _truncate_message(messages[0]) if messages else ""
        last_preview = _truncate_message(messages[-1]) if messages else ""

        return {
            "session_id": str(state.session_id),
            "title": state.title,
            "message_count": len(messages),
            "user_message_count": user_count,
            "assistant_message_count": assistant_count,
            "tool_call_count": tool_call_count,
            "first_message_preview": first_preview,
            "last_message_preview": last_preview,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "duration_seconds": max(0.0, state.updated_at - state.created_at),
            "word_count": word_count,
            "character_count": char_count,
        }


def _truncate_message(message) -> str:
    parts_text = []
    for part in message.parts:
        text = getattr(part, "text", None)
        if isinstance(text, str):
            parts_text.append(text)
    combined = " ".join(parts_text).strip()
    if len(combined) > _PREVIEW_MAX_CHARS:
        # Leave room for the "..." suffix
        limit = max(0, _PREVIEW_MAX_CHARS - 3)
        return combined[:limit].rstrip() + "..."
    return combined
