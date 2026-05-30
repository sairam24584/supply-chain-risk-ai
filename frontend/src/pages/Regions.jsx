import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import Spinner from "../components/Spinner.jsx";
import StatCard from "../components/StatCard.jsx";
import { intelligenceApi } from "../api/client.js";

export default function Regions() {
  const [data, setData] = useState(null);
  const [corr, setCorr] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([intelligenceApi.regions(), intelligenceApi.correlations()])
      .then(([r, c]) => {
        setData(r);
        setCorr(c);
      })
      .catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!data || !corr) return <Spinner label="Aggregating cross-region risk…" />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Regions" value={data.total_regions} />
        <StatCard label="Hotspot" value={data.hotspot || "—"} accent="red" />
        <StatCard
          label="Top disruption index"
          value={data.top_disrupted[0]?.disruption_index?.toFixed(2) ?? "—"}
          accent="amber"
        />
      </div>

      <div className="card">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">
          Disruption index by region
        </h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data.top_disrupted} margin={{ left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="Location" fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Bar dataKey="disruption_index" fill="#dc2626" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-slate-500 mt-2">
          disruption_index = 1.5·high_severity + 1.2·fail_inspections + delayed + 1.3·stockout_risk + anomalies
        </p>
      </div>

      <div className="card overflow-x-auto">
        <h3 className="text-sm font-semibold text-slate-900 mb-2">Region breakdown</h3>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 uppercase border-b border-slate-200">
            <tr>
              <th className="text-left py-2 pr-3">Region</th>
              <th className="text-right py-2 pr-3">SKUs</th>
              <th className="text-right py-2 pr-3">Suppliers</th>
              <th className="text-right py-2 pr-3">Avg defect</th>
              <th className="text-right py-2 pr-3">Fails</th>
              <th className="text-right py-2 pr-3">High sev</th>
              <th className="text-right py-2 pr-3">Delayed</th>
              <th className="text-right py-2 pr-3">Stockouts</th>
              <th className="text-right py-2 pr-3">Anomalies</th>
              <th className="text-right py-2 pr-3">Disruption</th>
            </tr>
          </thead>
          <tbody>
            {data.top_disrupted.map((r) => (
              <tr key={r.Location} className="border-b border-slate-100">
                <td className="py-2 pr-3 font-medium">{r.Location}</td>
                <td className="py-2 pr-3 text-right">{r.skus}</td>
                <td className="py-2 pr-3 text-right">{r.suppliers}</td>
                <td className="py-2 pr-3 text-right">{r.avg_defect_rate.toFixed(2)}</td>
                <td className="py-2 pr-3 text-right text-red-600">{r.fail_inspections}</td>
                <td className="py-2 pr-3 text-right">{r.high_severity}</td>
                <td className="py-2 pr-3 text-right text-amber-600">{r.delayed}</td>
                <td className="py-2 pr-3 text-right">{r.stockout_risk}</td>
                <td className="py-2 pr-3 text-right">{r.anomalies}</td>
                <td className="py-2 pr-3 text-right font-semibold">{r.disruption_index.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Top numeric correlations</h3>
          <table className="w-full text-sm">
            <tbody>
              {corr.numeric.slice(0, 8).map((c, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1.5 pr-3 text-slate-600">{c.a} ↔ {c.b}</td>
                  <td className="py-1.5 pr-3 text-right font-mono font-semibold">
                    <span className={Math.abs(c.pearson) >= 0.3 ? "text-red-600" : "text-slate-600"}>
                      {c.pearson > 0 ? "+" : ""}{c.pearson.toFixed(3)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Categorical associations (Cramér's V)</h3>
          <table className="w-full text-sm">
            <tbody>
              {corr.categorical.map((c, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1.5 pr-3 text-slate-600">{c.a} ↔ {c.b}</td>
                  <td className="py-1.5 pr-3 text-right font-mono font-semibold">
                    <span className={c.cramers_v >= 0.3 ? "text-red-600" : "text-slate-600"}>
                      {c.cramers_v.toFixed(3)}
                    </span>
                    <span className="ml-2 text-xs text-slate-400">p={c.p_value}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
