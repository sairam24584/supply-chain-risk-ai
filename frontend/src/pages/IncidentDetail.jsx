import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import Spinner from "../components/Spinner.jsx";
import RiskBadge from "../components/RiskBadge.jsx";
import { riskApi, intelligenceApi } from "../api/client.js";

const FIELD_GROUPS = [
  { title: "Identity",
    fields: ["SKU", "Product type", "Supplier name", "Location"] },
  { title: "Risk Signals",
    fields: ["risk_severity", "stock_status", "delay_status", "defect_severity", "Inspection results"] },
  { title: "Inventory",
    fields: ["Stock levels", "Order quantities", "Number of products sold", "Production volumes"] },
  { title: "Shipping",
    fields: [
      "Shipping carriers", "Transportation modes", "Routes",
      "Shipping times", "Lead time", "Manufacturing lead time",
    ] },
  { title: "Quality & Financials",
    fields: ["Defect rates", "Price", "Revenue generated", "Manufacturing costs", "Shipping costs", "Costs"] },
];

export default function IncidentDetail() {
  const { sku } = useParams();
  const [rec, setRec] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    riskApi.incident(sku).then(setRec).catch((e) => setError(e.userMessage || e.message));
    intelligenceApi.forecast(sku).then(setForecast).catch(() => null);
  }, [sku]);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!rec) return <Spinner label={`Loading ${sku}…`} />;

  return (
    <div className="space-y-5 max-w-5xl">
      <Link to="/inventory" className="btn-ghost">
        <ArrowLeft size={14} className="mr-1" /> Back to inventory
      </Link>

      <div className="card-hero">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="section-title">SKU detail</div>
            <h2 className="text-2xl font-bold text-ink-900 tracking-tight">{rec.SKU}</h2>
            <p className="text-sm text-ink-600 mt-1">
              {rec["Product type"]} · {rec["Supplier name"]} · {rec["Location"]}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 justify-end">
            <RiskBadge value={rec.risk_severity} />
            <RiskBadge value={rec.stock_status} />
            <RiskBadge value={rec.delay_status} />
            <RiskBadge value={rec["Inspection results"]} />
          </div>
        </div>
      </div>

      {forecast && (
        <div className="card">
          <h3 className="section-title mb-3">Forecast & stockout prediction</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Daily velocity" value={`${forecast.daily_velocity} u/d`} />
            <Stat label="30-day forecast" value={`${forecast.forecast_units} u`} />
            <Stat label="Days to stockout" value={forecast.days_to_stockout ?? "∞"} />
            <Stat label="Urgency" value={<RiskBadge value={forecast.urgency === "critical" ? "high" : forecast.urgency === "high" ? "medium" : "low"} />} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {FIELD_GROUPS.map((g) => (
          <div key={g.title} className="card">
            <h3 className="section-title mb-3">{g.title}</h3>
            <dl className="space-y-2 text-sm">
              {g.fields.map((f) => (
                <div key={f} className="flex justify-between gap-3 border-b border-ink-100 last:border-0 pb-1.5 last:pb-0">
                  <dt className="text-ink-500">{f}</dt>
                  <dd className="text-ink-900 font-medium text-right truncate max-w-[60%]">
                    {formatValue(rec[f])}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl border border-ink-100 bg-ink-50/40 p-3">
      <div className="section-title">{label}</div>
      <div className="text-lg font-bold text-ink-900 mt-1">{value}</div>
    </div>
  );
}

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toFixed(2);
  }
  return String(v);
}
