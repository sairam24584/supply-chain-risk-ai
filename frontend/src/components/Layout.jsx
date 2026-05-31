import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Factory,
  Truck,
  Boxes,
  ShieldAlert,
  Activity,
  Map,
  Plus,
  Wrench,
  Sparkles,
  Database,
  BarChart2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import StatusPanel from "./StatusPanel.jsx";

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

export function useRecents() {
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
  const [showStatus, setShowStatus] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const startNewQuery = () => {
    window.dispatchEvent(new Event("new-query"));
    navigate("/query");
  };

  return (
    <div className="h-screen flex bg-white overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`shrink-0 flex flex-col border-r border-ink-100 bg-white transition-all duration-200 ${
          sidebarOpen ? "w-[268px]" : "w-14"
        }`}
      >
        {/* Brand + toggle */}
        <div className={`flex items-center border-b border-ink-100 ${sidebarOpen ? "px-4 pt-4 pb-3 gap-2.5" : "flex-col px-2 pt-3 pb-2 gap-2"}`}>
          <div className="h-8 w-8 shrink-0 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
            <ShieldAlert size={16} className="text-white" />
          </div>
          {sidebarOpen && (
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-sm text-ink-900 truncate">Supply Chain</div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400 -mt-0.5">
                Risk Intelligence
              </div>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(o => !o)}
            className="shrink-0 h-6 w-6 flex items-center justify-center rounded-md hover:bg-ink-100 text-ink-400 hover:text-ink-700 transition"
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {sidebarOpen ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>

        {/* + New query */}
        <div className={`${sidebarOpen ? "px-3" : "px-2"} py-3`}>
          <button
            onClick={startNewQuery}
            title="New query"
            className={`inline-flex items-center justify-center gap-2 rounded-xl border border-ink-200 bg-white text-sm font-medium text-ink-800 hover:bg-ink-50 hover:border-ink-300 shadow-card transition
              ${sidebarOpen ? "w-full px-3 py-2.5" : "w-full h-10"}`}
          >
            <Plus size={15} className="text-brand-600 shrink-0" />
            {sidebarOpen && "New query"}
          </button>
        </div>

        {/* Tools */}
        <div className={`${sidebarOpen ? "px-3" : "px-2"} pb-3 flex-1 overflow-y-auto`}>
          {sidebarOpen && (
            <div className="px-1 pt-1 pb-1 flex items-center gap-1.5">
              <Wrench size={11} className="text-ink-400" />
              <span className="text-[10px] uppercase tracking-[0.14em] font-semibold text-ink-400">
                Tools
              </span>
            </div>
          )}
          <div className={`${sidebarOpen ? "space-y-0.5 pt-1" : "space-y-1 pt-1"}`}>
            {TOOLS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                title={!sidebarOpen ? label : undefined}
                className={({ isActive }) =>
                  `flex items-center rounded-lg font-medium transition
                   ${sidebarOpen ? "gap-2.5 px-2.5 py-2 text-[13px]" : "justify-center h-10 w-full"}
                   ${isActive ? "bg-brand-50 text-brand-700" : "text-ink-700 hover:bg-ink-50"}`
                }
              >
                <Icon size={15} className="opacity-80 shrink-0" />
                {sidebarOpen && label}
              </NavLink>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className={`${sidebarOpen ? "px-4" : "px-2"} py-3 border-t border-ink-100`}>
          {sidebarOpen ? (
            <>
              <div className="text-[11px] text-ink-500 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                connected
              </div>
              <div className="text-[10px] text-ink-400 mt-0.5">v0.2.0 · Multi-agent RAG</div>
            </>
          ) : (
            <div className="flex justify-center">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </div>
          )}
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
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowStatus(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-xs font-medium text-ink-700 hover:bg-ink-50 hover:border-ink-300 shadow-card transition"
            >
              <BarChart2 size={13} className="text-brand-500" />
              Status
            </button>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-ink-500 hover:text-ink-900 transition"
            >
              API docs ↗
            </a>
          </div>
        </header>

        <main className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full animate-fade-in">{children}</div>
        </main>
      </div>

      {/* Status slide-over panel */}
      {showStatus && <StatusPanel onClose={() => setShowStatus(false)} />}
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
