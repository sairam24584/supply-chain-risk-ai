const STYLES = {
  high:           "badge-soft-red",
  medium:         "badge-soft-amber",
  low:            "badge-soft-green",
  stockout_risk:  "badge-soft-red",
  overstock:      "badge-soft-amber",
  healthy:        "badge-soft-green",
  delayed:        "badge-soft-red",
  moderate:       "badge-soft-amber",
  on_time:        "badge-soft-green",
  Fail:           "badge-soft-red",
  Pending:        "badge-soft-amber",
  Pass:           "badge-soft-green",
};

export default function RiskBadge({ value }) {
  if (!value) return null;
  const klass = STYLES[value] || "badge-soft-ink";
  const label = String(value).replace("_", " ");
  return <span className={klass}>{label}</span>;
}
