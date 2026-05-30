import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Spinner from "../components/Spinner.jsx";
import RiskBadge from "../components/RiskBadge.jsx";
import { riskApi } from "../api/client.js";

export default function InventoryRisk() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    riskApi.inventory(30).then(setRows).catch((e) => setError(e.userMessage || e.message));
  }, []);

  if (error) return <div className="text-sm text-red-600">Failed: {error}</div>;
  if (!rows) return <Spinner label="Computing inventory risk…" />;

  return (
    <div className="card overflow-x-auto">
      <h3 className="section-title mb-3">
        At-risk SKUs ({rows.length}) — stockouts ranked first
      </h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product</th>
            <th>Supplier</th>
            <th>Location</th>
            <th className="text-right">Stock</th>
            <th>Status</th>
            <th className="text-right">Order Qty</th>
            <th className="text-right">Units Sold</th>
            <th>Severity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.sku}>
              <td>
                <Link to={`/incident/${r.sku}`} className="font-mono text-brand-700 hover:underline">
                  {r.sku}
                </Link>
              </td>
              <td className="capitalize">{r.product_type}</td>
              <td>{r.supplier}</td>
              <td>{r.location}</td>
              <td className="text-right font-semibold">{r.stock_level}</td>
              <td><RiskBadge value={r.stock_status} /></td>
              <td className="text-right">{r.order_quantity}</td>
              <td className="text-right">{r.units_sold}</td>
              <td><RiskBadge value={r.risk_severity} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
