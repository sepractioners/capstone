"""Durable conversation, run, and replayable event persistence."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import WebDatabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRunStore:
    """Persist safe chat state before it is emitted over SSE."""

    def __init__(self, database: WebDatabase) -> None:
        self._database = database

    def create_conversation(self, organization_id: str, user_id: str, title: str = "") -> dict[str, Any]:
        conversation_id = f"conv_{uuid.uuid4().hex}"
        created_at = _now()
        connection = self._database.connect()
        try:
            connection.execute(
                "INSERT INTO agent_conversations (id, organization_id, created_by, title, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, organization_id, user_id, title, created_at),
            )
            connection.commit()
        finally:
            connection.close()
        return {"id": conversation_id, "organization_id": organization_id, "title": title, "created_at": created_at}

    def create_message_and_run(
        self, conversation_id: str, organization_id: str, mode: str, text: str, attachment: dict[str, Any] | None
    ) -> dict[str, str]:
        message_id = f"msg_{uuid.uuid4().hex}"
        run_id = f"run_{uuid.uuid4().hex}"
        created_at = _now()
        connection = self._database.connect()
        try:
            connection.execute(
                "INSERT INTO agent_messages VALUES (?, ?, 'user', ?, ?, ?, ?)",
                (message_id, conversation_id, mode, text, json.dumps(attachment) if attachment else None, created_at),
            )
            connection.execute(
                "INSERT INTO agent_runs VALUES (?, ?, ?, ?, ?, 'queued', NULL, NULL, ?, NULL)",
                (run_id, conversation_id, message_id, organization_id, mode, created_at),
            )
            connection.commit()
        finally:
            connection.close()
        return {"message_id": message_id, "run_id": run_id}

    def event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> int:
        connection = self._database.connect()
        try:
            cursor = connection.execute(
                "INSERT INTO agent_run_events (run_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, event_type, json.dumps(payload, default=str), _now()),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def update_run(self, run_id: str, status: str, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        connection = self._database.connect()
        try:
            connection.execute(
                "UPDATE agent_runs SET status = ?, result_json = ?, error_json = ?, completed_at = ? WHERE id = ?",
                (status, json.dumps(result, default=str) if result else None, json.dumps(error) if error else None, _now() if status in {"completed", "failed"} else None, run_id),
            )
            connection.commit()
        finally:
            connection.close()

    def run_for_organization(self, run_id: str, organization_id: str) -> dict[str, Any] | None:
        connection = self._database.connect()
        try:
            row = connection.execute("SELECT * FROM agent_runs WHERE id = ? AND organization_id = ?", (run_id, organization_id)).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def conversation_for_organization(self, conversation_id: str, organization_id: str) -> dict[str, Any] | None:
        connection = self._database.connect()
        try:
            row = connection.execute(
                "SELECT * FROM agent_conversations WHERE id = ? AND organization_id = ?",
                (conversation_id, organization_id),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row else None

    def assistant_message(self, conversation_id: str, mode: str, text: str) -> str:
        message_id = f"msg_{uuid.uuid4().hex}"
        connection = self._database.connect()
        try:
            connection.execute(
                "INSERT INTO agent_messages VALUES (?, ?, 'assistant', ?, ?, NULL, ?)",
                (message_id, conversation_id, mode, text, _now()),
            )
            connection.commit()
        finally:
            connection.close()
        return message_id

    def conversation_window(
        self, conversation_id: str, organization_id: str, max_turns: int = 6
    ) -> list[dict[str, str]]:
        """Return the most recent non-empty turns as text-only episodic memory.

        No evidence, attachments, tokens, or hidden reasoning - just role + text,
        so a follow-up question can resolve what "it" refers to.
        """
        if self.conversation_for_organization(conversation_id, organization_id) is None:
            return []
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT role, text FROM agent_messages WHERE conversation_id = ? AND text != '' "
                "ORDER BY created_at DESC LIMIT ?",
                (conversation_id, max_turns),
            ).fetchall()
        finally:
            connection.close()
        return [{"role": row["role"], "text": row["text"]} for row in reversed(rows)]

    def conversation_summary(self, conversation_id: str, organization_id: str) -> str:
        conversation = self.conversation_for_organization(conversation_id, organization_id)
        return str((conversation or {}).get("summary") or "")

    def update_conversation_summary(self, conversation_id: str, summary: str) -> None:
        connection = self._database.connect()
        try:
            connection.execute(
                "UPDATE agent_conversations SET summary = ? WHERE id = ?", (summary[:4000], conversation_id)
            )
            connection.commit()
        finally:
            connection.close()

    def save_debug_trace(self, run_id: str, steps: list[dict[str, Any]]) -> None:
        """Persist the full per-step agent trace (prompts, context, reasoning)."""
        if not steps:
            return
        connection = self._database.connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO agent_debug_traces (run_id, steps_json, created_at) VALUES (?, ?, ?)",
                (run_id, json.dumps(steps, default=str), _now()),
            )
            connection.commit()
        finally:
            connection.close()

    def debug_trace(self, run_id: str, organization_id: str) -> list[dict[str, Any]]:
        if self.run_for_organization(run_id, organization_id) is None:
            return []
        connection = self._database.connect()
        try:
            row = connection.execute(
                "SELECT steps_json FROM agent_debug_traces WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            connection.close()
        return json.loads(row["steps_json"]) if row else []

    def latest_run_result(self, conversation_id: str, organization_id: str) -> dict[str, Any] | None:
        """The most recent completed run's result in this conversation - for reference resolution."""
        if self.conversation_for_organization(conversation_id, organization_id) is None:
            return None
        connection = self._database.connect()
        try:
            row = connection.execute(
                "SELECT result_json FROM agent_runs WHERE conversation_id = ? AND status = 'completed' "
                "AND result_json IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        finally:
            connection.close()
        return json.loads(row["result_json"]) if row else None

    def events_after(self, run_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT id, event_type, payload_json FROM agent_run_events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after_id),
            ).fetchall()
        finally:
            connection.close()
        return [{"id": row["id"], "event_type": row["event_type"], "payload": json.loads(row["payload_json"])} for row in rows]

    def list_runs(self, organization_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return safe run metadata for an organization administrator."""
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT id, conversation_id, mode, status, created_at, completed_at FROM agent_runs "
                "WHERE organization_id = ? ORDER BY created_at DESC LIMIT ?",
                (organization_id, limit),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def run_detail(self, run_id: str, organization_id: str) -> dict[str, Any] | None:
        """Return a run's safe event timeline and persisted conversation context."""
        run = self.run_for_organization(run_id, organization_id)
        if run is None:
            return None
        connection = self._database.connect()
        try:
            messages = connection.execute(
                "SELECT id, role, mode, text, attachment_json, created_at FROM agent_messages "
                "WHERE conversation_id = ? ORDER BY created_at",
                (run["conversation_id"],),
            ).fetchall()
        finally:
            connection.close()
        run["result"] = json.loads(run.pop("result_json")) if run.get("result_json") else None
        run["error"] = json.loads(run.pop("error_json")) if run.get("error_json") else None
        run["events"] = self.events_after(run_id)
        run["conversation"] = []
        for message in messages:
            item = dict(message)
            item["attachment"] = json.loads(item.pop("attachment_json") or "null")
            run["conversation"].append(item)
        return run