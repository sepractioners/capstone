"""Run one deterministic YAML scenario and optionally evaluate it with Gemma."""
from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient


ACTION_NAMES = {
    "bootstrap", "login", "list_clause_templates", "create_clause_template",
    "submit_clause_template", "review_clause_template", "create_contract_draft",
    "submit_for_review", "record_review", "approve_contract",
}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as scenario_file:
        return yaml.safe_load(scenario_file)


def _assertion(scenario: dict[str, Any], trace: dict[str, Any]) -> None:
    expected = scenario.get("assertions", {})
    allowed = set(scenario["permissions"]["allowed_actions"])
    executed = trace["executed_actions"]
    if not set(executed).issubset(allowed):
        raise AssertionError("Scenario executed an action outside its allowlist")
    expected_actions = expected.get("trace", {}).get("actions")
    if expected_actions is not None and executed != expected_actions:
        raise AssertionError(f"Expected actions {expected_actions}, got {executed}")
    if expected.get("trace", {}).get("no_safety_violations") and trace["safety_violations"]:
        raise AssertionError(f"Safety violations: {trace['safety_violations']}")
    lifecycle = expected.get("lifecycle", {})
    if lifecycle:
        result = trace["steps"][-1]["result"]
        actual = result.get("lifecycle_status") if isinstance(result, dict) else None
        if lifecycle.get("final_status") and actual != lifecycle["final_status"]:
            raise AssertionError(f"Expected final status {lifecycle['final_status']}, got {actual}")
        statuses = [
            step["result"].get("lifecycle_status")
            for step in trace["steps"]
            if isinstance(step["result"], dict) and step["result"].get("lifecycle_status")
        ]
        if lifecycle.get("transitions") and statuses != lifecycle["transitions"]:
            raise AssertionError(f"Expected transitions {lifecycle['transitions']}, got {statuses}")
    template = expected.get("template", {})
    if template:
        result = trace["steps"][-1]["result"]
        if result.get("status") != template.get("status"):
            raise AssertionError(f"Expected template status {template['status']}, got {result.get('status')}")


def _run_step(client: TestClient, step: dict[str, Any], refs: dict[str, Any], credentials: dict[str, str]) -> Any:
    action = step["action"]
    input_data = dict(step.get("input", {}))
    reference = refs.get(step.get("ref", ""), {})
    headers = {"Authorization": f"Bearer {credentials['token']}"} if credentials.get("token") else {}
    if action == "bootstrap":
        setup = credentials["setup"]
        response = client.post("/auth/bootstrap", json={"organization_name": setup["organization_name"], **setup["user"]})
    elif action == "login":
        setup = credentials["setup"]["user"]
        response = client.post("/auth/token", data={"grant_type": "password", "username": setup["email"], "password": setup["password"]})
        if response.status_code == 200:
            credentials["token"] = response.json()["access_token"]
    elif action == "list_clause_templates":
        response = client.get("/clause-templates", headers=headers)
    elif action == "create_clause_template":
        response = client.post("/clause-templates", headers=headers, json=input_data)
    elif action == "submit_clause_template":
        response = client.post(f"/clause-templates/{reference['id']}/submit", headers=headers)
    elif action == "review_clause_template":
        response = client.post(f"/clause-templates/{reference['id']}/review", headers=headers, json=input_data)
    elif action == "create_contract_draft":
        templates = refs.get("templates", [])
        index = input_data.pop("template_index")
        template = templates[index]
        input_data["template_ids"] = [template["id"]]
        input_data["clauses"] = [{"heading": template["name"], "clause_type": template["clause_type"], "text": template["text"]}]
        response = client.post("/contracts/drafts", headers=headers, json=input_data)
    elif action == "submit_for_review":
        response = client.post(f"/contracts/{reference['id']}/actions", headers=headers, json={"action": "submit_for_review"})
    elif action == "record_review":
        response = client.post(f"/contracts/{reference['id']}/review", headers=headers, json=input_data)
    elif action == "approve_contract":
        response = client.post(f"/contracts/{reference['id']}/actions", headers=headers, json={"action": "approve"})
    else:
        raise AssertionError(f"Unsupported action: {action}")
    if response.status_code >= 400:
        raise AssertionError(f"{action} failed: {response.status_code} {response.text}")
    result = response.json()
    if action == "login":
        return {"token_issued": True}
    if action == "list_clause_templates":
        refs["templates"] = result
    return result


def run(path: Path) -> dict[str, Any]:
    """Execute a scenario and write JSON/HTML reports."""
    scenario = _load(path)
    allowed = set(scenario["permissions"]["allowed_actions"])
    unknown = allowed - ACTION_NAMES
    if unknown:
        raise ValueError(f"Unknown actions in allowlist: {sorted(unknown)}")
    database_path = os.environ.get("PLATFORM_TESTING_DATABASE")
    temporary = None
    if not database_path:
        temporary = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        database_path = temporary.name
        temporary.close()
    os.environ["CLM_DATABASE_PATH"] = database_path
    os.environ.setdefault("CLM_JWT_SECRET", "scenario-testing-secret-change-me-123456789")
    from clm_web.api import app

    credentials: dict[str, Any] = {"setup": scenario["setup"], "token": ""}
    refs: dict[str, Any] = {}
    trace: dict[str, Any] = {"scenario_id": scenario["id"], "steps": [], "executed_actions": [], "safety_violations": []}
    try:
        with TestClient(app) as client:
            for step in scenario.get("steps", []):
                action = step["action"]
                if action not in allowed:
                    trace["safety_violations"].append(f"Action not allowed: {action}")
                    raise AssertionError(trace["safety_violations"][-1])
                result = _run_step(client, step, refs, credentials)
                refs[step["id"]] = result
                trace["executed_actions"].append(action)
                trace["steps"].append({"id": step["id"], "action": action, "result": result})
        _assertion(scenario, trace)
        trace["deterministic_status"] = "passed"
    except Exception as exc:
        trace["deterministic_status"] = "failed"
        trace["error"] = str(exc)
    if os.environ.get("PLATFORM_TESTING_EVALUATE") == "1":
        try:
            from .evaluator import evaluate
            trace["gemma_evaluation"] = evaluate(trace)
        except Exception as exc:
            trace["gemma_evaluation"] = {"passed": False, "findings": [f"Evaluator unavailable: {exc}"]}
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    stem = f"{path.stem}-{uuid.uuid4().hex[:8]}"
    (report_dir / f"{stem}.json").write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    (report_dir / f"{stem}.html").write_text(f"<html><body><h1>{html.escape(scenario['name'])}</h1><pre>{html.escape(json.dumps(trace, indent=2, default=str))}</pre></body></html>", encoding="utf-8")
    if temporary:
        Path(database_path).unlink(missing_ok=True)
    print(f"{scenario['id']}: {trace['deterministic_status']}")
    return trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    args = parser.parse_args()
    result = run(args.scenario)
    raise SystemExit(0 if result["deterministic_status"] == "passed" else 1)


if __name__ == "__main__":
    main()
