import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  MessageSquareText,
  Factory,
  Truck,
  Boxes,
  ShieldAlert,
  Activity,
  Map,
  Plus,
  Clock,
  Wrench,
  Sparkles,
  Database,
} from "lucide-react";

const TOOLS = [
  { to: "/dashboard", label: "Dashboard",       icon: LayoutDashboard },
  { to: "/anomalies", label: "Anomalies",       icon: Activity },
  { to: "/regions",   label: "Regions",         icon: Map },
  { to: "/suppliers", label: "Supplier risk",   icon: Factory },
  { to: "/shipments", label: "Shipment risk",   icon: Truck },
  { to: "/inventory", label: "Inventory risk",  icon: Boxes },
  { to: "/data",      label: "Data sources",    icon: Database },
];

const RECENTS_KEY = "scri.recents";
const MAX_RECENTS = 8;

export function pushRecent(query) {
  if (!query) return;
  try {
    const cur = JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]");
    const next = [
      { q: query, ts: Date.now() },
      ...cur.filter((r) => r.q !== query),
    ].slice(0, MAX_RECENTS);
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event("recents-changed"));
  } catch {
    /* ignore */
  }
}

export function clearRecents() {
  localStorage.removeItem(RECENTS_KEY);
  window.dispatchEvent(new Event("recents-changed"));
}

function useRecents() {
  const [recents, setRecents] = useState(() => {
    try { return JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]"); }
    catch { return []; }
  });
  useEffect(() => {
    const refresh = () => {
      try { setRecents(JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]")); }
      catch { setRecents([]); }
    };
    window.addEventListener("recents-changed", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("recents-changed", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);
  return recents;
}

export default function Layout({ children }) {
  const navigate = useNavigate();
  const loc = useLocation();
  const recents = useRecents();

  const startNewQuery = () => {
    // Tell Query Console to clear its thread, then navigate.
    window.dispatchEvent(new Event("new-query"));
    navigate("/query");
  };

  return (
    <div className="min-h-screen flex bg-white">
      {/* Sidebar — light, AI-assistant style */}
      <aside className="w-[268px] shrink-0 flex flex-col border-r border-ink-100 bg-white">
        {/* Brand */}
        <div className="px-4 pt-4 pb-3 flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
            <ShieldAlert size={16} className="text-white" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-sm text-ink-900 truncate">Supply Chain</div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400 -mt-0.5">
              Risk Intelligence
            </div>
          </div>
        </div>

        {/* + New query */}
        <div className="px-3 pb-3">
          <button
            onClick={startNewQuery}
            className="w-full inline-flex items-center gap-2 rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm font-medium text-ink-800 hover:bg-ink-50 hover:border-ink-300 shadow-card transition"
          >
            <Plus size={15} className="text-brand-600" />
            New query
          </button>
        </div>

        {/* Recents */}
        <div className="px-3 pb-3 flex-1 overflow-y-auto">
          <div className="px-1 pt-1 pb-2 flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-[0.14em] font-semibold text-ink-400">
              Recent
            </span>
            {recents.length > 0 && (
              <button
                onClick={clearRecents}
                className="text-[10px] text-ink-400 hover:text-ink-700"
              >
                clear
              </button>
            )}
          </div>
          {recents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-200 px-3 py-4 text-xs text-ink-400 leading-relaxed">
              Your recent queries will appear here.
            </div>
          ) : (
            <div className="space-y-0.5">
              {recents.map((r) => (
                <button
                  key={r.ts}
                  onClick={() => {
                    window.dispatchEvent(
                      new CustomEvent("rerun-query", { detail: r.q })
                    );
                    navigate("/query");
                  }}
                  className="w-full text-left flex items-start gap-2 px-2.5 py-2 rounded-lg text-[13px] text-ink-700 hover:bg-ink-50 transition"
                  title={r.q}
                >
                  <Clock size={13} className="mt-0.5 text-ink-400 shrink-0" />
                  <span className="line-clamp-2 leading-snug">{r.q}</span>
                </button>
              ))}
            </div>
          )}

          {/* Tools */}
          <div className="mt-5">
            <div className="px-1 pt-1 pb-1 flex items-center gap-1.5">
              <Wrench size={11} className="text-ink-400" />
              <span className="text-[10px] uppercase tracking-[0.14em] font-semibold text-ink-400">
                Tools
              </span>
            </div>
            <div className="space-y-0.5 pt-1">
              {TOOLS.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition ${
                      isActive
                        ? "bg-brand-50 text-brand-700"
                        : "text-ink-700 hover:bg-ink-50"
                    }`
                  }
                >
                  <Icon size={15} className="opacity-80" />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-ink-100">
          <div className="text-[11px] text-ink-500 flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            connected
          </div>
          <div className="text-[10px] text-ink-400 mt-0.5">v0.2.0 · Multi-agent RAG</div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#fbfbfc]">
        <header className="border-b border-ink-100 bg-white/70 backdrop-blur supports-[backdrop-filter]:bg-white/60 px-8 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={14} className="text-brand-500" />
            <span className="text-sm text-ink-500">
              {loc.pathname.startsWith("/query") || loc.pathname === "/"
                ? "Ask anything about your supply chain"
                : breadcrumb(loc.pathname)}
            </span>
          </div>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-ink-500 hover:text-ink-900 transition"
          >
            API docs ↗
          </a>
        </header>

        <main className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full animate-fade-in">{children}</div>
        </main>
      </div>
    </div>
  );
}

function breadcrumb(path) {
  const titles = {
    "/dashboard": "Dashboard",
    "/anomalies": "Anomalies — IsolationForest",
    "/regions":   "Cross-region disruption analysis",
    "/suppliers": "Supplier risk",
    "/shipments": "Shipment risk",
    "/inventory": "Inventory risk",
  };
  if (path.startsWith("/incident/")) return "Incident detail";
  return titles[path] || "Overview";
}
