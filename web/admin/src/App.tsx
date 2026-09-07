import { useCallback, useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "https://localhost:8443";
const TOKEN_KEY = "clm_admin_token";

type Principal = { subject: string; organization_id: string; role: string };
type Run = { id: string; conversation_id: string; mode: string; status: string; created_at: string; completed_at?: string };
type RunDetail = Run & {
  result?: unknown;
  error?: { code?: string; message?: string } | null;
  events: { id: number; event_type: string; payload: Record<string, unknown> }[];
  conversation: { id: string; role: string; mode: string; text: string; attachment?: { filename?: string } | null }[];
};
type DebugStep = {
  step: number;
  agent: string;
  phase: string;
  model?: string;
  provider?: string;
  system_prompt?: string;
  context?: unknown;
  output?: unknown;
  output_raw?: string;
  reasoning?: string;
  memory?: unknown;
  retrieval?: unknown;
  ms?: number | null;
  note?: string;
  ts?: string;
};
type ExtractionTrace = { contract_id: string; created_at: string; events: Record<string, unknown>[] };

async function api<T = unknown>(path: string): Promise<T> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `Request failed (${response.status})`);
  return response.json();
}

const pretty = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value, null, 2));
const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : "-");

function Login({ onLogin }: { onLogin: (principal: Principal) => void }) {
  const [email, setEmail] = useState("admin@capstone.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch(`${API_URL}/auth/token`, {
        method: "POST",
        body: new URLSearchParams({ grant_type: "password", username: email, password }),
      });
      if (!response.ok) throw new Error("Invalid email or password");
      sessionStorage.setItem(TOKEN_KEY, (await response.json()).access_token);
      const me = await api<Principal>("/me");
      if (me.role !== "admin") {
        sessionStorage.removeItem(TOKEN_KEY);
        throw new Error("This console requires an organization admin account.");
      }
      onLogin(me);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in");
    }
  }
  return (
    <main className="login">
      <form onSubmit={submit}>
        <span className="kicker">Agent observability</span>
        <h1>CLM Agent Console</h1>
        <p className="muted">Inspect every agent run: prompts, context, reasoning, memory, retrieval, and timing.</p>
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit">Sign in</button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}

function Block({ label, value }: { label: string; value: unknown }) {
  if (value == null || value === "") return null;
  return (
    <div className="block">
      <span className="block-label">{label}</span>
      <pre>{pretty(value)}</pre>
    </div>
  );
}

function RunView({ runId }: { runId: string }) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [steps, setSteps] = useState<DebugStep[]>([]);
  const [tab, setTab] = useState<"timeline" | "memory" | "trace">("trace");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setDetail(null);
    setSteps([]);
    setError("");
    const load = () => {
      Promise.all([api<RunDetail>(`/agent-admin/runs/${runId}`), api<{ steps: DebugStep[] }>(`/agent-admin/runs/${runId}/debug`)])
        .then(([d, s]) => {
          if (!active) return;
          setDetail(d);
          setSteps(s.steps ?? []);
          if (d.status === "running" || d.status === "queued") timer = setTimeout(load, 4000);
        })
        .catch((cause) => active && setError(cause instanceof Error ? cause.message : "Unable to load run"));
    };
    load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [runId]);

  if (error) return <p className="error">{error}</p>;
  if (!detail) return <p className="muted">Loading run…</p>;

  const contextStep = steps.find((s) => s.phase === "context");
  const memorySteps = steps.filter((s) => s.memory != null);

  return (
    <div className="run">
      <div className="run-head">
        <h2>{detail.mode} run</h2>
        <span className={`status status-${detail.status}`}>{detail.status}</span>
        <span className="muted">{when(detail.created_at)} → {when(detail.completed_at)}</span>
      </div>
      {detail.error && <p className="error">{detail.error.code}: {detail.error.message}</p>}

      <nav className="tabs">
        <button className={tab === "trace" ? "on" : ""} onClick={() => setTab("trace")}>Full trace <em>{steps.length}</em></button>
        <button className={tab === "memory" ? "on" : ""} onClick={() => setTab("memory")}>Memory</button>
        <button className={tab === "timeline" ? "on" : ""} onClick={() => setTab("timeline")}>Timeline <em>{detail.events.length}</em></button>
      </nav>

      {tab === "timeline" && (
        <div className="timeline">
          {detail.events.map((event) => (
            <div className="event" key={event.id}>
              <strong>{event.event_type}</strong>
              <pre>{pretty(event.payload)}</pre>
            </div>
          ))}
        </div>
      )}

      {tab === "memory" && (
        <div className="memory">
          <h3>Episodic — conversation the run could see</h3>
          <div className="turns">
            {detail.conversation.map((m) => (
              <div className="turn" key={m.id}>
                <strong>{m.role} · {m.mode}</strong>
                <span>{m.text || m.attachment?.filename || "(attachment)"}</span>
              </div>
            ))}
          </div>
          <Block label="context assembled at the start of the run" value={contextStep?.context} />
          <h3>Working — per-step snapshots (discarded after the run)</h3>
          {memorySteps.length === 0 && <p className="muted">No working-memory snapshots recorded.</p>}
          {memorySteps.map((s) => (
            <Block key={`m-${s.step}`} label={`${s.phase} · step ${s.step}`} value={s.memory} />
          ))}
        </div>
      )}

      {tab === "trace" && (
        <div className="trace">
          {steps.length === 0 && <p className="muted">No debug trace was recorded for this run.</p>}
          {steps.map((s) => (
            <details className="step" key={s.step} open={Boolean(s.system_prompt)}>
              <summary>
                <strong>{s.step}. {s.phase}</strong>
                <span>{s.agent}{s.model ? ` · ${s.model}` : ""}{s.ms != null ? ` · ${s.ms} ms` : ""}{s.note ? ` · ${s.note}` : ""}</span>
              </summary>
              <Block label="system prompt" value={s.system_prompt} />
              <Block label="context sent" value={s.context} />
              <Block label="reasoning" value={s.reasoning} />
              <Block label="parsed output" value={s.output} />
              <Block label="retrieval" value={s.retrieval} />
              <Block label="memory snapshot" value={s.memory} />
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function Console({ principal, onLogout }: { principal: Principal; onLogout: () => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [traces, setTraces] = useState<ExtractionTrace[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [view, setView] = useState<"runs" | "extractions">("runs");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    Promise.all([api<Run[]>("/agent-admin/runs"), api<ExtractionTrace[]>("/agent-admin/extraction-traces")])
      .then(([r, t]) => {
        setRuns(r);
        setTraces(t);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load agent data"));
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <div className="shell">
      <header>
        <div className="brand">CLM Agent Console</div>
        <div className="spacer" />
        <button className="ghost" onClick={refresh}>Refresh</button>
        <span className="muted">{principal.organization_id}</span>
        <button className="ghost" onClick={onLogout}>Sign out</button>
      </header>
      {error && <p className="error banner">{error}</p>}
      <nav className="view-switch">
        <button className={view === "runs" ? "on" : ""} onClick={() => setView("runs")}>Agent runs <em>{runs.length}</em></button>
        <button className={view === "extractions" ? "on" : ""} onClick={() => setView("extractions")}>Extraction traces <em>{traces.length}</em></button>
      </nav>

      {view === "runs" && (
        <div className="split">
          <aside className="list">
            {runs.length === 0 && <p className="muted">No agent runs yet.</p>}
            {runs.map((run) => (
              <button key={run.id} className={selected === run.id ? "row on" : "row"} onClick={() => setSelected(run.id)}>
                <span className="row-mode">{run.mode}</span>
                <span className={`status status-${run.status}`}>{run.status}</span>
                <span className="row-time">{when(run.created_at)}</span>
              </button>
            ))}
          </aside>
          <main className="detail">
            {selected ? <RunView runId={selected} /> : <p className="muted">Select a run to inspect its full trace.</p>}
          </main>
        </div>
      )}

      {view === "extractions" && (
        <main className="detail wide">
          {traces.length === 0 && <p className="muted">No extraction traces yet.</p>}
          {traces.map((trace) => (
            <details className="step" key={trace.contract_id}>
              <summary>
                <strong>{trace.contract_id}</strong>
                <span>{trace.events.length} events · {when(trace.created_at)}</span>
              </summary>
              <Block label="trace" value={trace.events} />
            </details>
          ))}
        </main>
      )}
    </div>
  );
}

export default function App() {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  useEffect(() => {
    if (sessionStorage.getItem(TOKEN_KEY))
      api<Principal>("/me")
        .then((me) => (me.role === "admin" ? setPrincipal(me) : sessionStorage.removeItem(TOKEN_KEY)))
        .catch(() => sessionStorage.removeItem(TOKEN_KEY));
  }, []);
  if (!principal) return <Login onLogin={setPrincipal} />;
  return (
    <Console
      principal={principal}
      onLogout={() => {
        sessionStorage.removeItem(TOKEN_KEY);
        setPrincipal(null);
      }}
    />
  );
}
