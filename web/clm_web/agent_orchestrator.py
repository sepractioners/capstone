"""Execute durable agent runs and publish safe, replayable progress events.

Three entry points:

- ``execute_analysis`` - one tenant-scoped question, now with episodic memory
  (rolling summary + recent turns) so follow-ups resolve.
- ``execute_extraction`` - one attachment through the extraction pipeline.
- ``execute_plan`` - a planner turns one message (optionally with an attachment)
  into a short ``extract``/``analyze`` sequence, threading each step's result
  into the next and reacting when extraction needs human confirmation.

Every step still passes through the same tenant checks and only safe events
reach the SSE stream: never prompts, tokens, evidence payloads, or source bytes.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_llm.client import acall
from extraction_agent.pipeline import arun as run_extraction
from query_agent.mcp_client import analyze_via_mcp

from . import planner
from .agent_runs import AgentRunStore
from .db import WebDatabase

logger = logging.getLogger(__name__)

_SUMMARY_MIN_TURNS = max(4, int(os.environ.get("AGENT_SUMMARY_MIN_TURNS", "6")))
_SUMMARY_PROMPT = (
    "Summarize this contract-assistant conversation in 3-4 sentences: what the user asked, "
    "which contracts were involved, and what was answered or extracted. No preamble."
)


class AgentOrchestrator:
    """Routes explicit user-selected capabilities and planned tasks to agents."""

    def __init__(self, store: AgentRunStore, database: WebDatabase) -> None:
        self._store = store
        self._database = database
        self._database_path = database.database_path

    @staticmethod
    def extraction_directive(instruction: str) -> dict[str, Any] | None:
        """Turn a user preference into a non-authoritative extraction directive."""
        normalized = instruction.strip()
        if not normalized:
            return None
        match = re.search(r"\bas\s+(?:an?\s+)?([a-z][a-z -]{1,60}?)(?:\s*[.!?]|$)", normalized, re.IGNORECASE)
        requested_type = "-".join(match.group(1).lower().split()) if match else None
        return {"raw_instruction": normalized, "requested_contract_type": requested_type}

    # -- episodic memory -----------------------------------------------------

    def _history(self, conversation_id: str, organization_id: str) -> list[dict[str, str]]:
        """Rolling summary + recent turns, text only - passed to the query agent."""
        turns: list[dict[str, str]] = []
        summary = self._store.conversation_summary(conversation_id, organization_id)
        if summary:
            turns.append({"role": "system", "text": f"Earlier in this conversation: {summary}"})
        turns.extend(self._store.conversation_window(conversation_id, organization_id, max_turns=6))
        return turns

    @staticmethod
    def _clarify_round(history: list[dict[str, str]]) -> int:
        """Consecutive trailing assistant turns that read as a clarification
        question - the orchestrator's own count, passed to the query agent so it
        can stop asking once ``QUERY_CLARIFY_MAX_ROUNDS`` is reached (ADR-0006
        D3; mirrors the agent's own `_history_clarify_floor` backstop)."""
        rounds = 0
        for turn in reversed(history):
            if turn.get("role") != "assistant":
                continue
            if not str(turn.get("text", "")).strip().endswith("?"):
                break
            rounds += 1
        return rounds

    async def _refresh_summary(self, conversation_id: str, organization_id: str) -> None:
        window = self._store.conversation_window(conversation_id, organization_id, max_turns=20)
        if len(window) < _SUMMARY_MIN_TURNS:
            return
        transcript = "\n".join(f"{turn['role']}: {turn['text'][:400]}" for turn in window)
        summary = await self._summarize(transcript) or transcript[-1500:]
        self._store.update_conversation_summary(conversation_id, summary)

    async def _summarize(self, transcript: str) -> str:
        text, note = await acall("summary", _SUMMARY_PROMPT, transcript)
        if note:
            logger.debug("conversation summary unavailable: %s", note)
        return str(text or "").strip()

    # -- single capabilities ----------------------------------------------------

    async def _analysis(
        self, organization_id: str, question: str, contract_id: str | None, history: list[dict[str, str]]
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        clarify_round = self._clarify_round(history)
        result = await analyze_via_mcp(
            question, organization_id, contract_id, self._database_path, history, clarify_round
        )
        trace = result.pop("debug_trace", []) or []
        if result.get("error"):
            failure = RuntimeError(result["error"].get("message", "analysis failed"))
            failure.debug_trace = trace  # type: ignore[attr-defined]
            raise failure
        return result, str(result.get("answer", ""))[:600], trace

    async def _extraction(
        self, run_id: str, organization_id: str, file_path: str, instruction: str
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        async def progress(payload: dict[str, Any]) -> None:
            self._store.event(run_id, "progress", payload)

        results = await run_extraction(
            file_path, self._database_path, self.extraction_directive(instruction), progress
        )
        self._bind_extraction_results(results, organization_id)
        trace = [step for item in results for step in (item.pop("debug_trace", []) or [])]
        payload = {"results": results}
        confirm = [item for item in results if item.get("requires_human_confirmation")]
        contract_ids = [item.get("contract_id") for item in results if item.get("contract_id")]
        if confirm:
            summary = "Extraction needs contract-type confirmation before it can be saved."
        elif contract_ids:
            summary = f"Extracted and saved contract {contract_ids[0]}."
        else:
            summary = "Contract extraction completed."
        return payload, summary, trace

    # -- unified entry point --------------------------------------------------

    async def execute_run(
        self,
        run_id: str,
        conversation_id: str,
        organization_id: str,
        mode: str,
        text: str = "",
        contract_id: str | None = None,
        file_path: str | None = None,
        instruction: str = "",
    ) -> None:
        """Route to the appropriate agent capability based on mode.

        Modes:
        - "analysis": single question on contract(s)
        - "extraction": run file through extraction pipeline
        - "plan": multi-step reasoning with optional attachment
        """
        if mode == "analysis":
            await self._execute_analysis(run_id, conversation_id, organization_id, text, contract_id)
        elif mode == "extraction":
            await self._execute_extraction(run_id, conversation_id, organization_id, file_path or "", instruction)
        elif mode == "plan":
            await self._execute_plan(run_id, conversation_id, organization_id, text, file_path, instruction)
        else:
            self._store.update_run(run_id, "failed", error={"code": "invalid_mode", "message": f"Unknown mode: {mode}"})

    # -- run entry points (private; use execute_run) ---------------------------

    async def _execute_analysis(
        self, run_id: str, conversation_id: str, organization_id: str, question: str, contract_id: str | None
    ) -> None:
        self._store.update_run(run_id, "running")
        self._store.event(run_id, "run.started", {"mode": "analysis"})
        self._store.event(run_id, "progress", {"stage": "retrieving_evidence", "label": "Retrieving contract evidence"})
        history = self._history(conversation_id, organization_id)
        try:
            result, answer_summary, trace = await self._analysis(organization_id, question, contract_id, history)
        except Exception as exc:
            self._store.save_debug_trace(run_id, getattr(exc, "debug_trace", []))
            error = {"code": "analysis_unavailable", "message": "Contract analysis is currently unavailable."}
            self._store.update_run(run_id, "failed", error=error)
            self._store.event(run_id, "run.failed", error)
            return
        self._store.save_debug_trace(run_id, trace)
        self._store.assistant_message(conversation_id, "analysis", result["answer"])
        self._store.update_run(run_id, "completed", result=result)
        self._store.event(run_id, "assistant.message", result)
        self._store.event(run_id, "run.completed", {"run_id": run_id})
        await self._refresh_summary(conversation_id, organization_id)

    async def _execute_extraction(
        self, run_id: str, conversation_id: str, organization_id: str, file_path: str, instruction: str
    ) -> None:
        self._store.update_run(run_id, "running")
        self._store.event(run_id, "run.started", {"mode": "extraction"})
        self._store.event(run_id, "progress", {"stage": "routing", "label": "Preparing contract extraction"})
        try:
            result, message, trace = await self._extraction(run_id, organization_id, file_path, instruction)
        except Exception as exc:
            self._store.save_debug_trace(run_id, getattr(exc, "debug_trace", []))
            error = {"code": "extraction_unavailable", "message": "Contract extraction is currently unavailable."}
            self._store.update_run(run_id, "failed", error=error)
            self._store.event(run_id, "run.failed", error)
            return
        finally:
            Path(file_path).unlink(missing_ok=True)
        self._store.save_debug_trace(run_id, trace)
        self._store.assistant_message(conversation_id, "extraction", message)
        self._store.update_run(run_id, "completed", result=result)
        self._store.event(run_id, "extraction.completed", result)
        self._store.event(run_id, "run.completed", {"run_id": run_id})
        await self._refresh_summary(conversation_id, organization_id)

    async def _execute_plan(
        self,
        run_id: str,
        conversation_id: str,
        organization_id: str,
        message: str,
        attachment_path: str | None,
        instruction: str,
    ) -> None:
        self._store.update_run(run_id, "running")
        self._store.event(run_id, "run.started", {"mode": "auto"})
        trace: list[dict[str, Any]] = []
        try:
            plan, plan_trace = await planner.plan(message, attachment_path is not None)
            trace.extend(plan_trace)
            self._store.event(run_id, "plan", {"steps": [step.model_dump() for step in plan.steps], "intent_ok": plan.intent_ok})

            if not plan.intent_ok:
                self._store.save_debug_trace(run_id, trace)
                self._store.assistant_message(conversation_id, "analysis", plan.clarification)
                self._store.update_run(run_id, "completed", result={"clarification": plan.clarification})
                self._store.event(run_id, "assistant.message", {"answer": plan.clarification})
                self._store.event(run_id, "run.completed", {"run_id": run_id})
                return

            step_results: list[dict[str, Any]] = []
            summaries: list[str] = []
            context_contract_id: str | None = None
            context_note = ""

            for index, step in enumerate(plan.steps):
                self._store.event(run_id, "step", {"index": index + 1, "total": len(plan.steps), "op": step.op})
                if step.op == "extract":
                    if attachment_path is None:
                        continue
                    payload, summary, step_trace = await self._extraction(run_id, organization_id, attachment_path, step.input or instruction)
                    for item in payload["results"]:
                        if item.get("requires_human_confirmation"):
                            self._store.event(run_id, "needs_confirmation", {"review": item.get("review_findings", [])})
                        if item.get("contract_id"):
                            context_contract_id = item["contract_id"]
                    context_note = f"(Just extracted: {summary}) "
                else:
                    question = f"{context_note}{step.input or message}".strip()
                    history = self._history(conversation_id, organization_id)
                    payload, summary, step_trace = await self._analysis(organization_id, question, context_contract_id, history)
                trace.extend(step_trace)
                step_results.append({"op": step.op, "result": payload, "summary": summary})
                summaries.append(summary)

            self._store.save_debug_trace(run_id, trace)
            final_message = "\n\n".join(summaries) or "Task completed."
            self._store.assistant_message(conversation_id, "analysis", final_message)
            self._store.update_run(run_id, "completed", result={"steps": step_results})
            self._store.event(run_id, "assistant.message", {"answer": final_message, "steps": step_results})
            self._store.event(run_id, "run.completed", {"run_id": run_id})
            await self._refresh_summary(conversation_id, organization_id)
        except Exception as exc:
            trace.extend(getattr(exc, "debug_trace", []))
            self._store.save_debug_trace(run_id, trace)
            error = {"code": "task_unavailable", "message": "The agent task could not be completed."}
            self._store.update_run(run_id, "failed", error=error)
            self._store.event(run_id, "run.failed", error)
        finally:
            if attachment_path:
                Path(attachment_path).unlink(missing_ok=True)

    # -- backward compatibility ------------------------------------------------

    async def execute_analysis(
        self, run_id: str, conversation_id: str, organization_id: str, question: str, contract_id: str | None
    ) -> None:
        """Deprecated: use execute_run(mode='analysis', ...) instead."""
        await self.execute_run(run_id, conversation_id, organization_id, "analysis", text=question, contract_id=contract_id)

    async def execute_extraction(
        self, run_id: str, conversation_id: str, organization_id: str, file_path: str, instruction: str
    ) -> None:
        """Deprecated: use execute_run(mode='extraction', ...) instead."""
        await self.execute_run(run_id, conversation_id, organization_id, "extraction", file_path=file_path, instruction=instruction)

    async def execute_plan(
        self, run_id: str, conversation_id: str, organization_id: str, message: str, attachment_path: str | None, instruction: str
    ) -> None:
        """Deprecated: use execute_run(mode='plan', ...) instead."""
        await self.execute_run(run_id, conversation_id, organization_id, "plan", text=message, file_path=attachment_path, instruction=instruction)

    def _bind_extraction_results(self, results: list[dict[str, Any]], organization_id: str) -> None:
        connection = self._database.connect()
        try:
            for result in results:
                contract_id = result.get("contract_id")
                if not contract_id:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO contract_tenants VALUES (?, ?, datetime('now'))",
                    (contract_id, organization_id),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO extraction_traces VALUES (?, ?, datetime('now'))",
                    (contract_id, json.dumps(result.get("extraction_trace", []))),
                )
            connection.commit()
        finally:
            connection.close()
