// Small shared presentational pieces for the incident screens.
// ponytail: plain Tailwind, no component library — shadcn/ui arrives with
// the first interactive controls (approve/reject), per docs/08-ui-design.md.

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-400",
  medium: "bg-yellow-400",
  low: "bg-sky-400",
};

export function SeverityDot({ severity }: { severity: string }) {
  return (
    <span
      title={severity}
      className={`h-2.5 w-2.5 shrink-0 rounded-full ${SEVERITY_COLORS[severity] ?? "bg-zinc-500"}`}
    />
  );
}

export function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone =
    value >= 0.25 ? "text-emerald-300 border-emerald-800/60" : "text-zinc-400 border-zinc-700";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-mono ${tone}`}>
      {pct}%
    </span>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded bg-zinc-800">
      <div
        className="h-full rounded bg-emerald-500/80"
        style={{ width: `${Math.min(100, Math.round(value * 100))}%` }}
      />
    </div>
  );
}
