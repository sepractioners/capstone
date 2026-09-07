import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import {
  Bot,
  Download,
  FileText,
  LogIn,
  Paperclip,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";

type Party = { legal_name: string; roles?: string[]; party_type?: string };
type Clause = {
  heading: string;
  clause_type: string;
  page_location: string;
  text: string;
};
type Contract = {
  id: string;
  title: string;
  contract_number: string;
  lifecycle_status: string;
  contract_type?: string;
  source_uri?: string;
  source_original_filename?: string;
  parties?: Party[];
  clauses?: Clause[];
  field_conflicts?: { field: string; candidate_values: string[] }[];
};
type Principal = { organization_id: string; role: string };
type ClauseTemplate = {
  id: string;
  organization_id?: string;
  name: string;
  clause_type: string;
  text: string;
  status: string;
  current_version: number;
};
type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  mode: "extraction" | "auto";
  text: string;
  citations?: { contract_id: string; label: string; evidence: string }[];
  results?: { contract_id?: string; lifecycle_status?: string; requires_human_confirmation?: boolean }[];
};

const API_URL = import.meta.env.VITE_API_URL ?? "https://localhost:8443";

async function api(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const token = sessionStorage.getItem("clm_access_token");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok)
    throw new Error((await response.json()).detail ?? "Request failed");
  return response.json();
}

async function downloadSource(contract: Contract) {
  const token = sessionStorage.getItem("clm_access_token");
  const response = await fetch(
    `${API_URL}/contracts/${contract.id}/source/download`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) throw new Error("Source document is not available");
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  const disposition = response.headers.get("content-disposition") ?? "";
  link.download =
    disposition.match(/filename="([^"]+)"/i)?.[1] ??
    contract.source_original_filename ??
    `${contract.contract_number}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function Login({ onLogin }: { onLogin: (principal: Principal) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch(`${API_URL}/auth/token`, {
        method: "POST",
        body: new URLSearchParams({
          grant_type: "password",
          username: email,
          password,
        }),
      });
      if (!response.ok) throw new Error("Invalid email or password");
      const token = await response.json();
      sessionStorage.setItem("clm_access_token", token.access_token);
      onLogin(await api("/me"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in");
    }
  }
  return (
    <main className="login-page">
      <section className="login-copy">
        <span className="eyebrow">Contract operations</span>
        <h1>Make every agreement easier to move forward.</h1>
        <p>
          Review extracted facts, create governed drafts, and keep lifecycle
          decisions visible.
        </p>
        <div className="trust">
          <ShieldCheck size={18} /> Tenant-scoped access with bearer tokens
        </div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          CLM<span>·</span>
        </div>
        <h2>Welcome back</h2>
        <p className="muted">Sign in to your contract workspace.</p>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit">
          <LogIn size={17} /> Sign in
        </button>
      </form>
    </main>
  );
}

function CreateDraftForm({
  busy,
  onClose,
  onCreated,
}: {
  busy: boolean;
  onClose: () => void;
  onCreated: (contract: Contract) => void;
}) {
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [vendor, setVendor] = useState("");
  const [templates, setTemplates] = useState<ClauseTemplate[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/clause-templates")
      .then((items) => {
        setTemplates(items);
        setSelected(
          items
            .filter((item: ClauseTemplate) => item.status === "approved")
            .slice(0, 1)
            .map((item: ClauseTemplate) => item.id),
        );
      })
      .catch((cause) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load clause library",
        ),
      );
  }, []);
  function toggleTemplate(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api("/contracts/drafts", {
        method: "POST",
        body: JSON.stringify({
          title,
          contract_type: "vendor-agreement",
          parties: [
            { legal_name: customer, role: "customer" },
            { legal_name: vendor, role: "vendor" },
          ],
          template_ids: selected,
          clauses: selected.map((id) => {
            const item = templates.find((template) => template.id === id)!;
            return {
              heading: item.name,
              clause_type: item.clause_type,
              text: item.text,
            };
          }),
        }),
      });
      onCreated(result);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to create draft",
      );
    }
  }
  return (
    <aside className="reader create-drawer">
      <button
        className="close"
        aria-label="Close create form"
        onClick={onClose}
      >
        <X size={19} />
      </button>
      <span className="eyebrow">New governed draft</span>
      <h2>Create contract</h2>
      <p className="muted">
        Choose approved clauses from the managed library, create a draft, then
        submit it for review.
      </p>
      <form className="create-form" onSubmit={submit}>
        <label>
          Contract title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Master Services Agreement"
            required
          />
        </label>
        <label>
          Customer
          <input
            value={customer}
            onChange={(event) => setCustomer(event.target.value)}
            placeholder="Customer legal name"
            required
          />
        </label>
        <label>
          Vendor
          <input
            value={vendor}
            onChange={(event) => setVendor(event.target.value)}
            placeholder="Vendor legal name"
            required
          />
        </label>
        <fieldset>
          <legend>Clause library</legend>
          {templates
            .filter((clause) => clause.status === "approved")
            .map((clause) => (
              <label className="clause-choice" key={clause.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(clause.id)}
                  onChange={() => toggleTemplate(clause.id)}
                />
                <span>
                  <strong>{clause.name}</strong>
                  <small>{clause.text}</small>
                </span>
              </label>
            ))}
        </fieldset>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={busy || selected.length === 0}>
          <Plus size={17} /> Create draft
        </button>
      </form>
    </aside>
  );
}

const CONTRACT_REF_RE = /\bcontract[_-][0-9a-f]{12,}\b/gi;
const BOLD_RE = /\*\*(.+?)\*\*/g;

/** Inline runs: **bold** spans and clickable links for any contract id that
 * resolves to a contract the user can actually open; everything else is plain. */
function renderInline(
  text: string,
  known: Map<string, Contract>,
  onOpen: (id: string) => void,
  keyPrefix: string,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let n = 0;

  const linkify = (chunk: string) => {
    let last = 0;
    for (const match of chunk.matchAll(CONTRACT_REF_RE)) {
      const id = match[0];
      const start = match.index ?? 0;
      const contract = known.get(id);
      if (!contract) continue;
      if (start > last) nodes.push(chunk.slice(last, start));
      nodes.push(
        <button key={`${keyPrefix}-l${n++}`} type="button" className="contract-link" onClick={() => onOpen(id)}>
          {contract.title}
        </button>,
      );
      last = start + id.length;
    }
    if (last < chunk.length) nodes.push(chunk.slice(last));
  };

  let cursor = 0;
  for (const match of text.matchAll(BOLD_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) linkify(text.slice(cursor, start));
    nodes.push(<strong key={`${keyPrefix}-b${n++}`}>{match[1]}</strong>);
    cursor = start + match[0].length;
  }
  if (cursor < text.length) linkify(text.slice(cursor));
  return nodes;
}

/** Answer text -> paragraphs and bullet lists, with inline links. */
function renderAnswer(
  text: string,
  known: Map<string, Contract>,
  onOpen: (id: string) => void,
): ReactElement[] {
  const blocks: ReactElement[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (!bullets.length) return;
    const at = blocks.length;
    blocks.push(
      <ul key={`ul${at}`} className="chat-list">
        {bullets.map((item, i) => (
          <li key={i}>{renderInline(item, known, onOpen, `ul${at}-${i}`)}</li>
        ))}
      </ul>,
    );
    bullets = [];
  };
  for (const raw of text.split(/\r?\n/)) {
    const bullet = raw.match(/^\s*[*\-•]\s+(.*)/);
    if (bullet) {
      bullets.push(bullet[1]);
      continue;
    }
    flush();
    if (raw.trim()) {
      const at = blocks.length;
      blocks.push(<p key={`p${at}`}>{renderInline(raw, known, onOpen, `p${at}`)}</p>);
    }
  }
  flush();
  return blocks.length ? blocks : [<p key="p0">{text}</p>];
}

function AgentChat({
  contracts,
  onOpenContract,
}: {
  contracts: Contract[];
  onOpenContract: (id: string) => void;
}) {
  const [conversationId, setConversationId] = useState("");
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [queued, setQueued] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const contractsById = new Map(contracts.map((contract) => [contract.id, contract]));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, queued.length, busy]);

  // A message typed while the agent is working is held as "queued" and sent once
  // the current run finishes - the composer is never blocked on run state.
  useEffect(() => {
    if (busy || queued.length === 0) return;
    const [next, ...rest] = queued;
    setQueued(rest);
    void runTask(next, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, queued]);

  function resetChat() {
    setConversationId("");
    setMessages([]);
    setQueued([]);
    setText("");
    setAttachment(null);
    setError("");
  }

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const created = await api("/agent/conversations", { method: "POST" });
    setConversationId(created.id);
    return created.id as string;
  }

  async function stream(run: { run_id: string; stream_url: string }) {
    const token = sessionStorage.getItem("clm_access_token");
    const response = await fetch(`${API_URL}${run.stream_url}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok || !response.body) throw new Error("Unable to open agent event stream");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        const type = event.match(/^event: (.+)$/m)?.[1];
        const data = event.match(/^data: (.+)$/m)?.[1];
        if (!type || !data) continue;
        const payload = JSON.parse(data);
        if (type === "assistant.message") {
          setMessages((current) => [...current, { id: run.run_id, role: "assistant", mode: "auto", text: payload.answer, citations: payload.citations }]);
        }
        if (type === "extraction.completed") {
          const results = payload.results ?? [];
          const requiresConfirmation = results.some((item: NonNullable<AgentMessage["results"]>[number]) => item.requires_human_confirmation);
          setMessages((current) => [...current, {
            id: run.run_id,
            role: "assistant",
            mode: "extraction",
            text: requiresConfirmation ? "Extraction needs contract-type confirmation." : "Contract extraction completed.",
            results,
          }]);
        }
        if (type === "run.failed") setError(payload.message ?? "Agent run failed");
      }
    }
  }

  async function runTask(runText: string, runAttachment: File | null) {
    const trimmed = runText.trim();
    if (!trimmed && !runAttachment) return;
    setError("");
    setBusy(true);
    const userMessage = runAttachment ? `${runAttachment.name}${trimmed ? ` — ${trimmed}` : ""}` : trimmed;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", mode: "auto", text: userMessage }]);
    try {
      const conversation = await ensureConversation();
      const form = new FormData();
      form.append("text", trimmed);
      if (runAttachment) form.append("file", runAttachment);
      const run = await api(`/agent/conversations/${conversation}/tasks`, { method: "POST", body: form });
      await stream(run);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Agent request failed");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed && !attachment) return;
    if (busy) {
      // The agent is busy - hold this message and send it when the run finishes.
      setQueued((current) => [...current, trimmed]);
      setText("");
      return;
    }
    const runAttachment = attachment;
    setText("");
    setAttachment(null);
    void runTask(trimmed, runAttachment);
  }

  return (
    <section className="reader-section agent-section">
      <div className="agent-chat-heading">
        <div>
          <span className="eyebrow">Agent workspace</span>
          <h3>Contract agent</h3>
        </div>
        <div className="agent-head-actions">
          {busy && (
            <span className="agent-thinking-tag">
              <span className="agent-spinner" /> Thinking
            </span>
          )}
          {(messages.length > 0 || queued.length > 0) && (
            <button type="button" className="agent-newchat" onClick={resetChat}>
              + New chat
            </button>
          )}
        </div>
      </div>

      <div className="chat-thread" aria-live="polite">
        {messages.length === 0 && !busy && (
          <p className="chat-empty-hint">
            Ask about your contracts, or describe a task. Attach a PDF/JSON/CSV to include an extraction.
          </p>
        )}

        {messages.map((message) => (
          <div key={message.id} className={`chat-row ${message.role === "user" ? "chat-row-user" : "chat-row-agent"}`}>
            <div
              className={`chat-bubble ${
                message.role === "user"
                  ? "chat-bubble-user"
                  : message.mode === "extraction"
                  ? "chat-bubble-agent"
                  : "chat-bubble-final"
              }`}
            >
              {message.role === "user" ? (
                <p>{message.text}</p>
              ) : (
                <div className="chat-answer">{renderAnswer(message.text, contractsById, onOpenContract)}</div>
              )}
              {message.citations
                ?.filter((citation) => contractsById.has(citation.contract_id))
                .map((citation) => (
                  <span key={`${citation.contract_id}-${citation.label}`} className="chat-sub">
                    <button
                      type="button"
                      className="contract-link"
                      onClick={() => onOpenContract(citation.contract_id)}
                    >
                      {contractsById.get(citation.contract_id)?.title}
                    </button>
                    {citation.evidence ? ` — ${citation.evidence}` : ""}
                  </span>
                ))}
              {message.results?.map((result, index) => (
                <span key={`${result.contract_id ?? "confirmation"}-${index}`} className="chat-sub">
                  {result.requires_human_confirmation ? (
                    "Human confirmation required"
                  ) : result.contract_id && contractsById.has(result.contract_id) ? (
                    <>
                      <button
                        type="button"
                        className="contract-link"
                        onClick={() => onOpenContract(result.contract_id!)}
                      >
                        {contractsById.get(result.contract_id)?.title}
                      </button>
                      {` — ${result.lifecycle_status}`}
                    </>
                  ) : (
                    `${result.contract_id ?? "contract"} — ${result.lifecycle_status}`
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}

        {busy && (
          <div className="chat-row chat-row-agent">
            <div className="chat-bubble chat-bubble-agent chat-bubble-typing">
              <span className="agent-spinner" />
              <p>Thinking</p>
            </div>
          </div>
        )}

        {queued.map((queuedText, index) => (
          <div key={`queued-${index}`} className="chat-row chat-row-user">
            <div className="chat-bubble chat-bubble-user chat-bubble-queued">
              {queuedText}
              <span className="bubble-tag">queued — sends when the agent is free</span>
            </div>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      <form className="chat-composer" onSubmit={submit}>
        <button
          type="button"
          className={`chat-attach ${attachment ? "has-file" : ""}`}
          onClick={() => fileInput.current?.click()}
          title={attachment ? attachment.name : "Attach a contract"}
        >
          <Paperclip size={15} />
          {attachment && <span className="chat-attach-name">{attachment.name}</span>}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.json,.csv"
          hidden
          onChange={(event) => setAttachment(event.target.files?.[0] ?? null)}
        />
        <input
          type="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Ask about your contracts, or describe a task…"
        />
        <button type="submit" className="chat-send" aria-label="Send">
          <Send size={15} />
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function AgentWorkspaceDrawer({
  onClose,
  contracts,
  onOpenContract,
}: {
  onClose: () => void;
  contracts: Contract[];
  onOpenContract: (id: string) => void;
}) {
  return (
    <aside className="reader agent-drawer">
      <button className="close" aria-label="Close agent workspace" onClick={onClose}>
        <X size={19} />
      </button>
      <div className="reader-header">
        <span className="eyebrow">Agent workspace</span>
        <h2>Contract agent</h2>
        <p className="muted">Ask about your contracts or describe a task — the agent plans and runs the steps.</p>
      </div>
      <AgentChat contracts={contracts} onOpenContract={onOpenContract} />
    </aside>
  );
}

function ContractReader({
  contract,
  busy,
  onClose,
  onAction,
  onReview,
  onDownload,
}: {
  contract: Contract;
  busy: boolean;
  onClose: () => void;
  onAction: (action: string) => void;
  onReview: () => void;
  onDownload: () => void;
}) {
  return (
    <aside className="reader">
      <button
        className="close"
        aria-label="Close contract reader"
        onClick={onClose}
      >
        <X size={19} />
      </button>
      <div className="reader-header">
        <span className="eyebrow">Contract reader</span>
        <h2>{contract.title}</h2>
        <p className="muted">
          {contract.contract_number} ·{" "}
          {contract.contract_type ?? "Unclassified"}
        </p>
        <div className="reader-actions">
          <span className="detail-status">
            {contract.lifecycle_status.replaceAll("_", " ")}
          </span>
          <button className="secondary" onClick={onDownload}>
            <Download size={16} /> Download source
          </button>
        </div>
      </div>
      <section className="reader-section">
        <h3>
          Parties <small>{contract.parties?.length ?? 0}</small>
        </h3>
        {contract.parties?.map((party) => (
          <div className="reader-item" key={party.legal_name}>
            <strong>{party.legal_name}</strong>
            <span>{party.roles?.join(", ") || "other"}</span>
          </div>
        ))}
      </section>
      <section className="reader-section">
        <h3>
          Clauses <small>{contract.clauses?.length ?? 0}</small>
        </h3>
        {contract.clauses?.map((clause) => (
          <article
            className="content-block"
            key={`${clause.heading}-${clause.page_location}`}
          >
            <strong>{clause.heading}</strong>
            <span>
              {clause.clause_type} · {clause.page_location}
            </span>
            <p>{clause.text}</p>
          </article>
        ))}
      </section>
      <section className="reader-section">
        <h3>Workflow</h3>
        <div className="actions">
          <button className="secondary" disabled={busy} onClick={onReview}>
            Record approved review
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => onAction("submit_for_review")}
          >
            Submit for review
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => onAction("approve")}
          >
            Approve
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => onAction("activate")}
          >
            Activate
          </button>
        </div>
      </section>
    </aside>
  );
}

function ClauseLibrary({
  role,
  onClose,
}: {
  role: string;
  onClose: () => void;
}) {
  const [templates, setTemplates] = useState<ClauseTemplate[]>([]);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [notice, setNotice] = useState("");
  async function refresh() {
    setTemplates(await api("/clause-templates"));
  }
  useEffect(() => {
    refresh().catch((cause) =>
      setNotice(
        cause instanceof Error ? cause.message : "Unable to load library",
      ),
    );
  }, []);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    try {
      await api("/clause-templates", {
        method: "POST",
        body: JSON.stringify({ name, text, clause_type: "general_provision" }),
      });
      setName("");
      setText("");
      setNotice("Draft template created.");
      await refresh();
    } catch (cause) {
      setNotice(
        cause instanceof Error ? cause.message : "Unable to create template",
      );
    }
  }
  async function update(id: string, path: string, body: object) {
    try {
      await api(`/clause-templates/${id}/${path}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setNotice("Template updated.");
      await refresh();
    } catch (cause) {
      setNotice(
        cause instanceof Error ? cause.message : "Template update failed",
      );
    }
  }
  return (
    <aside className="reader library-drawer">
      <button
        className="close"
        aria-label="Close clause library"
        onClick={onClose}
      >
        <X size={19} />
      </button>
      <span className="eyebrow">Clause governance</span>
      <h2>Clause library</h2>
      <p className="muted">
        Manage versioned clauses before they are copied into a contract.
      </p>
      {(role === "admin" || role === "contract_manager") && (
        <form className="create-form" onSubmit={create}>
          <label>
            Template name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Data protection"
              required
            />
          </label>
          <label>
            Clause text
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={4}
              placeholder="Approved clause wording"
              required
            />
          </label>
          <button className="primary">
            <Plus size={17} /> Create draft template
          </button>
        </form>
      )}
      {notice && <p className="notice">{notice}</p>}
      <div className="template-list">
        {templates.map((template) => (
          <article className="template-card" key={template.id}>
            <div>
              <strong>{template.name}</strong>
              <span>
                {template.status} · v{template.current_version} ·{" "}
                {template.organization_id ? "Organization" : "Global"}
              </span>
            </div>
            <p>{template.text}</p>
            {template.status === "draft" &&
              (role === "admin" || role === "contract_manager") && (
                <button
                  className="secondary"
                  onClick={() => update(template.id, "submit", {})}
                >
                  Submit for review
                </button>
              )}
            {template.status === "in_review" &&
              (role === "admin" || role === "clause_reviewer") && (
                <div className="template-actions">
                  <button
                    className="secondary"
                    onClick={() =>
                      update(template.id, "review", { decision: "approved" })
                    }
                  >
                    Approve
                  </button>
                  <button
                    className="secondary"
                    onClick={() =>
                      update(template.id, "review", { decision: "archived" })
                    }
                  >
                    Archive
                  </button>
                </div>
              )}
          </article>
        ))}
      </div>
    </aside>
  );
}

function Workspace({
  principal,
  onLogout,
}: {
  principal: Principal;
  onLogout: () => void;
}) {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Contract | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    refresh();
  }, []);
  async function refresh() {
    setContracts(await api("/contracts").catch(() => []));
  }
  async function openContract(contract: Contract) {
    setSelected(await api(`/contracts/${contract.id}`));
  }
  async function upload(file: File) {
    setBusy(true);
    setNotice("Extracting contract...");
    try {
      const form = new FormData();
      form.append("file", file);
      await api("/contracts/upload", { method: "POST", body: form });
      await refresh();
      setNotice("Contract extracted and added.");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  async function action(actionName: string) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await api(`/contracts/${selected.id}/actions`, {
        method: "POST",
        body: JSON.stringify({ action: actionName }),
      });
      setSelected(updated);
      await refresh();
      setNotice(`${actionName.replaceAll("_", " ")} completed.`);
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }
  async function review() {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await api(`/contracts/${selected.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          decision: "approved",
          comments: "Reviewed in portal",
        }),
      });
      setSelected(updated);
      await refresh();
      setNotice("Review recorded.");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }
  const visible = contracts.filter((contract) =>
    `${contract.title} ${contract.contract_number}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <div className="shell">
      <header>
        <div className="brand">
          CLM<span>·</span>
        </div>
        <div className="header-actions">
          <button className="ghost" onClick={() => setAgentOpen(true)}>
            <Bot size={17} /> Agent
          </button>
          <button className="ghost" onClick={() => setLibraryOpen(true)}>
            Clause library
          </button>
          <span>{principal.organization_id}</span>
          <button className="ghost" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="workspace">
        <div className="heading">
          <div>
            <span className="eyebrow">Contract workspace</span>
            <h1>Agreements, in motion.</h1>
            <p className="muted">
              Create governed drafts, upload extractions, and move agreements
              through review.
            </p>
          </div>
          <div className="heading-actions">
            <button className="secondary" onClick={() => setAgentOpen(true)}>
              <Bot size={17} /> Open agent
            </button>
            <button className="secondary" onClick={() => setCreateOpen(true)}>
              <Plus size={17} /> Create draft
            </button>
            <button
              className="primary"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={17} /> Upload contract
            </button>
          </div>
        </div>
        <input
          ref={fileInput}
          hidden
          type="file"
          accept=".pdf,.json,.csv"
          onChange={(event) =>
            event.target.files?.[0] && upload(event.target.files[0])
          }
        />
        {notice && <p className="notice">{notice}</p>}
        <section className="metrics">
          <div>
            <span>Visible contracts</span>
            <strong>{contracts.length}</strong>
          </div>
          <div>
            <span>Needs review</span>
            <strong>
              {
                contracts.filter(
                  (item) => item.lifecycle_status === "in_review",
                ).length
              }
            </strong>
          </div>
          <div>
            <span>Active</span>
            <strong>
              {
                contracts.filter((item) => item.lifecycle_status === "active")
                  .length
              }
            </strong>
          </div>
        </section>
        <section className="records">
          <div className="records-heading">
            <div>
              <h2>Recent agreements</h2>
              <p className="muted">
                Select a contract to read clauses and manage workflow.
              </p>
            </div>
            <label className="search">
              <Search size={17} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search contracts"
              />
            </label>
          </div>
          {visible.length === 0 ? (
            <div className="empty">
              <FileText size={28} />
              <strong>No contracts to show</strong>
              <span>Create a draft or upload an extraction to begin.</span>
            </div>
          ) : (
            visible.map((contract) => (
              <button
                className="record"
                key={contract.id}
                onClick={() => openContract(contract)}
              >
                <FileText size={20} />
                <div>
                  <strong>{contract.title}</strong>
                  <span>
                    {contract.contract_number} ·{" "}
                    {contract.contract_type ?? "Unclassified"}
                  </span>
                </div>
                <b>{contract.lifecycle_status.replaceAll("_", " ")}</b>
              </button>
            ))
          )}
        </section>
      </main>
      {createOpen && (
        <CreateDraftForm
          busy={busy}
          onClose={() => setCreateOpen(false)}
          onCreated={(contract) => {
            setCreateOpen(false);
            setSelected(contract);
            refresh();
            setNotice(
              "Draft created. Submit it for review from the contract reader.",
            );
          }}
        />
      )}
      {libraryOpen && (
        <ClauseLibrary
          role={principal.role}
          onClose={() => setLibraryOpen(false)}
        />
      )}
      {!agentOpen && (
        <button className="agent-fab" onClick={() => setAgentOpen(true)} aria-label="Open the contract agent">
          <Sparkles size={18} /> Ask the agent
        </button>
      )}
      {agentOpen && (
        <AgentWorkspaceDrawer
          onClose={() => setAgentOpen(false)}
          contracts={contracts}
          onOpenContract={(id) => {
            const match = contracts.find((item) => item.id === id);
            if (match) openContract(match);
          }}
        />
      )}
      {selected && (
        <ContractReader
          contract={selected}
          busy={busy}
          onClose={() => setSelected(null)}
          onAction={action}
          onReview={review}
          onDownload={() => downloadSource(selected)}
        />
      )}
    </div>
  );
}

export default function App() {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  if (!principal) return <Login onLogin={setPrincipal} />;
  return (
    <Workspace
      principal={principal}
      onLogout={() => {
        sessionStorage.removeItem("clm_access_token");
        setPrincipal(null);
      }}
    />
  );
}
