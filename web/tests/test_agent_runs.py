import os
import tempfile

from clm_web.agent_orchestrator import AgentOrchestrator
from clm_web.agent_runs import AgentRunStore
from clm_web.db import WebDatabase


def test_run_events_are_ordered_and_scoped_to_the_run_organization() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        database = WebDatabase(path)
        connection = database.connect()
        connection.execute("INSERT INTO organizations VALUES ('org-a', 'Organization A', 'now')")
        connection.execute("INSERT INTO users VALUES ('user-a', 'a@example.test', 'hash', 'A', 1, 'now')")
        connection.execute("INSERT INTO memberships VALUES ('user-a', 'org-a', 'admin')")
        connection.commit()
        connection.close()
        store = AgentRunStore(database)
        conversation = store.create_conversation("org-a", "user-a")
        run = store.create_message_and_run(conversation["id"], "org-a", "analysis", "When does it expire?", None)
        first_event = store.event(run["run_id"], "run.started", {"mode": "analysis"})
        second_event = store.event(run["run_id"], "progress", {"stage": "retrieving_evidence"})
        assert [event["id"] for event in store.events_after(run["run_id"])] == [first_event, second_event]
        assert [event["event_type"] for event in store.events_after(run["run_id"], first_event)] == ["progress"]
        assert store.run_for_organization(run["run_id"], "org-a") is not None
        assert store.run_for_organization(run["run_id"], "org-b") is None
    finally:
        os.remove(path)


def test_extraction_instruction_is_a_non_authoritative_contract_type_preference() -> None:
    directive = AgentOrchestrator.extraction_directive("Extract this as a vendor agreement.")
    assert directive == {
        "raw_instruction": "Extract this as a vendor agreement.",
        "requested_contract_type": "vendor-agreement",
    }


def _seeded_store(path: str) -> tuple[AgentRunStore, str]:
    database = WebDatabase(path)
    connection = database.connect()
    connection.execute("INSERT INTO organizations VALUES ('org-a', 'Organization A', 'now')")
    connection.execute("INSERT INTO users VALUES ('user-a', 'a@example.test', 'hash', 'A', 1, 'now')")
    connection.execute("INSERT INTO memberships VALUES ('user-a', 'org-a', 'admin')")
    connection.commit()
    connection.close()
    return AgentRunStore(database), "org-a"


def test_conversation_window_and_summary_are_tenant_scoped() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        store, org = _seeded_store(path)
        conversation = store.create_conversation(org, "user-a")
        store.create_message_and_run(conversation["id"], org, "analysis", "When does contract X expire?", None)
        store.assistant_message(conversation["id"], "analysis", "Contract X expires 2027-01-01.")

        window = store.conversation_window(conversation["id"], org, max_turns=6)
        assert [turn["role"] for turn in window] == ["user", "assistant"]
        assert store.conversation_window(conversation["id"], "org-b") == []

        store.update_conversation_summary(conversation["id"], "Discussed contract X expiry.")
        assert store.conversation_summary(conversation["id"], org) == "Discussed contract X expiry."
        assert store.conversation_summary(conversation["id"], "org-b") == ""
    finally:
        os.remove(path)


def test_debug_trace_round_trips_and_is_tenant_scoped() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        store, org = _seeded_store(path)
        conversation = store.create_conversation(org, "user-a")
        run = store.create_message_and_run(conversation["id"], org, "analysis", "q", None)
        steps = [{"step": 1, "phase": "decompose", "system_prompt": "Break the question...", "reasoning": "one part"}]
        store.save_debug_trace(run["run_id"], steps)

        assert store.debug_trace(run["run_id"], org)[0]["system_prompt"].startswith("Break")
        assert store.debug_trace(run["run_id"], "org-b") == []
        store.save_debug_trace(run["run_id"], [])  # empty is a no-op
        assert len(store.debug_trace(run["run_id"], org)) == 1
    finally:
        os.remove(path)


def test_latest_run_result_returns_the_most_recent_completed_run() -> None:
    descriptor, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        store, org = _seeded_store(path)
        conversation = store.create_conversation(org, "user-a")
        first = store.create_message_and_run(conversation["id"], org, "analysis", "q1", None)
        store.update_run(first["run_id"], "completed", result={"answer": "a1"})
        second = store.create_message_and_run(conversation["id"], org, "analysis", "q2", None)
        store.update_run(second["run_id"], "completed", result={"answer": "a2"})

        assert store.latest_run_result(conversation["id"], org) == {"answer": "a2"}
        assert store.latest_run_result(conversation["id"], "org-b") is None
    finally:
        os.remove(path)