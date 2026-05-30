import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import Spinner from "../components/Spinner.jsx";
import { riskApi } from "../api/client.js";

export default function SupplierRisk() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    riskApi.suppliers(10).then(setRows).catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!rows) return <Spinner label="Computing supplier risk…" />;

  return (
    <div className="space-y-6">
      <div className="card-elevated">
        <h3 className="section-title mb-3">Supplier Risk Index (top 10)</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={rows} layout="vertical" margin={{ left: 30 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis type="number" fontSize={11} tickLine={false} axisLine={{ stroke: "#cbd5e1" }} />
            <YAxis dataKey="supplier" type="category" fontSize={11} width={90}
                   tickLine={false} axisLine={{ stroke: "#cbd5e1" }} />
            <Tooltip
              cursor={{ fill: "rgba(220,38,38,0.05)" }}
              contentStyle={{ borderRadius: 12, border: "1px solid #e2e8f0" }}
            />
            <Bar dataKey="risk_index" fill="#dc2626" radius={[0, 8, 8, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-ink-500 mt-2">
          risk_index = avg_defect_rate + 1.5 × fail_inspections + 1.2 × high_severity_count
        </p>
      </div>

      <div className="card overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th className="text-right">SKUs</th>
              <th className="text-right">Avg Defect %</th>
              <th className="text-right">Max Defect %</th>
              <th className="text-right">Fail</th>
              <th className="text-right">Pending</th>
              <th className="text-right">High Sev</th>
              <th className="text-right">Risk Index</th>
              <th className="text-right">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.supplier}>
                <td className="font-semibold text-ink-900">{r.supplier}</td>
                <td className="text-right">{r.skus}</td>
                <td className="text-right">{r.avg_defect_rate.toFixed(2)}</td>
                <td className="text-right">{r.max_defect_rate.toFixed(2)}</td>
                <td className="text-right text-red-600 font-medium">{r.fail_inspections}</td>
                <td className="text-right text-amber-600">{r.pending_inspections}</td>
                <td className="text-right">{r.high_severity_count}</td>
                <td className="text-right font-bold text-ink-900">{r.risk_index.toFixed(2)}</td>
                <td className="text-right text-ink-500">
                  ${(r.total_revenue / 1000).toFixed(1)}k
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
