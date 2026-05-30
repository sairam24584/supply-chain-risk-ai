import { useEffect, useState } from "react";
import { Truck, Clock, TrendingDown } from "lucide-react";
import Spinner from "../components/Spinner.jsx";
import StatCard from "../components/StatCard.jsx";
import { riskApi } from "../api/client.js";

export default function ShipmentRisk() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    riskApi.shipments().then(setData).catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!data) return <Spinner label="Computing shipment risk…" />;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Total shipments" value={data.total_shipments}                      icon={Truck} />
        <StatCard label="Delayed"         value={data.delayed_count} accent="red"            icon={Clock} />
        <StatCard label="Delay rate"      value={`${(data.delay_rate * 100).toFixed(1)}%`}  accent="amber" icon={TrendingDown} />
      </div>

      <div className="card overflow-x-auto">
        <h3 className="section-title mb-3">Carrier × Route Hotspots (sorted by delay rate)</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Carrier</th>
              <th>Route</th>
              <th className="text-right">Shipments</th>
              <th className="text-right">Delayed</th>
              <th className="text-right">Delay Rate</th>
              <th className="text-right">Avg Time (d)</th>
              <th className="text-right">Avg Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.hotspots.map((r, i) => (
              <tr key={i}>
                <td>{r.carrier}</td>
                <td>{r.route}</td>
                <td className="text-right">{r.shipments}</td>
                <td className="text-right text-red-600 font-medium">{r.delayed}</td>
                <td className="text-right font-bold">{(r.delay_rate * 100).toFixed(0)}%</td>
                <td className="text-right">{r.avg_shipping_time.toFixed(1)}</td>
                <td className="text-right text-ink-500">${r.avg_shipping_cost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3 className="section-title mb-3">By Transport Mode</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.by_transport_mode.map((m) => {
            const rate = m.delay_rate * 100;
            const accent = rate >= 60 ? "border-red-200"
                          : rate >= 40 ? "border-amber-200"
                          : "border-emerald-200";
            return (
              <div key={m.mode} className={`rounded-xl border ${accent} bg-white p-4`}>
                <div className="section-title">{m.mode}</div>
                <div className="text-2xl font-bold text-ink-900 mt-1">{rate.toFixed(0)}%</div>
                <div className="text-xs text-ink-500 mt-0.5">
                  {m.delayed}/{m.shipments} delayed · ${m.avg_cost.toFixed(0)} avg
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
