import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Spinner from "../components/Spinner.jsx";
import StatCard from "../components/StatCard.jsx";
import RiskBadge from "../components/RiskBadge.jsx";
import { intelligenceApi } from "../api/client.js";

export default function Anomalies() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    intelligenceApi.anomalies().then(setData).catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!data) return <Spinner label="Detecting anomalies…" />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Anomalies detected" value={data.total_anomalies} accent="red" />
        <StatCard label="Anomaly rate" value={`${(data.anomaly_rate * 100).toFixed(0)}%`} accent="amber" />
        <StatCard label="Contamination" value={data.contamination} sub="IsolationForest" />
        <StatCard label="Features used" value={data.features_used.length} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Anomalies by Supplier</h3>
          <ul className="text-sm divide-y divide-slate-100">
            {Object.entries(data.by_supplier).map(([k, v]) => (
              <li key={k} className="flex justify-between py-1.5">
                <span>{k}</span>
                <span className="font-semibold text-red-600">{v}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Anomalies by Region</h3>
          <ul className="text-sm divide-y divide-slate-100">
            {Object.entries(data.by_region).map(([k, v]) => (
              <li key={k} className="flex justify-between py-1.5">
                <span>{k}</span>
                <span className="font-semibold text-red-600">{v}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">Top Anomalous Incidents</h3>
        <p className="text-xs text-slate-500 mb-2">
          Detected by IsolationForest over [{data.features_used.join(", ")}]. Higher score = more anomalous.
        </p>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 uppercase border-b border-slate-200">
            <tr>
              <th className="text-left py-2 pr-3">SKU</th>
              <th className="text-left py-2 pr-3">Product</th>
              <th className="text-left py-2 pr-3">Supplier</th>
              <th className="text-left py-2 pr-3">Location</th>
              <th className="text-right py-2 pr-3">Defect %</th>
              <th className="text-right py-2 pr-3">Lead</th>
              <th className="text-right py-2 pr-3">Ship</th>
              <th className="text-right py-2 pr-3">Cost</th>
              <th className="text-right py-2 pr-3">Anomaly Score</th>
              <th className="text-left py-2 pr-3">Sev</th>
            </tr>
          </thead>
          <tbody>
            {data.top_anomalies.map((r) => (
              <tr key={r.sku} className="border-b border-slate-100">
                <td className="py-2 pr-3">
                  <Link to={`/incident/${r.sku}`} className="font-mono text-brand-700 hover:underline">
                    {r.sku}
                  </Link>
                </td>
                <td className="py-2 pr-3 capitalize">{r.product_type}</td>
                <td className="py-2 pr-3">{r.supplier}</td>
                <td className="py-2 pr-3">{r.location}</td>
                <td className="py-2 pr-3 text-right">{r.defect_rate.toFixed(2)}</td>
                <td className="py-2 pr-3 text-right">{r.lead_time}</td>
                <td className="py-2 pr-3 text-right">{r.shipping_time}</td>
                <td className="py-2 pr-3 text-right">${r.total_cost.toFixed(0)}</td>
                <td className="py-2 pr-3 text-right font-semibold text-red-600">
                  {r.anomaly_score.toFixed(3)}
                </td>
                <td className="py-2 pr-3"><RiskBadge value={r.risk_severity} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
