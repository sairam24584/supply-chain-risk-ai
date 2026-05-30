import { useEffect, useRef, useState } from "react";
import {
  Send, AlertTriangle, Sparkles, GitBranch, ShieldCheck, User, Loader2, Zap,
  ThumbsUp, ThumbsDown,
} from "lucide-react";
import AgentCard from "../components/AgentCard.jsx";
import RiskBadge from "../components/RiskBadge.jsx";
import { queryApi, feedbackApi, resetThread } from "../api/client.js";
import { pushRecent } from "../components/Layout.jsx";

const SAMPLE_QUERIES = [
  "Which suppliers are creating the most quality risk?",
  "Are there shipment routes with chronic delays we should re-route?",
  "Which SKUs are at imminent stockout risk and what do we do?",
  "Recommend a mitigation plan for the highest severity incidents.",
];

export default function QueryConsole() {
  const [query, setQuery] = useState("");
  const [thread, setThread] = useState([]);   // [{role, content/data}]
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Listen for sidebar events
  useEffect(() => {
    const onNew = () => {
      setThread([]);
      setQuery("");
      resetThread();         // new conversation memory thread on the backend
      inputRef.current?.focus();
    };
    const onRerun = (e) => { setQuery(e.detail || ""); inputRef.current?.focus(); };
    window.addEventListener("new-query", onNew);
    window.addEventListener("rerun-query", onRerun);
    return () => {
      window.removeEventListener("new-query", onNew);
      window.removeEventListener("rerun-query", onRerun);
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread, loading]);

  async function submit(e) {
    e?.preventDefault();
    const q = query.trim();
    if (!q || loading) return;
    setLoading(true);
    setThread((t) => [...t, { role: "user", content: q }]);
    setQuery("");
    try {
      const data = await queryApi.ask({ query: q, top_k: 8 });
      setThread((t) => [...t, { role: "assistant", data }]);
      pushRecent(q);
    } catch (err) {
      setThread((t) => [
        ...t,
        { role: "assistant", error: err.userMessage || err.message || "Request failed" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const empty = thread.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Scrollable thread / welcome */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {empty && <Welcome onPick={(s) => setQuery(s)} />}

          {thread.map((m, i) =>
            m.role === "user" ? (
              <UserMessage key={i} text={m.content} />
            ) : m.error ? (
              <ErrorMessage key={i} text={m.error} />
            ) : (
              <AssistantMessage
                key={i}
                data={m.data}
                query={thread[i - 1]?.content || ""}
              />
            )
          )}

          {loading && <LoadingMessage />}

          <div ref={endRef} />
        </div>
      </div>

      {/* Sticky input bar */}
      <div className="border-t border-ink-100 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <form
            onSubmit={submit}
            className="flex items-end gap-2 rounded-2xl border border-ink-200 bg-white shadow-soft p-2 focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-100 transition"
          >
            <textarea
              ref={inputRef}
              rows={1}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit(e);
                }
              }}
              placeholder="Ask about suppliers, shipments, inventory…"
              className="flex-1 resize-none bg-transparent border-0 outline-none px-3 py-2 text-sm placeholder:text-ink-400 max-h-40"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="shrink-0 inline-flex items-center justify-center h-10 w-10 rounded-xl bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
              aria-label="Send"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={15} />}
            </button>
          </form>
          <p className="text-[11px] text-ink-400 text-center mt-2">
            Multi-agent pipeline: Retrieve → Supplier · Shipment · Inventory → Recommend → Judge
          </p>
        </div>
      </div>
    </div>
  );
}

/* -------------------- MESSAGE COMPONENTS -------------------- */

function Welcome({ onPick }) {
  return (
    <div className="text-center py-12">
      <div className="inline-flex h-12 w-12 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 items-center justify-center shadow-glow mb-4">
        <Sparkles size={22} className="text-white" />
      </div>
      <h1 className="text-2xl font-bold text-ink-900 tracking-tight">
        How can I help you today?
      </h1>
      <p className="text-sm text-ink-500 mt-2 max-w-md mx-auto">
        I analyze your supply chain risks across suppliers, shipments and
        inventory using a multi-agent RAG pipeline grounded in your incident data.
      </p>
      <div className="mt-6 flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
        {SAMPLE_QUERIES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="text-xs px-3 py-2 rounded-xl border border-ink-200 bg-white text-ink-700 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700 transition text-left max-w-xs"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function UserMessage({ text }) {
  return (
    <div className="flex justify-end mb-4">
      <div className="flex items-start gap-2 max-w-[85%]">
        <div className="rounded-2xl bg-brand-600 text-white text-sm leading-relaxed px-4 py-2.5 shadow-soft">
          {text}
        </div>
        <div className="h-7 w-7 rounded-full bg-ink-200 flex items-center justify-center shrink-0 mt-0.5">
          <User size={14} className="text-ink-600" />
        </div>
      </div>
    </div>
  );
}

function ErrorMessage({ text }) {
  return (
    <div className="flex items-start gap-3 mb-6">
      <AgentAvatar />
      <div className="flex-1 rounded-2xl border border-red-200 bg-red-50 px-4 py-3">
        <div className="flex items-center gap-2 text-red-700 text-sm font-semibold">
          <AlertTriangle size={14} /> {text}
        </div>
      </div>
    </div>
  );
}

function LoadingMessage() {
  return (
    <div className="flex items-start gap-3 mb-6">
      <AgentAvatar />
      <div className="flex-1">
        <div className="flex items-center gap-2 text-ink-500 text-sm">
          <Loader2 size={14} className="animate-spin text-brand-500" />
          Running the multi-agent pipeline…
        </div>
        <div className="mt-3 text-xs text-ink-400 space-y-1">
          <Step label="Hybrid retrieval (Chroma + BM25 → RRF → rerank)" />
          <Step label="Supplier / Shipment / Inventory agents in parallel" />
          <Step label="Recommendation Agent synthesises a plan" />
          <Step label="Quality Judge scores the output" />
        </div>
      </div>
    </div>
  );
}

function Step({ label }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-1 w-1 rounded-full bg-ink-300" />
      {label}
    </div>
  );
}

function AgentAvatar() {
  return (
    <div className="h-7 w-7 rounded-full bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shrink-0 mt-0.5">
      <Sparkles size={13} className="text-white" />
    </div>
  );
}

function FeedbackBar({ query }) {
  const [voted, setVoted] = useState(null); // +1 | -1 | null

  async function handleVote(v) {
    if (voted !== null) return;
    try {
      await feedbackApi.vote(query, v);
      setVoted(v);
    } catch {
      // silently ignore
    }
  }

  return (
    <div className="flex items-center gap-2 pt-1">
      <span className="text-[11px] text-ink-400">Was this helpful?</span>
      <button
        onClick={() => handleVote(1)}
        disabled={voted !== null}
        title="Thumbs up"
        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs border transition
          ${voted === 1
            ? "bg-emerald-50 border-emerald-200 text-emerald-700"
            : "border-ink-200 text-ink-500 hover:border-emerald-300 hover:text-emerald-600 disabled:opacity-50"
          }`}
      >
        <ThumbsUp size={11} /> {voted === 1 ? "Thanks!" : "Yes"}
      </button>
      <button
        onClick={() => handleVote(-1)}
        disabled={voted !== null}
        title="Thumbs down"
        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs border transition
          ${voted === -1
            ? "bg-red-50 border-red-200 text-red-700"
            : "border-ink-200 text-ink-500 hover:border-red-300 hover:text-red-600 disabled:opacity-50"
          }`}
      >
        <ThumbsDown size={11} /> No
      </button>
    </div>
  );
}

function AssistantMessage({ data, query }) {
  const score = data.risk_score ?? null;
  const plan = data.recommendation_plan;
  const judge = data.judge_verdict;
  const scoreColor =
    score == null   ? "text-ink-500" :
    score >= 7      ? "text-red-600" :
    score >= 4      ? "text-amber-600" :
                      "text-emerald-600";

  return (
    <div className="flex items-start gap-3 mb-6">
      <AgentAvatar />
      <div className="flex-1 min-w-0 space-y-4">

        {/* Headline + risk score */}
        <div>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-ink-900">Recommendation</h3>
              {data.cache_hit && (
                <span
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-emerald-100"
                  title={data.cache_type === "semantic" ?
                    `Semantic match · sim ${data.cache_match?.similarity} · "${data.cache_match?.matched_query}"` :
                    `Exact cache · cached at ${new Date((data.cached_at || 0) * 1000).toLocaleTimeString()}`}
                >
                  <Zap size={10} /> {data.cache_type === "semantic" ? "semantic cache" : "cached"}
                </span>
              )}
              {data.intent && (
                <span className="inline-flex items-center rounded-md bg-brand-50 text-brand-700 px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-brand-100">
                  intent: {data.intent.replace(/_/g, " ")} ({Math.round((data.intent_confidence || 0) * 100)}%)
                </span>
              )}
              {data.attempts > 1 && (
                <span className="inline-flex items-center rounded-md bg-amber-50 text-amber-700 px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-amber-100">
                  retried {data.attempts}×
                </span>
              )}
            </div>
            <div className={`text-right ${scoreColor}`}>
              <div className="text-[10px] uppercase tracking-wider font-semibold">Risk score</div>
              <div className="text-2xl font-extrabold leading-none">
                {score ?? "—"}<span className="text-sm font-bold">/10</span>
              </div>
            </div>
          </div>
        </div>

        {plan && plan.actions?.length > 0 ? (
          <>
            <p className="text-sm text-ink-800 leading-relaxed">{plan.executive_summary}</p>
            <ol className="space-y-2">
              {plan.actions.map((a, i) => (
                <li
                  key={i}
                  className="rounded-xl border border-ink-100 bg-white px-3.5 py-3 hover:border-ink-200 transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="text-sm font-semibold text-ink-900">
                        {i + 1}. {a.title}
                      </div>
                      <div className="mt-1 text-xs text-ink-500">
                        <span className="text-ink-400">Owner</span> <b className="text-ink-700">{a.owner_role}</b>
                        <span className="mx-1.5 text-ink-300">·</span>
                        <span className="text-ink-400">Timeframe</span> <b className="text-ink-700">{a.timeframe_days}d</b>
                        <span className="mx-1.5 text-ink-300">·</span>
                        <span className="text-ink-400">Driver</span> <span className="italic text-ink-600">{a.driver}</span>
                      </div>
                    </div>
                    <PriorityChip priority={a.priority} />
                  </div>
                </li>
              ))}
            </ol>
            <div className="text-xs text-ink-500 space-y-1.5 pt-1">
              <div><b className="text-ink-700">Risk justification.</b> {plan.risk_score_justification}</div>
              <div><b className="text-ink-700">Reasoning trail.</b> {plan.reasoning_trail}</div>
            </div>
          </>
        ) : (
          <pre className="text-sm whitespace-pre-wrap text-ink-700 font-sans leading-relaxed">
            {data.answer}
          </pre>
        )}

        {/* Judge */}
        {judge && (
          <div className="rounded-xl border border-brand-100 bg-brand-50/40 px-3.5 py-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-ink-900">
                <ShieldCheck size={13} className="text-brand-600" /> Quality Judge
              </div>
              <div className="flex items-center gap-2">
                <div className="h-1 w-24 rounded-full bg-ink-100 overflow-hidden">
                  <div
                    className={`h-full ${judge.overall_quality >= 0.7 ? "bg-emerald-500" : judge.overall_quality >= 0.4 ? "bg-amber-500" : "bg-red-500"}`}
                    style={{ width: `${(judge.overall_quality * 100).toFixed(0)}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-ink-900">
                  {(judge.overall_quality * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
              <Check label="actionable"    ok={judge.actionable} />
              <Check label="grounded"      ok={judge.grounded} />
              <Check label="prioritised"   ok={judge.prioritised} />
              <Check label="score justified" ok={judge.score_justified} />
            </div>
            <p className="text-[11px] text-ink-600 italic mt-2 leading-relaxed">{judge.rationale}</p>
          </div>
        )}

        {/* Escalations */}
        {data.escalations?.length > 0 && (
          <div className="rounded-xl border border-red-200 bg-red-50/60 px-3.5 py-3">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-red-800 mb-2">
              <GitBranch size={13} /> A2A escalations · {data.escalations.length}
            </div>
            <ul className="space-y-1">
              {data.escalations.map((e, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2 text-xs text-ink-800">
                  <span className="badge-soft-red">{e.agent}</span>
                  <RiskBadge value={e.severity} />
                  <span className="text-ink-700">— {e.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Per-agent findings */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <AgentCard agent="supplier"  text={data.findings?.supplier} />
          <AgentCard agent="shipment"  text={data.findings?.shipment} />
          <AgentCard agent="inventory" text={data.findings?.inventory} />
        </div>

        {/* Final report (Report Agent) */}
        {data.final_report?.body && (
          <details className="rounded-xl border border-ink-100 bg-white px-3.5 py-3" open>
            <summary className="cursor-pointer text-xs font-semibold text-ink-900">
              Report — {data.final_report.title}
            </summary>
            <div className="mt-2 text-sm text-ink-800 whitespace-pre-wrap leading-relaxed">
              {data.final_report.body}
            </div>
            {data.final_report.next_steps?.length > 0 && (
              <ul className="mt-3 list-disc pl-5 text-xs text-ink-700 space-y-1">
                {data.final_report.next_steps.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            )}
          </details>
        )}

        {/* Sources collapsible */}
        <SourcesCollapsible sources={data.sources || []} />

        {/* Guardrails + trail */}
        {data.guardrail_violations?.length > 0 && (
          <div className="text-[11px] text-ink-500">
            <span className="text-ink-400 mr-1">guardrails:</span>
            {data.guardrail_violations.map((v, i) => (
              <span key={i} className="mr-1 badge-soft-ink">{v}</span>
            ))}
          </div>
        )}
        <div className="text-[11px] text-ink-400">
          {data.agents_invoked?.join(" → ")}
        </div>

        {/* Feedback */}
        {query && <FeedbackBar query={query} />}
      </div>
    </div>
  );
}

function PriorityChip({ priority }) {
  const map = {
    1: { c: "bg-red-100 text-red-700",     l: "P1" },
    2: { c: "bg-amber-100 text-amber-700", l: "P2" },
    3: { c: "bg-ink-100 text-ink-700",     l: "P3" },
  };
  const m = map[priority] || map[3];
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold ${m.c}`}>{m.l}</span>;
}

function Check({ label, ok }) {
  return (
    <span className={`inline-flex items-center gap-1 ${ok ? "text-emerald-700" : "text-red-700"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      {label}
    </span>
  );
}

function SourcesCollapsible({ sources }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="border border-ink-100 rounded-xl bg-white overflow-hidden">
      <button
        onClick={() => setOpen((x) => !x)}
        className="w-full text-left px-3.5 py-2 flex items-center justify-between text-xs text-ink-600 hover:bg-ink-50 transition"
      >
        <span>Retrieved sources · {sources.length}</span>
        <span className="text-ink-400">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-ink-100">
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Supplier</th>
                <th>Location</th>
                <th>Severity</th>
                <th className="text-right">RRF</th>
                <th className="text-right">Rerank</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id}>
                  <td className="font-mono text-brand-700">{s.metadata?.sku}</td>
                  <td>{s.metadata?.supplier}</td>
                  <td>{s.metadata?.location}</td>
                  <td><RiskBadge value={s.metadata?.risk_severity} /></td>
                  <td className="text-right text-ink-500 font-mono text-xs">
                    {s.rrf_score?.toFixed(4) || "—"}
                  </td>
                  <td className="text-right text-ink-500 font-mono text-xs">
                    {s.rerank_score?.toFixed(2) || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
