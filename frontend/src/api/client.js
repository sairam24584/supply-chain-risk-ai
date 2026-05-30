import axios from "axios";

// Same-origin: vite proxies /api/* to FastAPI in dev; in prod set VITE_API_BASE.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "",
  timeout: 60000,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    // Surface backend detail when present for nicer UX.
    const detail = err?.response?.data?.detail;
    if (detail) err.userMessage = typeof detail === "string" ? detail : JSON.stringify(detail);
    return Promise.reject(err);
  }
);

export const dashboardApi = {
  summary: () => api.get("/api/dashboard/summary").then((r) => r.data),
};

export const riskApi = {
  suppliers: (top_n = 10) => api.get(`/api/suppliers/risk?top_n=${top_n}`).then((r) => r.data),
  shipments: () => api.get("/api/shipments/risk").then((r) => r.data),
  inventory: (top_n = 20) => api.get(`/api/inventory/risk?top_n=${top_n}`).then((r) => r.data),
  incident: (sku) => api.get(`/api/incidents/${encodeURIComponent(sku)}`).then((r) => r.data),
};

export const intelligenceApi = {
  anomalies: () => api.get("/api/anomalies").then((r) => r.data),
  correlations: () => api.get("/api/correlations").then((r) => r.data),
  forecast: (sku) => api.get(`/api/forecast/${encodeURIComponent(sku)}`).then((r) => r.data),
  stockoutPrediction: (top_n = 20) =>
    api.get(`/api/stockout-prediction?top_n=${top_n}`).then((r) => r.data),
  regions: () => api.get("/api/regions/risk").then((r) => r.data),
};

export const uploadApi = {
  document: (file, onProgress) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post("/api/upload/document", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) =>
          onProgress && onProgress(Math.round((e.loaded / (e.total || e.loaded)) * 100)),
      })
      .then((r) => r.data);
  },
  csv: (file, onProgress) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post("/api/upload/csv", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) =>
          onProgress && onProgress(Math.round((e.loaded / (e.total || e.loaded)) * 100)),
      })
      .then((r) => r.data);
  },
  sources: () => api.get("/api/upload/sources").then((r) => r.data),
  remove: (name) =>
    api.delete(`/api/upload/sources/${encodeURIComponent(name)}`).then((r) => r.data),
};

// Persistent per-browser-session thread id so the backend keeps conversation state.
function getThreadId() {
  try {
    let tid = localStorage.getItem("scri.thread_id");
    if (!tid) {
      tid = `thr_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
      localStorage.setItem("scri.thread_id", tid);
    }
    return tid;
  } catch {
    return null;
  }
}

export function resetThread() {
  try {
    const tid = `thr_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    localStorage.setItem("scri.thread_id", tid);
    return tid;
  } catch {
    return null;
  }
}

export const queryApi = {
  ask: (payload) =>
    api
      .post("/api/query", { thread_id: getThreadId(), ...payload })
      .then((r) => r.data),
  cacheStats: () => api.get("/api/cache/stats").then((r) => r.data),
  cacheClear: () => api.post("/api/cache/clear").then((r) => r.data),
};

export const feedbackApi = {
  vote: (query, vote, doc_id = null) =>
    api.post("/api/feedback", { query, vote, doc_id }).then((r) => r.data),
  stats: () => api.get("/api/feedback/stats").then((r) => r.data),
};

export const alertsApi = {
  list: (params = {}) => api.get("/api/alerts", { params }).then((r) => r.data),
  summary: () => api.get("/api/alerts/summary").then((r) => r.data),
};

export default api;
