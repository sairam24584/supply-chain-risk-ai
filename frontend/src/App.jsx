import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import QueryConsole from "./pages/QueryConsole.jsx";
import SupplierRisk from "./pages/SupplierRisk.jsx";
import ShipmentRisk from "./pages/ShipmentRisk.jsx";
import InventoryRisk from "./pages/InventoryRisk.jsx";
import IncidentDetail from "./pages/IncidentDetail.jsx";
import Anomalies from "./pages/Anomalies.jsx";
import Regions from "./pages/Regions.jsx";
import Data from "./pages/Data.jsx";

function Page({ children }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-7xl mx-auto px-8 py-7">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/"          element={<Navigate to="/query" replace />} />
        <Route path="/query"     element={<QueryConsole />} />
        <Route path="/dashboard" element={<Page><Dashboard /></Page>} />
        <Route path="/anomalies" element={<Page><Anomalies /></Page>} />
        <Route path="/regions"   element={<Page><Regions /></Page>} />
        <Route path="/suppliers" element={<Page><SupplierRisk /></Page>} />
        <Route path="/shipments" element={<Page><ShipmentRisk /></Page>} />
        <Route path="/inventory" element={<Page><InventoryRisk /></Page>} />
        <Route path="/data"      element={<Page><Data /></Page>} />
        <Route path="/incident/:sku" element={<Page><IncidentDetail /></Page>} />
        <Route path="*"          element={<Navigate to="/query" replace />} />
      </Routes>
    </Layout>
  );
}
