import { useEffect, useState } from "react";
import {
  X, Activity, ShieldCheck, Zap, Bell, RefreshCw, CheckCircle, AlertCircle,
} from "lucide-react";
import api from "../api/client.js";

function fetchAll() {
  return Promise.allSettled([
    api.get("/api/health"),
    api.get("/api/alerts/summary"),
    api.get("/api/cache/stats"),
    api.get("/api/eval/results"),
  ]);
}

function val(result) {
  return result.status === "fulfilled" ? result.value?.data : null;
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-ink-100 last:border-0">
      <span className="text-xs text-ink-500">{label}</span>
      <span className="text-xs font-semibold text-ink-900">{children}</span>
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={13} className="text-brand-500" />
        <span className="text-[11px] uppercase tracking-wider font-semibold text-ink-500">{title}</span>
      </div>
      <div className="rounded-xl border border-ink-100 bg-white px-3.5 py-1">
        {children}
      </div>
    </div>
  );
}

export default function StatusPanel({ onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState(null);

  const load = async () => {
    setLoading(true);
    const [health, alerts, cache, evalRes] = await fetchAll();
    setData({ health: val(health), alerts: val(alerts), cache: val(cache), eval: val(evalRes) });
    setRefreshedAt(new Date());
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const health = data?.health;
  const alerts = data?.alerts;
  const cache = data?.cache;
  const evalData = data?.eval;

  const isOnline = health?.status === "ok";

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/20 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <aside className="w-80 bg-[#fbfbfc] border-l border-ink-200 shadow-2xl flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-100 bg-white">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${isOnline ? "bg-emerald-500 animate-pulse" : "bg-red-400"}`} />
            <span className="text-sm font-semibold text-ink-900">System Status</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              disabled={loading}
              className="p-1.5 rounded-lg hover:bg-ink-100 transition text-ink-500 disabled:opacity-40"
              title="Refresh"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-ink-100 transition text-ink-500">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">

          {/* Health */}
          <Section title="Backend" icon={Activity}>
            <Row label="Status">
              <span className={`flex items-center gap-1 ${isOnline ? "text-emerald-600" : "text-red-600"}`}>
                {isOnline
                  ? <><CheckCircle size={11} /> online</>
                  : <><AlertCircle size={11} /> offline</>}
              </span>
            </Row>
            <Row label="Service">{health?.service ?? "—"}</Row>
            <Row label="Version">{health?.version ?? "—"}</Row>
          </Section>

          {/* Alerts */}
          <Section title="Active Alerts" icon={Bell}>
            <Row label="Total alerts">{alerts?.total ?? "—"}</Row>
            <Row label="Supplier">{alerts?.by_category?.supplier ?? 0}</Row>
            <Row label="Shipment">{alerts?.by_category?.shipment ?? 0}</Row>
            <Row label="Inventory">{alerts?.by_category?.inventory ?? 0}</Row>
            <Row label="Anomaly">{alerts?.by_category?.anomaly ?? 0}</Row>
            {alerts?.by_severity && (
              <Row label="High / Medium">
                <span className="text-red-600">{alerts.by_severity.high ?? 0}</span>
                <span className="text-ink-400 mx-1">/</span>
                <span className="text-amber-600">{alerts.by_severity.medium ?? 0}</span>
              </Row>
            )}
          </Section>

          {/* Cache */}
          <Section title="Query Cache" icon={Zap}>
            <Row label="Exact hits">{cache?.exact?.hits ?? "—"}</Row>
            <Row label="Exact misses">{cache?.exact?.misses ?? "—"}</Row>
            <Row label="Semantic hits">{cache?.semantic?.hits ?? "—"}</Row>
            <Row label="Semantic entries">{cache?.semantic?.size ?? "—"}</Row>
          </Section>

          {/* Eval scores */}
          <Section title="DeepEval Scores" icon={ShieldCheck}>
            {evalData ? (
              <>
                <Row label="Cases run">{evalData.num_cases ?? "—"}</Row>
                {evalData.metrics_summary &&
                  Object.entries(evalData.metrics_summary).map(([k, v]) => (
                    <Row key={k} label={k}>
                      <span className={v >= 0.7 ? "text-emerald-600" : v >= 0.4 ? "text-amber-600" : "text-red-600"}>
                        {typeof v === "number" ? (v * 100).toFixed(0) + "%" : v}
                      </span>
                    </Row>
                  ))}
                <Row label="Last run">
                  {evalData.run_at
                    ? new Date(evalData.run_at).toLocaleDateString()
                    : "never"}
                </Row>
              </>
            ) : (
              <Row label="Status">
                <span className="text-ink-400 text-xs italic">no eval results yet</span>
              </Row>
            )}
          </Section>
        </div>

        {/* Footer */}
        {refreshedAt && (
          <div className="px-5 py-2.5 border-t border-ink-100 text-[11px] text-ink-400">
            Refreshed {refreshedAt.toLocaleTimeString()}
          </div>
        )}
      </aside>
    </div>
  );
}
