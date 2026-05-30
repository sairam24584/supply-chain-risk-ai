export default function StatCard({ label, value, sub, accent = "ink", icon: Icon }) {
  const accentMap = {
    brand:   { text: "text-brand-700",   bg: "bg-brand-50",   ring: "ring-brand-100" },
    red:     { text: "text-red-700",     bg: "bg-red-50",     ring: "ring-red-100" },
    amber:   { text: "text-amber-700",   bg: "bg-amber-50",   ring: "ring-amber-100" },
    emerald: { text: "text-emerald-700", bg: "bg-emerald-50", ring: "ring-emerald-100" },
    ink:     { text: "text-ink-700",     bg: "bg-ink-100",    ring: "ring-ink-200" },
  };
  const a = accentMap[accent] || accentMap.ink;
  return (
    <div className="kpi">
      <div className="flex items-start justify-between">
        <div className="kpi-label">{label}</div>
        {Icon && (
          <div className={`h-8 w-8 rounded-lg ${a.bg} ${a.text} ring-1 ${a.ring} flex items-center justify-center`}>
            <Icon size={16} />
          </div>
        )}
      </div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}
