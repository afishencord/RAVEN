"use client";

type Props = {
  status: string;
};

const palette: Record<string, string> = {
  healthy: "bg-emerald-100 text-emerald-800 border-emerald-300",
  degraded: "bg-amber-100 text-amber-900 border-amber-300",
  down: "bg-rose-100 text-rose-900 border-rose-300",
  disabled: "bg-slate-200 text-slate-700 border-slate-300",
  open: "bg-rose-100 text-rose-900 border-rose-300",
  acknowledged: "bg-amber-100 text-amber-900 border-amber-300",
  resolved: "bg-emerald-100 text-emerald-800 border-emerald-300",
  queued: "bg-sky-100 text-sky-900 border-sky-300",
  running: "bg-violet-100 text-violet-900 border-violet-300",
  success: "bg-emerald-100 text-emerald-800 border-emerald-300",
  failed: "bg-rose-100 text-rose-900 border-rose-300",
};

export function StatusBadge({ status }: Props) {
  const key = status.toLowerCase();
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${palette[key] ?? "bg-slate-200 text-slate-700 border-slate-300"}`}>
      {status}
    </span>
  );
}
