"""FastAPI routes for local identity, tenancy, and contract access."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import parse_qs

from contract_lifecycle.application.commands import (
    AddContractVersionCommand,
    ActivateContractCommand,
    ApproveContractCommand,
    CreateContractCommand,
    RecordReviewCommand,
    SubmitForReviewCommand,
)
from contract_lifecycle.domain.entities import Clause, ClauseType, ContractParty, PartyRole, PartyType, ReviewDecision
from contract_lifecycle.domain.exceptions import InvalidValueError
from contract_lifecycle.domain.value_objects import Actor, ContractId, ContractNumber, ContractType, DocumentReference, Jurisdiction, LegalName, OrganizationalRole, PartyId, VersionNumber
from contract_lifecycle.infrastructure.sqlite.contract_mapper import ContractMapper
from extraction_agent.pipeline import run as run_extraction
from query_agent.mcp_client import analyze_via_mcp
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from clm_mcp_server.dependencies import build_dependencies
from clm_mcp_server.ingest_contract_handler import ingest_contract
from clm_mcp_server.ingest_payload import ContractCandidate

from .db import WebDatabase
from .agent_orchestrator import AgentOrchestrator
from .agent_runs import AgentRunStore
from .security import create_access_token, decode_access_token, hash_password, new_secret, verify_password
from .settings import settings


app = FastAPI(title="CLM Web API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:5174",
        "https://localhost:5174",
        "https://localhost:8443",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)
database = WebDatabase(settings.database_path)
agent_runs = AgentRunStore(database)
agent_orchestrator = AgentOrchestrator(agent_runs, database)
dependencies = build_dependencies(
    settings.database_path,
    authority_roles=frozenset({"legal-approver", "automated-import"}),
)
mapper = ContractMapper()


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=12)
    display_name: str = Field(min_length=1, max_length=120)


class ClientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["contracts:read", "contracts:ingest"])


class CandidateRequest(BaseModel):
    candidate: ContractCandidate


class ReviewRequest(BaseModel):
    decision: str = "approved"
    comments: str | None = None


class ActionRequest(BaseModel):
    action: str
    effective_date: date | None = None
    comments: str | None = None


class AgentQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    contract_id: str | None = None


class AgentMessageRequest(BaseModel):
    mode: str = Field(pattern="^analysis$")
    text: str = Field(min_length=3, max_length=1000)
    contract_id: str | None = None


class DraftPartyRequest(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    role: str = "other"


class DraftClauseRequest(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    clause_type: str = "general_provision"


class DraftContractRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    contract_type: str = "vendor-agreement"
    parties: list[DraftPartyRequest] = Field(min_length=1, max_length=20)
    clauses: list[DraftClauseRequest] = Field(min_length=1, max_length=100)
    template_ids: list[str] = []


class ClauseTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    clause_type: str = "general_provision"
    text: str = Field(min_length=1, max_length=10000)
    tags: list[str] = []
    contract_types: list[str] = []
    jurisdiction: str = ""
    risk_level: str = "medium"


class ClauseReviewRequest(BaseModel):
    decision: str
    comments: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue_token(subject: str, organization_id: str | None, role: str, scopes: list[str]) -> dict[str, Any]:
    token = create_access_token(
        settings.jwt_secret,
        subject,
        {"iss": settings.issuer, "org": organization_id, "role": role, "scope": " ".join(scopes)},
        settings.access_token_seconds,
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.access_token_seconds, "scope": " ".join(scopes)}


def _bearer(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        return decode_access_token(settings.jwt_secret, header[7:].strip())
    except Exception as exc:  # jwt errors have a common public response
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc


def _require_scope(claims: dict[str, Any], scope: str) -> None:
    if scope not in str(claims.get("scope", "")).split():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing scope: {scope}")


def _require_org(claims: dict[str, Any]) -> str:
    organization_id = claims.get("org")
    if not organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context required")
    return organization_id


def _require_clause_role(claims: dict[str, Any], *roles: str) -> None:
    """Require a role allowed to manage or review clause templates."""
    if str(claims.get("role")) not in roles:
        raise HTTPException(status_code=403, detail="Clause template permission required")


def _require_agent_admin(claims: dict[str, Any]) -> None:
    """Restrict agent traces and persisted memory to organization administrators."""
    if str(claims.get("role")) != "admin":
        raise HTTPException(status_code=403, detail="Agent administration permission required")


def _tenant_contract(contract_id: str, organization_id: str) -> dict[str, Any]:
    """Return a contract only when it belongs to the caller's tenant."""
    connection = database.connect()
    try:
        row = connection.execute(
            "SELECT c.data FROM contracts c JOIN contract_tenants t ON t.contract_id = c.id WHERE c.id = ? AND t.organization_id = ?",
            (contract_id, organization_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return json.loads(row["data"])


def _actor(claims: dict[str, Any]) -> Actor:
    """Translate a web principal into the domain actor roles used by services."""
    role = str(claims.get("role", "read-only"))
    domain_role = "legal-approver" if role in {"admin", "contract_manager"} else role
    return Actor(
        actor_id=str(claims.get("sub")),
        display_name=str(claims.get("sub")),
        role=OrganizationalRole(domain_role),
    )


def _contract_type(raw: str) -> ContractType:
    try:
        return ContractType(raw)
    except InvalidValueError:
        ContractType.register(raw)
        return ContractType(raw)


def _draft_party(party: DraftPartyRequest) -> ContractParty:
    try:
        role = PartyRole(party.role)
    except ValueError:
        role = PartyRole.OTHER
    return ContractParty(
        party_id=PartyId.new(),
        legal_name=LegalName(party.legal_name.strip()),
        party_type=PartyType.ORGANIZATION,
        jurisdiction=Jurisdiction(country_code="US"),
        roles=(role,),
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Return a liveness response."""
    return {"status": "ok"}


@app.post("/auth/bootstrap")
def bootstrap(request: BootstrapRequest) -> dict[str, str]:
    """Create the first platform admin; disabled after the first user exists."""
    connection = database.connect()
    try:
        if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
            raise HTTPException(status_code=409, detail="Bootstrap is already complete")
        organization_id = f"org_{uuid.uuid4().hex}"
        user_id = f"usr_{uuid.uuid4().hex}"
        now = _now()
        connection.execute("INSERT INTO organizations VALUES (?, ?, ?)", (organization_id, request.organization_name, now))
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, 1, ?)",
            (user_id, request.email.lower(), hash_password(request.password), request.display_name, now),
        )
        connection.execute("INSERT INTO memberships VALUES (?, ?, ?)", (user_id, organization_id, "admin"))
        connection.commit()
        return {"user_id": user_id, "organization_id": organization_id, "message": "Bootstrap complete"}
    finally:
        connection.close()


@app.post("/auth/token")
async def token(request: Request) -> dict[str, Any]:
    """Issue a bearer token for password or OAuth client-credentials grants."""
    raw = (await request.body()).decode()
    values = {key: items[-1] for key, items in parse_qs(raw).items()}
    grant_type = values.get("grant_type", "password")
    connection = database.connect()
    try:
        if grant_type == "client_credentials":
            client_id = values.get("client_id", "")
            client_secret = values.get("client_secret", "")
            client = connection.execute("SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)).fetchone()
            if client is None or not verify_password(client_secret, client["client_secret_hash"]):
                raise HTTPException(status_code=401, detail="Invalid client credentials")
            requested = values.get("scope")
            scopes = requested.split() if requested else client["scopes"].split()
            allowed = set(client["scopes"].split())
            if not set(scopes).issubset(allowed):
                raise HTTPException(status_code=400, detail="Requested scope is not allowed")
            return _issue_token(client_id, client["organization_id"], "client", scopes)

        user = connection.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (values.get("username", "").lower(),)).fetchone()
        if user is None or not verify_password(values.get("password", ""), user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        membership = connection.execute("SELECT * FROM memberships WHERE user_id = ? LIMIT 1", (user["id"],)).fetchone()
        if membership is None:
            raise HTTPException(status_code=403, detail="User has no organization membership")
        return _issue_token(user["id"], membership["organization_id"], membership["role"], ["contracts:read", "contracts:ingest", "contracts:mutate"])
    finally:
        connection.close()


@app.get("/me")
def me(claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Return the authenticated principal and tenant context."""
    return {"subject": claims.get("sub"), "organization_id": claims.get("org"), "role": claims.get("role"), "scope": claims.get("scope", "").split()}


@app.post("/agent/query")
async def agent_query(request: AgentQueryRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Answer a tenant-scoped contract question with the query agent."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    if request.contract_id:
        _tenant_contract(request.contract_id, organization_id)
    try:
        result = await analyze_via_mcp(
            request.question,
            organization_id,
            request.contract_id,
            str(settings.database_path),
        )
        result.pop("debug_trace", None)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Query agent unavailable: {type(exc).__name__}") from exc


@app.post("/agent/conversations")
def create_agent_conversation(claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Create a tenant-owned conversation for agent chat messages."""
    _require_scope(claims, "contracts:read")
    return agent_runs.create_conversation(_require_org(claims), str(claims["sub"]))


@app.post("/agent/conversations/{conversation_id}/messages", status_code=202)
async def create_agent_message(
    conversation_id: str, request: AgentMessageRequest, claims: dict[str, Any] = Depends(_bearer)
) -> dict[str, str]:
    """Queue an analysis message and return its replayable SSE stream URL."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    if agent_runs.conversation_for_organization(conversation_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if request.contract_id:
        _tenant_contract(request.contract_id, organization_id)
    run = agent_runs.create_message_and_run(conversation_id, organization_id, request.mode, request.text, None)
    asyncio.create_task(
        agent_orchestrator.execute_run(
            run["run_id"], conversation_id, organization_id, "analysis",
            text=request.text, contract_id=request.contract_id
        )
    )
    return {"run_id": run["run_id"], "stream_url": f"/agent/runs/{run['run_id']}/events"}


@app.post("/agent/conversations/{conversation_id}/extractions", status_code=202)
async def create_agent_extraction(
    conversation_id: str,
    file: UploadFile = File(...),
    instruction: str = Form(""),
    claims: dict[str, Any] = Depends(_bearer),
) -> dict[str, str]:
    """Queue an attachment-based extraction and return its SSE stream URL."""
    _require_scope(claims, "contracts:ingest")
    organization_id = _require_org(claims)
    if agent_runs.conversation_for_organization(conversation_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in {".pdf", ".json", ".csv"}:
        raise HTTPException(status_code=415, detail="Only PDF, JSON, and CSV files are supported")
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(await file.read())
        temporary_path = temporary.name
    run = agent_runs.create_message_and_run(
        conversation_id,
        organization_id,
        "extraction",
        instruction,
        {"filename": file.filename, "media_type": file.content_type},
    )
    asyncio.create_task(
        agent_orchestrator.execute_run(
            run["run_id"], conversation_id, organization_id, "extraction",
            file_path=temporary_path, instruction=instruction
        )
    )
    return {"run_id": run["run_id"], "stream_url": f"/agent/runs/{run['run_id']}/events"}


@app.post("/agent/conversations/{conversation_id}/tasks", status_code=202)
async def create_agent_task(
    conversation_id: str,
    text: str = Form(""),
    file: UploadFile | None = File(None),
    claims: dict[str, Any] = Depends(_bearer),
) -> dict[str, str]:
    """Queue a planned multi-step task (optionally with an attachment) over SSE."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    if agent_runs.conversation_for_organization(conversation_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not text.strip() and file is None:
        raise HTTPException(status_code=422, detail="A task needs a message or an attachment")

    attachment_path: str | None = None
    attachment_meta: dict[str, Any] | None = None
    if file is not None:
        _require_scope(claims, "contracts:ingest")
        suffix = Path(file.filename or "upload.bin").suffix.lower()
        if suffix not in {".pdf", ".json", ".csv"}:
            raise HTTPException(status_code=415, detail="Only PDF, JSON, and CSV files are supported")
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(await file.read())
            attachment_path = temporary.name
        attachment_meta = {"filename": file.filename, "media_type": file.content_type}

    run = agent_runs.create_message_and_run(
        conversation_id, organization_id, "analysis", text or (file.filename if file else ""), attachment_meta
    )
    asyncio.create_task(
        agent_orchestrator.execute_run(
            run["run_id"], conversation_id, organization_id, "plan",
            text=text, file_path=attachment_path, instruction=text
        )
    )
    return {"run_id": run["run_id"], "stream_url": f"/agent/runs/{run['run_id']}/events"}


@app.get("/agent/runs/{run_id}/events")
async def stream_agent_run_events(run_id: str, request: Request, claims: dict[str, Any] = Depends(_bearer)) -> StreamingResponse:
    """Replay persisted run events and stream new events until a terminal state."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    if agent_runs.run_for_organization(run_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    try:
        after_id = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        after_id = 0

    async def event_stream():
        nonlocal after_id
        while True:
            events = agent_runs.events_after(run_id, after_id)
            for event in events:
                after_id = event["id"]
                yield f"id: {event['id']}\nevent: {event['event_type']}\ndata: {json.dumps(event['payload'])}\n\n"
            run = agent_runs.run_for_organization(run_id, organization_id)
            if run and run["status"] in {"completed", "failed"}:
                return
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/contracts")
def list_contracts(claims: dict[str, Any] = Depends(_bearer)) -> list[dict[str, Any]]:
    """List contracts owned by the caller's organization."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    connection = database.connect()
    try:
        rows = connection.execute(
            "SELECT c.data FROM contracts c JOIN contract_tenants t ON t.contract_id = c.id WHERE t.organization_id = ? ORDER BY c.updated_at DESC",
            (organization_id,),
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]
    finally:
        connection.close()


def _template_dict(row: Any, version_text: str | None = None) -> dict[str, Any]:
    """Serialize a clause template database row for the portal."""
    return {
        "id": row["id"], "organization_id": row["organization_id"], "name": row["name"],
        "description": row["description"], "clause_type": row["clause_type"],
        "tags": [tag for tag in row["tags"].split(",") if tag],
        "contract_types": [item for item in row["contract_types"].split(",") if item],
        "jurisdiction": row["jurisdiction"], "risk_level": row["risk_level"],
        "status": row["status"], "current_version": row["current_version"],
        "text": version_text,
    }


@app.get("/clause-templates")
def list_clause_templates(claims: dict[str, Any] = Depends(_bearer)) -> list[dict[str, Any]]:
    """List approved and editable global/tenant clause templates."""
    organization_id = _require_org(claims)
    connection = database.connect()
    try:
        rows = connection.execute(
            "SELECT * FROM clause_templates WHERE organization_id IS NULL OR organization_id = ? ORDER BY name",
            (organization_id,),
        ).fetchall()
        result = []
        for row in rows:
            version = connection.execute(
                "SELECT text FROM clause_template_versions WHERE template_id = ? AND version = ?",
                (row["id"], row["current_version"]),
            ).fetchone()
            result.append(_template_dict(row, version["text"] if version else None))
        return result
    finally:
        connection.close()


@app.post("/clause-templates")
def create_clause_template(request: ClauseTemplateRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Create an organization-owned draft clause template."""
    _require_clause_role(claims, "admin", "contract_manager")
    organization_id = _require_org(claims)
    template_id = f"clause_{uuid.uuid4().hex}"
    now = _now()
    connection = database.connect()
    try:
        connection.execute(
            "INSERT INTO clause_templates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (template_id, organization_id, request.name, request.description, request.clause_type,
             ",".join(request.tags), ",".join(request.contract_types), request.jurisdiction,
             request.risk_level, "draft", 1, str(claims["sub"]), now, now),
        )
        connection.execute(
            "INSERT INTO clause_template_versions VALUES (?, ?, ?, ?, ?)",
            (template_id, 1, request.text, str(claims["sub"]), now),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM clause_templates WHERE id = ?", (template_id,)).fetchone()
        return _template_dict(row, request.text)
    finally:
        connection.close()


@app.post("/clause-templates/{template_id}/submit")
def submit_clause_template(template_id: str, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, str]:
    """Submit an organization template for clause-reviewer approval."""
    _require_clause_role(claims, "admin", "contract_manager")
    organization_id = _require_org(claims)
    connection = database.connect()
    try:
        cursor = connection.execute(
            "UPDATE clause_templates SET status = 'in_review', updated_at = ? WHERE id = ? AND organization_id = ? AND status = 'draft'",
            (_now(), template_id, organization_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="Draft clause template not found")
        connection.commit()
        return {"status": "in_review"}
    finally:
        connection.close()


@app.post("/clause-templates/{template_id}/review")
def review_clause_template(template_id: str, request: ClauseReviewRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, str]:
    """Approve, reject, or archive a clause template as a clause reviewer."""
    _require_clause_role(claims, "admin", "clause_reviewer")
    decision = request.decision if request.decision in {"approved", "draft", "archived"} else None
    if decision is None:
        raise HTTPException(status_code=400, detail="Decision must be approved, draft, or archived")
    connection = database.connect()
    try:
        row = connection.execute("SELECT * FROM clause_templates WHERE id = ?", (template_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Clause template not found")
        connection.execute(
            "INSERT INTO clause_template_reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"review_{uuid.uuid4().hex}", template_id, row["current_version"], str(claims["sub"]), decision, request.comments, _now()),
        )
        connection.execute("UPDATE clause_templates SET status = ?, updated_at = ? WHERE id = ?", (decision, _now(), template_id))
        connection.commit()
        return {"status": decision}
    finally:
        connection.close()


@app.post("/contracts/drafts")
def create_draft_contract(request: DraftContractRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Create a tenant-bound draft contract with manually selected clauses."""
    _require_scope(claims, "contracts:ingest")
    organization_id = _require_org(claims)
    actor = _actor(claims)
    correlation_id = f"web-draft-{uuid.uuid4().hex}"
    contract_number = ContractNumber(f"WEB-{uuid.uuid4().hex[:16].upper()}")
    selected_templates: list[tuple[str, int]] = []
    if request.template_ids:
        connection = database.connect()
        try:
            placeholders = ",".join("?" for _ in request.template_ids)
            rows = connection.execute(
                f"SELECT * FROM clause_templates WHERE id IN ({placeholders}) AND status = 'approved' AND (organization_id IS NULL OR organization_id = ?)",
                [*request.template_ids, organization_id],
            ).fetchall()
            if len(rows) != len(request.template_ids):
                raise HTTPException(status_code=400, detail="One or more clause templates are unavailable")
            clauses_from_templates = []
            for row in rows:
                version = connection.execute(
                    "SELECT text FROM clause_template_versions WHERE template_id = ? AND version = ?",
                    (row["id"], row["current_version"]),
                ).fetchone()
                clauses_from_templates.append(DraftClauseRequest(heading=row["name"], clause_type=row["clause_type"], text=version["text"]))
                selected_templates.append((row["id"], row["current_version"]))
            request.clauses = clauses_from_templates
        finally:
            connection.close()
    source = {
        "title": request.title,
        "contract_type": request.contract_type,
        "parties": [party.model_dump() for party in request.parties],
        "clauses": [clause.model_dump() for clause in request.clauses],
    }
    source_bytes = json.dumps(source, sort_keys=True).encode("utf-8")
    content_hash = hashlib.sha256(source_bytes).hexdigest()
    document = DocumentReference(
        uri=f"web://contracts/{contract_number}",
        media_type="application/json",
        content_hash=content_hash,
    )
    contract = dependencies.intake.handle_create(
        CreateContractCommand(
            idempotency_key=f"create-{contract_number}",
            actor=actor,
            correlation_id=correlation_id,
            contract_type=_contract_type(request.contract_type),
            title=request.title,
            parties=[_draft_party(party) for party in request.parties],
            contract_number=str(contract_number),
        )
    )
    contract = dependencies.intake.handle_add_version(
        AddContractVersionCommand(
            idempotency_key=f"version-{contract_number}",
            actor=actor,
            correlation_id=correlation_id,
            contract_id=contract.id,
            document=document,
            author_id=actor.actor_id,
            change_summary="Created from portal clause selection",
        )
    )
    for index, clause_request in enumerate(request.clauses, start=1):
        normalized_type = clause_request.clause_type.lower().replace("-", "_")
        try:
            clause_type = ClauseType(normalized_type)
        except ValueError:
            clause_type = ClauseType.GENERAL_PROVISION
        contract.add_clause(
            Clause(
                clause_id=f"{contract_number}-clause-{index}",
                heading=clause_request.heading,
                text_reference=document,
                clause_type=clause_type,
                location="portal draft",
                version_number=contract.current_version.version_number,
                text=clause_request.text,
            )
        )
        if index <= len(selected_templates):
            connection = database.connect()
            try:
                connection.execute(
                    "INSERT INTO contract_clause_provenance VALUES (?, ?, ?, ?)",
                    (str(contract.id), f"{contract_number}-clause-{index}", selected_templates[index - 1][0], selected_templates[index - 1][1]),
                )
                connection.commit()
            finally:
                connection.close()
    dependencies.repository.save(contract)
    dependencies.blob_store.put(
        content_hash=content_hash,
        media_type="application/json",
        data=source_bytes,
        original_filename=f"{contract_number}.json",
    )
    connection = database.connect()
    try:
        connection.execute(
            "INSERT INTO contract_tenants (contract_id, organization_id, created_at) VALUES (?, ?, ?)",
            (str(contract.id), organization_id, _now()),
        )
        connection.commit()
    finally:
        connection.close()
    return mapper.to_dict(contract)


@app.get("/contracts/{contract_id}")
def get_contract(contract_id: str, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Return one tenant-scoped contract aggregate snapshot."""
    _require_scope(claims, "contracts:read")
    return _tenant_contract(contract_id, _require_org(claims))


@app.get("/agent-admin/extraction-traces")
def list_extraction_traces(claims: dict[str, Any] = Depends(_bearer)) -> list[dict[str, Any]]:
    """List safe extraction traces for the organization agent administrator."""
    _require_scope(claims, "contracts:read")
    _require_agent_admin(claims)
    connection = database.connect()
    try:
        rows = connection.execute(
            "SELECT e.contract_id, e.trace_json, e.created_at FROM extraction_traces e "
            "JOIN contract_tenants t ON t.contract_id = e.contract_id "
            "WHERE t.organization_id = ? ORDER BY e.created_at DESC",
            (_require_org(claims),),
        ).fetchall()
    finally:
        connection.close()
    return [
        {"contract_id": row["contract_id"], "events": json.loads(row["trace_json"]), "created_at": row["created_at"]}
        for row in rows
    ]


@app.get("/agent-admin/runs")
def list_agent_runs(claims: dict[str, Any] = Depends(_bearer)) -> list[dict[str, Any]]:
    """List safe, tenant-scoped agent runs for organization administrators."""
    _require_scope(claims, "contracts:read")
    _require_agent_admin(claims)
    return agent_runs.list_runs(_require_org(claims))


@app.get("/agent-admin/runs/{run_id}")
def get_agent_run(run_id: str, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Return safe run events and persisted conversation memory for administrators."""
    _require_scope(claims, "contracts:read")
    _require_agent_admin(claims)
    run = agent_runs.run_detail(run_id, _require_org(claims))
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@app.get("/agent-admin/runs/{run_id}/debug")
def get_agent_run_debug(run_id: str, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Return the full per-step agent trace: system prompts, context, reasoning, retrieval, timing."""
    _require_scope(claims, "contracts:read")
    _require_agent_admin(claims)
    organization_id = _require_org(claims)
    if agent_runs.run_for_organization(run_id, organization_id) is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return {"run_id": run_id, "steps": agent_runs.debug_trace(run_id, organization_id)}


@app.get("/contracts/{contract_id}/source")
def get_source(contract_id: str, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Return metadata and base64 source bytes for a tenant contract."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    contract = _tenant_contract(contract_id, organization_id)
    aggregate = dependencies.search.get(ContractId(contract_id))
    if aggregate.current_version is None:
        raise HTTPException(status_code=404, detail="Contract has no source version")
    stored = dependencies.blob_store.get(aggregate.current_version.document.content_hash)
    if stored is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return {
        "contract_id": contract["id"],
        "content_hash": stored.content_hash,
        "media_type": stored.media_type,
        "original_filename": stored.original_filename,
        "content_base64": base64.b64encode(stored.data).decode("ascii"),
    }


@app.get("/contracts/{contract_id}/source/download")
def download_source(contract_id: str, claims: dict[str, Any] = Depends(_bearer)) -> Response:
    """Download the tenant-scoped original source document as its stored media type."""
    _require_scope(claims, "contracts:read")
    organization_id = _require_org(claims)
    _tenant_contract(contract_id, organization_id)
    aggregate = dependencies.search.get(ContractId(contract_id))
    if aggregate.current_version is None:
        raise HTTPException(status_code=404, detail="Contract has no source version")
    stored = dependencies.blob_store.get(aggregate.current_version.document.content_hash)
    if stored is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    filename = (stored.original_filename or f"{contract_id}.bin").replace('"', "")
    return Response(
        content=stored.data,
        media_type=stored.media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/contracts/upload")
async def upload_contract(
    file: UploadFile = File(...), claims: dict[str, Any] = Depends(_bearer)
) -> list[dict[str, Any]]:
    """Run an uploaded PDF, JSON, or CSV file through the extraction agent."""
    _require_scope(claims, "contracts:ingest")
    organization_id = _require_org(claims)
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in {".pdf", ".json", ".csv"}:
        raise HTTPException(status_code=415, detail="Only PDF, JSON, and CSV files are supported")
    data = await file.read()
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(data)
        temporary_path = temporary.name
    try:
        results = await asyncio.to_thread(run_extraction, temporary_path, settings.database_path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
    connection = database.connect()
    try:
        for result in results:
            connection.execute(
                "INSERT OR IGNORE INTO contract_tenants VALUES (?, ?, ?)",
                (result["contract_id"], organization_id, _now()),
            )
            connection.execute(
                "INSERT OR REPLACE INTO extraction_traces VALUES (?, ?, ?)",
                (result["contract_id"], json.dumps(result.get("extraction_trace", [])), _now()),
            )
        connection.commit()
    finally:
        connection.close()
    return results


@app.post("/contracts/{contract_id}/review")
def review_contract(contract_id: str, request: ReviewRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Record a human review decision through the review application service."""
    _require_scope(claims, "contracts:mutate")
    organization_id = _require_org(claims)
    _tenant_contract(contract_id, organization_id)
    try:
        decision = ReviewDecision(request.decision)
        aggregate = dependencies.review.handle_record_review(
            RecordReviewCommand(
                idempotency_key=f"web-review-{contract_id}-{uuid.uuid4().hex}",
                actor=_actor(claims),
                correlation_id=f"web-{uuid.uuid4().hex}",
                contract_id=ContractId(contract_id),
                reviewer_id=str(claims["sub"]),
                review_type="portal-review",
                decision=decision,
                comments=request.comments,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return mapper.to_dict(aggregate)


@app.post("/contracts/{contract_id}/actions")
def lifecycle_action(contract_id: str, request: ActionRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Execute supported lifecycle actions through application services."""
    _require_scope(claims, "contracts:mutate")
    organization_id = _require_org(claims)
    _tenant_contract(contract_id, organization_id)
    actor = _actor(claims)
    command_id = f"web-{request.action}-{contract_id}-{uuid.uuid4().hex}"
    correlation_id = f"web-{uuid.uuid4().hex}"
    typed_id = ContractId(contract_id)
    try:
        if request.action == "submit_for_review":
            aggregate = dependencies.review.handle_submit_for_review(
                SubmitForReviewCommand(idempotency_key=command_id, actor=actor, correlation_id=correlation_id, contract_id=typed_id)
            )
        elif request.action == "approve":
            aggregate = dependencies.approval.handle_approve(
                ApproveContractCommand(
                    idempotency_key=command_id, actor=actor, correlation_id=correlation_id,
                    contract_id=typed_id, approver_id=str(claims["sub"]), authority_basis="portal-role", scope="full",
                )
            )
        elif request.action == "activate":
            aggregate = dependencies.execution.handle_activate(
                ActivateContractCommand(
                    idempotency_key=command_id, actor=actor, correlation_id=correlation_id,
                    contract_id=typed_id, effective_date=request.effective_date or date.today(),
                )
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported lifecycle action")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return mapper.to_dict(aggregate)


@app.post("/contracts/ingest")
def ingest(request: CandidateRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Ingest a candidate through the existing MCP handler and bind it to the tenant."""
    _require_scope(claims, "contracts:ingest")
    organization_id = _require_org(claims)
    result = ingest_contract(request.candidate, dependencies)
    connection = database.connect()
    try:
        connection.execute(
            "INSERT OR IGNORE INTO contract_tenants VALUES (?, ?, ?)",
            (result.contract_id, organization_id, _now()),
        )
        connection.execute(
            "INSERT OR REPLACE INTO extraction_traces VALUES (?, ?, ?)",
            (result.contract_id, json.dumps(result.extraction_trace), _now()),
        )
        connection.commit()
    finally:
        connection.close()
    return result.model_dump(mode="json")


@app.post("/oauth/clients")
def create_client(request: ClientRequest, claims: dict[str, Any] = Depends(_bearer)) -> dict[str, Any]:
    """Create tenant-scoped OAuth client credentials; the secret is returned once."""
    _require_scope(claims, "contracts:mutate")
    organization_id = _require_org(claims)
    client_id = f"cl_{secrets.token_urlsafe(18)}"
    client_secret = new_secret()
    connection = database.connect()
    try:
        connection.execute(
            "INSERT INTO oauth_clients VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, hash_password(client_secret), request.name, organization_id, " ".join(request.scopes), _now()),
        )
        connection.commit()
    finally:
        connection.close()
    return {"client_id": client_id, "client_secret": client_secret, "scopes": request.scopes}
