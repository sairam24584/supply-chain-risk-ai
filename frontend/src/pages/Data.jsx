import { useEffect, useRef, useState } from "react";
import {
  Upload, FileText, FileSpreadsheet, Trash2, CheckCircle2, Loader2, AlertTriangle, RotateCcw,
} from "lucide-react";
import { uploadApi } from "../api/client.js";

const DOC_EXTS = [".pdf", ".txt", ".md"];

function bytes(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export default function Data() {
  const [sources, setSources] = useState(null);
  const [docMsg, setDocMsg] = useState(null);
  const [csvMsg, setCsvMsg] = useState(null);
  const [docBusy, setDocBusy] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = () => uploadApi.sources().then(setSources).catch((e) => setError(e.message));
  useEffect(() => { refresh(); }, []);

  async function uploadDoc(file) {
    setError(null); setDocMsg(null); setDocBusy(true);
    try {
      const r = await uploadApi.document(file);
      setDocMsg(r);
      refresh();
    } catch (e) {
      setError(e.userMessage || e.message);
    } finally {
      setDocBusy(false);
    }
  }

  async function uploadCsv(file) {
    setError(null); setCsvMsg(null); setCsvBusy(true);
    try {
      const r = await uploadApi.csv(file);
      setCsvMsg(r);
      refresh();
    } catch (e) {
      setError(e.userMessage || e.message);
    } finally {
      setCsvBusy(false);
    }
  }

  async function remove(name) {
    if (!confirm(`Delete ${name}?`)) return;
    try {
      await uploadApi.remove(name);
      refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-ink-900 tracking-tight">Data sources</h2>
        <p className="text-sm text-ink-500 mt-1">
          Upload documents to enrich the assistant's knowledge or replace the dataset CSV entirely.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <UploadCard
          title="Supplementary documents"
          subtitle="PDF · TXT · MD — added as retrievable context"
          icon={FileText}
          accept={DOC_EXTS.join(",")}
          busy={docBusy}
          msg={docMsg && (
            <span>
              <b>{docMsg.file}</b> · {docMsg.chunks} chunks · {bytes(docMsg.bytes)}
            </span>
          )}
          onFile={uploadDoc}
        />
        <UploadCard
          title="Replace dataset CSV"
          subtitle="Must match the supply-chain schema. Triggers full re-ingest."
          icon={FileSpreadsheet}
          accept=".csv"
          busy={csvBusy}
          danger
          msg={csvMsg && (
            <span>
              <b>{csvMsg.rows}</b> rows ingested · severity {JSON.stringify(csvMsg.severity_breakdown)}
            </span>
          )}
          onFile={uploadCsv}
        />
      </div>

      <SourcesList sources={sources} onRemove={remove} onRefresh={refresh} />
    </div>
  );
}

function UploadCard({ title, subtitle, icon: Icon, accept, busy, msg, danger, onFile }) {
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);

  function handleFiles(files) {
    const f = files?.[0];
    if (f) onFile(f);
  }

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className={danger ? "text-red-600" : "text-brand-600"} />
        <h3 className="font-semibold text-sm text-ink-900">{title}</h3>
      </div>
      <p className="text-xs text-ink-500 mb-3">{subtitle}</p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault(); setDrag(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`rounded-xl border-2 border-dashed px-4 py-8 text-center cursor-pointer transition
          ${drag ? "border-brand-400 bg-brand-50" :
            danger ? "border-red-200 hover:border-red-300 hover:bg-red-50/50" :
                     "border-ink-200 hover:border-brand-300 hover:bg-brand-50/50"}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {busy ? (
          <div className="flex items-center justify-center gap-2 text-ink-600 text-sm">
            <Loader2 size={14} className="animate-spin" /> uploading…
          </div>
        ) : (
          <div className="text-sm text-ink-600">
            <Upload size={18} className="mx-auto mb-2 text-ink-400" />
            <div>Drop a file or <span className="text-brand-700 font-semibold">browse</span></div>
            <div className="mt-1 text-[11px] text-ink-400">accepted: {accept}</div>
          </div>
        )}
      </div>

      {msg && (
        <div className="mt-3 flex items-start gap-2 text-xs text-emerald-700">
          <CheckCircle2 size={14} className="mt-0.5" /> {msg}
        </div>
      )}
    </div>
  );
}

function SourcesList({ sources, onRemove, onRefresh }) {
  if (!sources) return null;
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-sm text-ink-900">Sources</h3>
        <button onClick={onRefresh} className="btn-ghost text-xs">
          <RotateCcw size={12} className="mr-1" /> refresh
        </button>
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between border border-ink-100 rounded-xl px-3 py-2.5 bg-ink-50/40">
          <div className="flex items-center gap-2 text-sm">
            <FileSpreadsheet size={14} className="text-ink-500" />
            <span className="font-mono text-xs text-ink-700">{sources.csv_path}</span>
          </div>
          <span className="badge-soft-brand">canonical dataset</span>
        </div>
        {sources.documents?.length === 0 ? (
          <div className="rounded-xl border border-dashed border-ink-200 px-4 py-6 text-center text-xs text-ink-400">
            No documents uploaded yet.
          </div>
        ) : (
          sources.documents?.map((d) => (
            <div key={d.name} className="flex items-center justify-between border border-ink-100 rounded-xl px-3 py-2.5">
              <div className="flex items-center gap-2 text-sm">
                <FileText size={14} className="text-ink-500" />
                <span className="text-ink-800">{d.name}</span>
                <span className="text-xs text-ink-400">{d.ext} · {bytes(d.bytes)}</span>
              </div>
              <button
                onClick={() => onRemove(d.name)}
                className="text-ink-400 hover:text-red-600 transition"
                title="Delete file"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>
      <p className="text-[11px] text-ink-400 mt-3">
        Deleting a file here removes it from disk. Already-embedded chunks remain in the vector store
        until the dataset is rebuilt.
      </p>
    </div>
  );
}
