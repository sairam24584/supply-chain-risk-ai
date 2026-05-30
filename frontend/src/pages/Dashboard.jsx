import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Boxes, Factory, Truck, TrendingUp, AlertTriangle, MapPin,
  Activity, DollarSign, ShieldAlert, ArrowRight,
} from "lucide-react";
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import StatCard from "../components/StatCard.jsx";
import Spinner from "../components/Spinner.jsx";
import { dashboardApi, intelligenceApi } from "../api/client.js";

const SEVERITY_COLORS = { high: "#dc2626", medium: "#f59e0b", low: "#16a34a" };
const STOCK_COLORS    = { stockout_risk: "#dc2626", overstock: "#f59e0b", healthy: "#16a34a" };

export default function Dashboard() {
  const [data, setData]         = useState(null);
  const [anomaly, setAnomaly]   = useState(null);
  const [regions, setRegions]   = useState(null);
  const [error, setError]       = useState(null);

  useEffect(() => {
    Promise.all([
      dashboardApi.summary(),
      intelligenceApi.anomalies().catch(() => null),
      intelligenceApi.regions().catch(() => null),
    ])
      .then(([d, a, r]) => { setData(d); setAnomaly(a); setRegions(r); })
      .catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed to load: {error}</div>;
  if (!data) return <Spinner label="Loading dashboard…" />;

  const sevData   = Object.entries(data.severity_breakdown).map(([k, v]) => ({ name: k, value: v }));
  const stockData = Object.entries(data.stock_status_breakdown).map(([k, v]) => ({ name: k, value: v }));
  const delayData = Object.entries(data.delay_status_breakdown).map(([k, v]) => ({ name: k.replace("_", " "), value: v }));

  const hotspot = regions?.hotspot;
  const topRegion = regions?.top_disrupted?.[0];

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="card-hero">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-3">
            <div className="section-title text-brand-700">Live state of the supply chain</div>
            <h2 className="text-2xl font-bold text-ink-900 tracking-tight leading-snug">
              {data.high_severity_pct}% of SKUs are high severity
              {hotspot && <> · concentrated in <span className="text-brand-700">{hotspot}</span></>}
            </h2>
            <p className="text-sm text-ink-600 max-w-2xl">
              {anomaly?.total_anomalies != null && (
                <>{anomaly.total_anomalies} multivariate anomalies detected by IsolationForest. </>
              )}
              {data.stock_status_breakdown.stockout_risk || 0} SKUs at stockout risk.{" "}
              Average defect rate {data.avg_defect_rate}% across {data.suppliers} suppliers.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <Link to="/query" className="btn-primary">
                Ask the multi-agent system <ArrowRight size={14} className="ml-1.5" />
              </Link>
              <Link to="/anomalies" className="btn-secondary">View anomalies</Link>
              <Link to="/regions" className="btn-secondary">Region breakdown</Link>
            </div>
          </div>
          <div className="hidden md:flex flex-col items-end gap-2">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-800 flex items-center justify-center shadow-glow">
              <ShieldAlert size={28} className="text-white" />
            </div>
          </div>
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total SKUs"      value={data.total_skus}                              icon={Boxes} />
        <StatCard label="Suppliers"       value={data.suppliers}                               icon={Factory} />
        <StatCard
          label="High severity"
          value={`${data.high_severity_pct}%`}
          sub={`${data.severity_breakdown.high || 0} SKUs`}
          accent="red"
          icon={AlertTriangle}
        />
        <StatCard
          label="Avg defect rate"
          value={`${data.avg_defect_rate}%`}
          accent="amber"
          icon={Activity}
        />
        <StatCard
          label="Anomalies"
          value={anomaly?.total_anomalies ?? "—"}
          sub={anomaly ? `${(anomaly.anomaly_rate * 100).toFixed(0)}% rate (IsolationForest)` : "—"}
          accent="red"
          icon={TrendingUp}
        />
        <StatCard
          label="Hotspot region"
          value={hotspot || "—"}
          sub={topRegion ? `Disruption index ${topRegion.disruption_index?.toFixed?.(2)}` : "—"}
          accent="brand"
          icon={MapPin}
        />
        <StatCard
          label="Stockouts"
          value={data.stock_status_breakdown.stockout_risk || 0}
          sub="below safety stock"
          accent="red"
          icon={Boxes}
        />
        <StatCard
          label="Revenue"
          value={`$${(data.total_revenue / 1000).toFixed(0)}k`}
          sub={`Logistics $${(data.total_logistics_cost / 1000).toFixed(1)}k`}
          accent="emerald"
          icon={DollarSign}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <PieCard title="Severity mix" data={sevData} colors={SEVERITY_COLORS} />
        <PieCard title="Stock status" data={stockData} colors={STOCK_COLORS} />
        <BarCard title="Delivery status" data={delayData} />
      </div>

      {/* Inspection */}
      <div className="card">
        <h3 className="section-title mb-3">Inspection outcomes</h3>
        <div className="grid grid-cols-3 gap-4">
          {Object.entries(data.inspection_breakdown).map(([k, v]) => {
            const accent =
              k === "Fail" ? "border-red-100 text-red-700" :
              k === "Pending" ? "border-amber-100 text-amber-700" :
              "border-emerald-100 text-emerald-700";
            return (
              <div key={k} className={`rounded-xl border ${accent} bg-white p-4`}>
                <div className="section-title">{k}</div>
                <div className="text-2xl font-bold text-ink-900 mt-1">{v}</div>
                <div className="text-xs text-ink-500 mt-0.5">
                  {((v / data.total_skus) * 100).toFixed(0)}% of total
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function PieCard({ title, data, colors }) {
  return (
    <div className="card">
      <h3 className="section-title mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={78} paddingAngle={2}>
            {data.map((d) => (
              <Cell key={d.name} fill={colors[d.name] || "#94a3b8"} stroke="white" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0", boxShadow: "0 8px 24px -8px rgba(13,27,77,.15)" }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-2 justify-center text-xs">
        {data.map((d) => (
          <span key={d.name} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: colors[d.name] || "#94a3b8" }} />
            <span className="text-ink-600">{d.name.replace("_"," ")}: <b>{d.value}</b></span>
          </span>
        ))}
      </div>
    </div>
  );
}

function BarCard({ title, data }) {
  return (
    <div className="card">
      <h3 className="section-title mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={11} tickLine={false} axisLine={{ stroke: "#cbd5e1" }} />
          <YAxis fontSize={11} tickLine={false} axisLine={{ stroke: "#cbd5e1" }} />
          <Tooltip
            cursor={{ fill: "rgba(53,99,255,0.05)" }}
            contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0" }}
          />
          <Bar dataKey="value" fill="#1d44f0" radius={[8, 8, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
