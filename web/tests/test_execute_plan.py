"""execute_plan threads step results and reacts to human-confirmation."""
from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

from clm_web import agent_orchestrator as orch_module
from clm_web.agent_orchestrator import AgentOrchestrator
from clm_web.agent_runs import AgentRunStore
from clm_web.db import WebDatabase
from clm_web.planner import Plan, PlanStep


def _orchestrator(path: str) -> tuple[AgentOrchestrator, AgentRunStore, str, str]:
    database = WebDatabase(path)
    connection = database.connect()
    connection.execute("INSERT INTO organizations VALUES ('org-a', 'Org A', 'now')")
    connection.execute("INSERT INTO users VALUES ('user-a', 'a@example.test', 'h', 'A', 1, 'now')")
    connection.execute("INSERT INTO memberships VALUES ('user-a', 'org-a', 'admin')")
    connection.commit()
    connection.close()
    store = AgentRunStore(database)
    conversation = store.create_conversation("org-a", "user-a")
    return AgentOrchestrator(store, database), store, "org-a", conversation["id"]


def test_extract_then_analyze_threads_the_new_contract_into_the_question() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    seen_questions: list[str] = []

    async def fake_analyze(question, organization_id, contract_id, database_path, history, clarify_round=0):
        seen_questions.append(question)
        return {"answer": f"analysis for {contract_id}", "confidence": 0.8, "citations": []}

    async def fake_extraction(file_path, database_path, directive, progress):
        return [{"contract_id": "c-123", "lifecycle_status": "approved", "extraction_trace": []}]

    try:
        orchestrator, store, org, conversation_id = _orchestrator(path)
        run = store.create_message_and_run(conversation_id, org, "analysis", "extract and compare", {"filename": "v.pdf"})
        plan = Plan(steps=[PlanStep(op="extract", input="ingest"), PlanStep(op="analyze", input="compare to vendor contracts")])
        with patch.object(orch_module.planner, "plan", new=AsyncMock(return_value=(plan, []))), patch.object(
            orch_module, "run_extraction", new=fake_extraction
        ), patch.object(orch_module, "analyze_via_mcp", new=fake_analyze):
            asyncio.run(
                orchestrator.execute_run(
                    run["run_id"], conversation_id, org, "plan",
                    text="extract and compare", file_path="/tmp/does-not-exist.pdf", instruction="extract and compare"
                )
            )

        detail = store.run_for_organization(run["run_id"], org)
        assert detail["status"] == "completed"
        assert seen_questions and "c-123" in seen_questions[0] and "Just extracted" in seen_questions[0]
    finally:
        os.remove(path)


def test_non_actionable_message_returns_a_clarification() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        orchestrator, store, org, conversation_id = _orchestrator(path)
        run = store.create_message_and_run(conversation_id, org, "analysis", "hi", None)
        plan = Plan(intent_ok=False, clarification="What would you like me to do?", steps=[])
        with patch.object(orch_module.planner, "plan", new=AsyncMock(return_value=(plan, []))):
            asyncio.run(orchestrator.execute_plan(run["run_id"], conversation_id, org, "hi", None, "hi"))

        result = store.run_detail(run["run_id"], org)
        assert result["result"] == {"clarification": "What would you like me to do?"}
        assert any(event["event_type"] == "assistant.message" for event in result["events"])
    finally:
        os.remove(path)
