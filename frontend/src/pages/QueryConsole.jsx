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

const THREAD_KEY = "scri.thread";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Strip metadata suffixes and prompt-template leakage from agent finding text. */
function cleanFinding(text) {
  if (!text || text.includes("did not run") || text.includes("agent unavailable")) return null;
  let s = text
    .replace(/\s*\[(severity|escalated|entities|citations)[^\]]*\]/gi, "")
    .replace(/\s*Cite\s+[^.]+\.\s*Include citations\..*$/si, "")
    .replace(/\s*Operations question:.*$/si, "")
    .replace(/\s*Retrieved incident context:.*$/si, "")
    .trim();
  if (s.length > 500) s = s.slice(0, 500).replace(/\s+\S*$/, "") + "…";
  return s || null;
}

/** Return the most relevant agent finding to show as the primary answer. */
function getPrimaryFinding(data) {
  const f = data.findings || {};
  const intent = data.intent || "";
  const order = {
    supplier_quality:   ["supplier", "shipment", "inventory"],
    shipment_logistics: ["shipment", "supplier", "inventory"],
    inventory_demand:   ["inventory", "supplier", "shipment"],
  }[intent] || ["supplier", "shipment", "inventory"];
  for (const key of order) {
    const cleaned = cleanFinding(f[key]);
    if (cleaned) return cleaned;
  }
  return null;
}

export default function QueryConsole() {
  const [query, setQuery] = useState("");
  // Restore thread from sessionStorage so navigation away & back preserves history
  const [thread, setThread] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(THREAD_KEY) || "[]"); }
    catch { return []; }
  });
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Persist thread to sessionStorage on every change (max 20 messages)
  useEffect(() => {
    try {
      sessionStorage.setItem(THREAD_KEY, JSON.stringify(thread.slice(-20)));
    } catch { /* quota — ignore */ }
  }, [thread]);

  // Listen for sidebar events
  useEffect(() => {
    const onNew = () => {
      setThread([]);
      setQuery("");
      resetThread();
      sessionStorage.removeItem(THREAD_KEY);
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
      // Extract friendly message from API error response when available.
      const apiDetail = err.response?.data;
      let errorMsg;
      if (apiDetail?.violations?.includes("out_of_scope")) {
        errorMsg = "I'm focused on supply chain operations. Try asking about suppliers, shipments, or inventory risks.";
      } else if (apiDetail?.message) {
        errorMsg = apiDetail.message;
      } else {
        errorMsg = err.userMessage || err.message || "Request failed — please try again.";
      }
      setThread((t) => [...t, { role: "assistant", error: errorMsg }]);
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

const CAPABILITY_CHIPS = [
  { emoji: "🏭", label: "Supplier risk" },
  { emoji: "🚚", label: "Shipment delays" },
  { emoji: "📦", label: "Inventory stockouts" },
  { emoji: "⚠️", label: "Anomaly detection" },
];

function Welcome({ onPick }) {
  return (
    <div className="py-10 max-w-2xl mx-auto">
      {/* Hero */}
      <div className="text-center mb-8">
        <div className="inline-flex h-14 w-14 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 items-center justify-center shadow-glow mb-5">
          <Sparkles size={26} className="text-white" />
        </div>
        <h1 className="text-2xl font-bold text-ink-900 tracking-tight">
          Supply Chain Risk Intelligence
        </h1>
        <p className="text-sm text-ink-500 mt-2 leading-relaxed">
          Ask anything about your operational data — I'll retrieve historical incidents,
          analyse risks across suppliers, shipments and inventory, and recommend actions.
        </p>
      </div>

      {/* Capability chips */}
      <div className="flex flex-wrap justify-center gap-2 mb-7">
        {CAPABILITY_CHIPS.map(({ emoji, label }) => (
          <span
            key={label}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-ink-200 bg-white text-xs text-ink-600 font-medium"
          >
            {emoji} {label}
          </span>
        ))}
      </div>

      {/* Sample queries */}
      <p className="text-[11px] uppercase tracking-wider font-semibold text-ink-400 text-center mb-3">
        Try asking
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {SAMPLE_QUERIES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="text-left text-sm px-4 py-3 rounded-xl border border-ink-200 bg-white text-ink-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 transition leading-snug"
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
  const isScope = text?.includes("supply chain") || text?.includes("suppliers");
  return (
    <div className="flex items-start gap-3 mb-5">
      <AgentAvatar />
      <div className={`flex-1 rounded-2xl border px-4 py-3 ${
        isScope
          ? "border-ink-200 bg-ink-50"
          : "border-red-200 bg-red-50"
      }`}>
        <div className={`flex items-center gap-2 text-sm ${isScope ? "text-ink-700" : "text-red-700 font-semibold"}`}>
          {!isScope && <AlertTriangle size={14} />} {text}
        </div>
      </div>
    </div>
  );
}

const PIPELINE_STEPS = [
  { label: "Retrieving relevant incidents…",         ms: 1800 },
  { label: "Analysing supplier, shipment & inventory risk…", ms: 3500 },
  { label: "Synthesising recommendations…",          ms: 2000 },
  { label: "Quality-judging the output…",            ms: 1200 },
];

function LoadingMessage() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timers = [];
    let acc = 0;
    PIPELINE_STEPS.forEach((s, i) => {
      if (i === 0) return;
      acc += PIPELINE_STEPS[i - 1].ms;
      timers.push(setTimeout(() => setStep(i), acc));
    });
    return () => timers.forEach(clearTimeout);
  }, []);

  const pct = Math.round(((step + 1) / PIPELINE_STEPS.length) * 100);

  return (
    <div className="flex items-start gap-3 mb-6">
      <AgentAvatar />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-ink-600 text-sm font-medium">
          <Loader2 size={13} className="animate-spin text-brand-500 shrink-0" />
          {PIPELINE_STEPS[step].label}
        </div>
        {/* Progress bar */}
        <div className="mt-2.5 h-1 rounded-full bg-ink-100 overflow-hidden w-48">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-1.5 flex gap-3">
          {PIPELINE_STEPS.map((s, i) => (
            <span
              key={i}
              className={`text-[10px] transition-colors duration-300 ${
                i <= step ? "text-brand-600 font-medium" : "text-ink-300"
              }`}
            >
              {["Retrieve", "Analyse", "Recommend", "Judge"][i]}
            </span>
          ))}
        </div>
      </div>
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
  const [expanded, setExpanded] = useState(false);
  const score = data.risk_score ?? null;
  const plan = data.recommendation_plan;
  const judge = data.judge_verdict;
  const isGreeting = data.agents_invoked?.includes("greeting-handler") ||
                     data.agents_invoked?.includes("guardrail");

  const scoreColor =
    score == null   ? "text-ink-400" :
    score >= 7      ? "text-red-600"  :
    score >= 4      ? "text-amber-600":
                      "text-emerald-600";

  const TOP_N = 3;
  const actions = plan?.actions || [];
  const topActions = actions.slice(0, TOP_N);
  const moreCount = actions.length - TOP_N;

  // The direct factual answer from the specialist agent
  const directAnswer = !isGreeting ? getPrimaryFinding(data) : null;

  return (
    <div className="flex items-start gap-3 mb-5">
      <AgentAvatar />
      <div className="flex-1 min-w-0">

        {/* ── Meta badges ─────────────────────────────────────────── */}
        {!isGreeting && (data.cache_hit || data.intent) && (
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            {data.cache_hit && (
              <span
                className="inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-emerald-100"
                title={data.cache_type === "semantic" ? `Semantic match` : `Exact cache`}
              >
                <Zap size={10} /> {data.cache_type === "semantic" ? "semantic cache" : "cached"}
              </span>
            )}
            {data.intent && (
              <span className="inline-flex items-center rounded-md bg-ink-50 text-ink-500 px-1.5 py-0.5 text-[10px] ring-1 ring-ink-200">
                {data.intent.replace(/_/g, " ")} · {Math.round((data.intent_confidence || 0) * 100)}%
              </span>
            )}
            {data.attempts > 1 && (
              <span className="inline-flex items-center rounded-md bg-amber-50 text-amber-700 px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-amber-100">
                retried {data.attempts}×
              </span>
            )}
          </div>
        )}

        {/* ── Primary answer card ──────────────────────────────────── */}
        <div className="rounded-2xl border border-ink-100 bg-white px-4 py-3.5 shadow-card">

          {isGreeting ? (
            /* Greeting / out-of-scope: just show the answer text */
            <p className="text-sm text-ink-800 leading-relaxed whitespace-pre-line">{data.answer}</p>
          ) : (
            <>
              {/* Executive summary + risk score — primary answer */}
              {plan && (
                <div className="flex items-start justify-between gap-4 mb-3">
                  <p className="text-sm text-ink-900 leading-relaxed flex-1 font-medium">
                    {plan.executive_summary}
                  </p>
                  {score !== null && (
                    <div className={`shrink-0 text-right ${scoreColor}`}>
                      <div className="text-[9px] uppercase tracking-wider font-semibold opacity-70">Risk</div>
                      <div className="text-xl font-extrabold leading-none">
                        {score}<span className="text-xs font-bold">/10</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Fallback: specialist finding or raw answer */}
              {!plan && (
                <p className="text-sm text-ink-900 leading-relaxed font-medium">
                  {directAnswer || data.answer}
                </p>
              )}

              {/* Top actions */}
              {topActions.length > 0 && (
                <ol className="space-y-1.5 mt-1">
                  {topActions.map((a, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm">
                      <PriorityChip priority={a.priority} />
                      <div className="flex-1 min-w-0">
                        <span className="text-ink-900 font-medium">{a.title}</span>
                        <span className="text-ink-400 text-xs ml-2">
                          {a.owner_role} · {a.timeframe_days}d
                        </span>
                      </div>
                    </li>
                  ))}
                  {moreCount > 0 && !expanded && (
                    <li
                      className="text-xs text-brand-600 pl-1 cursor-pointer hover:underline"
                      onClick={() => setExpanded(true)}
                    >
                      + {moreCount} more action{moreCount > 1 ? "s" : ""}
                    </li>
                  )}
                </ol>
              )}

              {/* Expanded extra actions */}
              {expanded && actions.slice(TOP_N).map((a, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm mt-1.5">
                  <PriorityChip priority={a.priority} />
                  <div className="flex-1 min-w-0">
                    <span className="text-ink-900 font-medium">{a.title}</span>
                    <span className="text-ink-400 text-xs ml-2">
                      {a.owner_role} · {a.timeframe_days}d
                    </span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* ── Footer row ───────────────────────────────────────────── */}
        <div className="flex items-center gap-3 mt-2 flex-wrap">

          {/* Judge quality badge */}
          {judge && (
            <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full
              ${judge.overall_quality >= 0.7 ? "bg-emerald-50 text-emerald-700" :
                judge.overall_quality >= 0.4 ? "bg-amber-50 text-amber-700" :
                "bg-red-50 text-red-700"}`}>
              <ShieldCheck size={11} />
              Quality {Math.round(judge.overall_quality * 100)}%
            </span>
          )}

          {/* A2A escalation badge */}
          {data.escalations?.length > 0 && (
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-red-50 text-red-700">
              <GitBranch size={11} /> {data.escalations.length} escalation{data.escalations.length > 1 ? "s" : ""}
            </span>
          )}

          {/* Sources */}
          {data.sources?.length > 0 && (
            <SourcesCollapsible sources={data.sources} />
          )}

          {/* Full analysis toggle */}
          {!isGreeting && (plan || judge) && (
            <button
              onClick={() => setExpanded(x => !x)}
              className="text-[11px] text-brand-600 hover:underline ml-auto"
            >
              {expanded ? "Hide details ↑" : "Full analysis ↓"}
            </button>
          )}
        </div>

        {/* ── Expanded details ──────────────────────────────────────── */}
        {expanded && (
          <div className="mt-3 space-y-3">

            {/* Risk justification */}
            {plan?.risk_score_justification && (
              <p className="text-xs text-ink-600">
                <b className="text-ink-800">Justification:</b> {plan.risk_score_justification}
              </p>
            )}

            {/* Quality Judge */}
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
                  <Check label="actionable"     ok={judge.actionable} />
                  <Check label="grounded"       ok={judge.grounded} />
                  <Check label="prioritised"    ok={judge.prioritised} />
                  <Check label="score justified" ok={judge.score_justified} />
                </div>
                <p className="text-[11px] text-ink-600 italic mt-2 leading-relaxed">{judge.rationale}</p>
              </div>
            )}

            {/* A2A Escalations */}
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

            {/* Final report */}
            {data.final_report?.body && (
              <details className="rounded-xl border border-ink-100 bg-white px-3.5 py-3">
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

            {/* Agent trail */}
            <div className="text-[11px] text-ink-400">
              {data.agents_invoked?.join(" → ")}
            </div>
          </div>
        )}

        {/* Feedback */}
        {query && !isGreeting && <FeedbackBar query={query} />}
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
