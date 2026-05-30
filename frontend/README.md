# Supply Chain Risk Intelligence — Frontend

React + Vite + TailwindCSS dashboard for the FastAPI backend.

## Quick start

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on **http://localhost:5173** and proxies `/api/*` and
`/health` to the FastAPI backend at `http://localhost:8000` (configured in
`vite.config.js`). Make sure the backend is running first:

```bash
# in a separate terminal, from project root
cd backend
uvicorn app.main:app --reload
```

## Pages

| Route | Purpose |
| --- | --- |
| `/dashboard` | Summary tiles + severity / stock / delay charts |
| `/query` | Natural-language query console (multi-agent pipeline) |
| `/suppliers` | Supplier risk index + ranking table |
| `/shipments` | Carrier × route hotspots + transport-mode delay rates |
| `/inventory` | At-risk SKU list (stockouts first), click to drill down |
| `/incident/:sku` | Single-SKU drill-down |

## Build

```bash
npm run build      # outputs to dist/
npm run preview    # serve the production build locally
```

## Environment variables

In production set `VITE_API_BASE=https://your-backend.example.com` before
building. In dev, leave it unset — the proxy handles routing.
