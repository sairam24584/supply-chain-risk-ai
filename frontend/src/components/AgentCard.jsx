import { Factory, Truck, Boxes } from "lucide-react";

const META = {
  supplier:  { icon: Factory, label: "Supplier Risk",        accent: "from-red-50 to-white border-red-100" },
  shipment:  { icon: Truck,   label: "Shipment Analysis",    accent: "from-amber-50 to-white border-amber-100" },
  inventory: { icon: Boxes,   label: "Inventory Intelligence", accent: "from-brand-50 to-white border-brand-100" },
};

export default function AgentCard({ agent, text }) {
  const meta = META[agent] || { icon: Factory, label: agent, accent: "from-ink-50 to-white border-ink-100" };
  const Icon = meta.icon;
  return (
    <div className={`rounded-2xl border bg-gradient-to-br ${meta.accent} shadow-card p-5`}>
      <div className="flex items-center gap-2 mb-3">
        <div className="h-8 w-8 rounded-lg bg-white shadow-card flex items-center justify-center">
          <Icon size={16} className="text-ink-700" />
        </div>
        <h3 className="font-semibold text-sm text-ink-900">{meta.label}</h3>
      </div>
      <p className="text-sm whitespace-pre-wrap text-ink-700 leading-relaxed">
        {text || <span className="text-ink-400 italic">(no findings)</span>}
      </p>
    </div>
  );
}
