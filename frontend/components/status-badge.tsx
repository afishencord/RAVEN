"use client";

type Props = {
  status: string;
};

const palette: Record<string, string> = {
  healthy: "bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-900",
  degraded: "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-900",
  down: "bg-rose-100 text-rose-900 border-rose-300 dark:bg-rose-950/70 dark:text-rose-300 dark:border-rose-900",
  disabled: "bg-slate-200 text-slate-700 border-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800",
  open: "bg-rose-100 text-rose-900 border-rose-300 dark:bg-rose-950/70 dark:text-rose-300 dark:border-rose-900",
  acknowledged: "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-900",
  resolved: "bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-900",
  queued: "bg-sky-100 text-sky-900 border-sky-300 dark:bg-sky-950/70 dark:text-sky-300 dark:border-sky-900",
  running: "bg-violet-100 text-violet-900 border-violet-300 dark:bg-violet-950/70 dark:text-violet-300 dark:border-violet-900",
  success: "bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-900",
  failed: "bg-rose-100 text-rose-900 border-rose-300 dark:bg-rose-950/70 dark:text-rose-300 dark:border-rose-900",
};

export function StatusBadge({ status }: Props) {
  const key = status.toLowerCase();
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${palette[key] ?? "bg-slate-200 text-slate-700 border-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800"}`}>
      {status}
    </span>
  );
}
