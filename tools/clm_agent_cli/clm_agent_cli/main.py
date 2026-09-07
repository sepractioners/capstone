"""Interactive and scriptable client for the CLM agent SSE API."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import httpx
import typer

app = typer.Typer(no_args_is_help=True)
DEFAULT_API_URL = os.environ.get("CLM_API_URL", "https://localhost:8443")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(token: str | None) -> str:
    return token or os.environ.get("CLM_AGENT_TOKEN") or typer.prompt("Bearer access token", hide_input=True)


def _conversation(client: httpx.Client, token: str) -> str:
    response = client.post("/agent/conversations", headers=_headers(token))
    response.raise_for_status()
    return response.json()["id"]


def _events(client: httpx.Client, stream_url: str, token: str) -> Iterator[tuple[str, dict[str, Any]]]:
    with client.stream("GET", stream_url, headers=_headers(token)) as response:
        response.raise_for_status()
        event_type = "message"
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                yield event_type, json.loads(line[6:])
                event_type = "message"


def _render(events: Iterator[tuple[str, dict[str, Any]]], as_json: bool) -> None:
    for event_type, payload in events:
        if event_type == "progress":
            typer.echo(payload.get("label", "Working"), err=True)
        elif event_type == "plan":
            steps = ", ".join(step.get("op", "?") for step in payload.get("steps", []))
            typer.echo(f"Plan: {steps or 'clarification'}", err=True)
        elif event_type == "step":
            typer.echo(f"Step {payload.get('index')}/{payload.get('total')}: {payload.get('op')}", err=True)
        elif event_type == "needs_confirmation":
            typer.echo("Extraction needs contract-type confirmation before it is saved.", err=True)
        elif event_type in {"assistant.message", "extraction.completed"}:
            typer.echo(json.dumps(payload) if as_json else json.dumps(payload, indent=2))
        elif event_type == "run.failed":
            typer.echo(payload.get("message", "Agent run failed"), err=True)
            raise typer.Exit(1)


@app.command()
def ask(
    question: str,
    contract_id: str | None = typer.Option(None),
    token: str | None = typer.Option(None, envvar="CLM_AGENT_TOKEN"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="CLM_API_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Ask an analysis question and render streamed progress and answer."""
    resolved_token = _token(token)
    with httpx.Client(base_url=api_url, verify=False, timeout=None) as client:
        conversation_id = _conversation(client, resolved_token)
        response = client.post(
            f"/agent/conversations/{conversation_id}/messages",
            headers=_headers(resolved_token),
            json={"mode": "analysis", "text": question, "contract_id": contract_id},
        )
        response.raise_for_status()
        _render(_events(client, response.json()["stream_url"], resolved_token), as_json)


@app.command()
def extract(
    source: Path,
    instruction: str = typer.Option("", help="Optional non-authoritative extraction preference."),
    token: str | None = typer.Option(None, envvar="CLM_AGENT_TOKEN"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="CLM_API_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Upload a contract and render extraction progress and result."""
    if not source.is_file():
        raise typer.BadParameter("Source file does not exist")
    resolved_token = _token(token)
    with httpx.Client(base_url=api_url, verify=False, timeout=None) as client, source.open("rb") as file_handle:
        conversation_id = _conversation(client, resolved_token)
        response = client.post(
            f"/agent/conversations/{conversation_id}/extractions",
            headers=_headers(resolved_token),
            data={"instruction": instruction},
            files={"file": (source.name, file_handle)},
        )
        response.raise_for_status()
        _render(_events(client, response.json()["stream_url"], resolved_token), as_json)


@app.command()
def task(
    message: str,
    file: Path | None = typer.Option(None, "--file", help="Optional PDF/JSON/CSV attachment for an extraction step."),
    token: str | None = typer.Option(None, envvar="CLM_AGENT_TOKEN"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="CLM_API_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run a planned multi-step task; the planner decides extract/analyze steps."""
    if file is not None and not file.is_file():
        raise typer.BadParameter("Attachment file does not exist")
    resolved_token = _token(token)
    with httpx.Client(base_url=api_url, verify=False, timeout=None) as client:
        conversation_id = _conversation(client, resolved_token)
        request: dict[str, Any] = {"data": {"text": message}}
        handle = file.open("rb") if file is not None else None
        try:
            if handle is not None:
                request["files"] = {"file": (file.name, handle)}
            response = client.post(
                f"/agent/conversations/{conversation_id}/tasks", headers=_headers(resolved_token), **request
            )
        finally:
            if handle is not None:
                handle.close()
        response.raise_for_status()
        _render(_events(client, response.json()["stream_url"], resolved_token), as_json)


@app.command()
def watch(
    run_id: str,
    token: str | None = typer.Option(None, envvar="CLM_AGENT_TOKEN"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="CLM_API_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Reconnect to an existing agent run's SSE stream."""
    resolved_token = _token(token)
    with httpx.Client(base_url=api_url, verify=False, timeout=None) as client:
        _render(_events(client, f"/agent/runs/{run_id}/events", resolved_token), as_json)


@app.command()
def chat(
    token: str | None = typer.Option(None, envvar="CLM_AGENT_TOKEN"),
    api_url: str = typer.Option(DEFAULT_API_URL, envvar="CLM_API_URL"),
) -> None:
    """Open an interactive analysis chat session; type 'exit' to leave."""
    resolved_token = _token(token)
    with httpx.Client(base_url=api_url, verify=False, timeout=None) as client:
        conversation_id = _conversation(client, resolved_token)
        while True:
            question = typer.prompt("analysis")
            if question.strip().lower() in {"exit", "quit"}:
                return
            response = client.post(
                f"/agent/conversations/{conversation_id}/messages",
                headers=_headers(resolved_token),
                json={"mode": "analysis", "text": question},
            )
            response.raise_for_status()
            _render(_events(client, response.json()["stream_url"], resolved_token), False)


if __name__ == "__main__":
    app()