from __future__ import annotations

import json
from typing import Any

from cscode.storage.db import Database


class TaskTracker:
    """Receives tool events via handle_event callback, writes to task_verifications projection table."""

    def __init__(self, db: Database):
        self.db = db

    async def handle_event(self, session_id: str, event: dict[str, Any]) -> None:
        evt_type = event.get("type", "")
        if evt_type not in ("tool.success", "tool.failed"):
            return

        data = event.get("data", {})
        args = data.get("args", {})
        metadata = data.get("metadata", {})

        task_id = args.get("task_id") or metadata.get("task_id", "")
        if not task_id:
            return

        tool_name = data.get("name", "unknown")

        if evt_type == "tool.success":
            evidence_raw = metadata.get("evidence", "{}")
            evidence = evidence_raw
            if isinstance(evidence_raw, str):
                try:
                    evidence = json.loads(evidence_raw)
                except json.JSONDecodeError:
                    evidence = {}
            verified = self._verify_evidence(tool_name, evidence)
            status = "EXECUTED" if verified else "UNVERIFIED"
            result_summary = data.get("result", "")[:500]
        else:
            evidence = {}
            verified = False
            status = "FAILED"
            result_summary = data.get("error", "")[:500]

        await self.db.execute(
            """INSERT OR REPLACE INTO task_verifications
               (session_id, task_id, tool_name, status, verified, evidence, result_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, task_id, tool_name, status, int(verified),
             json.dumps(evidence), result_summary),
        )

    def _verify_evidence(self, tool: str, evidence: dict) -> bool:
        if not isinstance(evidence, dict):
            return False
        if tool == "browser":
            return bool(evidence.get("screenshot_path")) or evidence.get("html", False)
        if tool == "bash":
            return evidence.get("content_length", 0) > 0
        return bool(evidence)

    async def get_execution_report(self, session_id: str) -> dict:
        rows = await self.db.fetchall(
            "SELECT task_id, status, verified, evidence, result_summary, created_at "
            "FROM task_verifications WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        executed = [r for r in rows if r["status"] == "EXECUTED"]
        failed = [r for r in rows if r["status"] == "FAILED"]
        unverified = [r for r in rows if r["status"] == "UNVERIFIED"]

        return {
            "summary": {
                "executed": len(executed),
                "failed": len(failed),
                "unverified": len(unverified),
                "skipped": 0,
            },
            "details": [
                {
                    "task_id": r["task_id"],
                    "status": r["status"],
                    "evidence": json.loads(r["evidence"]) if r["evidence"] else {},
                    "result_summary": r["result_summary"],
                    "timestamp": r["created_at"],
                }
                for r in rows
            ],
        }
