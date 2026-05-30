import { Loader2 } from "lucide-react";

export default function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 text-ink-500 text-sm">
      <Loader2 size={16} className="animate-spin text-brand-500" />
      {label}
    </div>
  );
}

export function SkeletonRow({ width = "100%" }) {
  return <div className="skeleton h-3" style={{ width }} />;
}

export function SkeletonCard() {
  return (
    <div className="card">
      <div className="space-y-3">
        <SkeletonRow width="40%" />
        <SkeletonRow width="60%" />
        <SkeletonRow width="80%" />
      </div>
    </div>
  );
}
