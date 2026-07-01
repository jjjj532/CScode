from __future__ import annotations

from typing import Any

from cscode.core.messages import Message, MessageRole
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class Projector:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _get_latest_epoch(self, session_id: str) -> dict[str, Any] | None:
        logger.debug("Projector._get_latest_epoch: session_id=%s", session_id)
        cursor = await self._db.conn.execute(
            "SELECT epoch, baseline_seq, snapshot FROM context_epochs WHERE session_id = ? ORDER BY epoch DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "epoch": row["epoch"],
            "baseline_seq": row["baseline_seq"],
            "snapshot": row["snapshot"],
        }

    async def build_context(
        self,
        session_id: str,
        event_store: EventStore,
        system_prompt: str | None = None,
    ) -> list[Message]:
        logger.info("Projector.build_context: session_id=%s has_system_prompt=%s", session_id, system_prompt is not None)
        epoch = await self._get_latest_epoch(session_id)

        msgs: list[Message] = []
        after_seq = 0

        if epoch:
            msgs.append(Message(role=MessageRole.SYSTEM, content=epoch["snapshot"]))
            after_seq = epoch["baseline_seq"]
        elif system_prompt:
            msgs.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        events = await event_store.read(session_id, after_seq=after_seq)
        logger.debug("Projector.build_context: events_count=%d", len(events))
        for evt in events:
            if evt.type == "compaction":
                continue
            match evt.type:
                case "prompt.admitted":
                    content = evt.data.get("content") or evt.data.get("prompt", "")
                    if content:
                        msgs.append(
                            Message(role=MessageRole.USER, content=content)
                        )
                case "text.ended":
                    content = evt.data.get("content", "")
                    if not content:
                        continue
                    msgs.append(
                        Message(role=MessageRole.ASSISTANT, content=content)
                    )
                case "tool.called":
                    pass
                case "tool.success":
                    msgs.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=evt.data.get("result", ""),
                            name=evt.data.get("name"),
                        )
                    )
                case "tool.failed":
                    msgs.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=f"Error: {evt.data.get('error', '')}",
                            name=evt.data.get("name"),
                        )
                    )
        return msgs
