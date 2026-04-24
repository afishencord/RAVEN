"use client";

type Props = {
  status: string;
};

const palette: Record<string, string> = {
  healthy: "bg-green-50 text-[#16A34A] border-green-200 dark:bg-green-500/10 dark:text-green-300 dark:border-green-500/20",
  degraded: "bg-orange-50 text-[#F97316] border-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:border-orange-500/20",
  down: "bg-red-50 text-[#EF4444] border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  disabled: "bg-slate-100 text-[#64748B] border-slate-200 dark:bg-white/5 dark:text-slate-400 dark:border-white/10",
  open: "bg-red-50 text-[#EF4444] border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  acknowledged: "bg-orange-50 text-[#F97316] border-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:border-orange-500/20",
  resolved: "bg-green-50 text-[#16A34A] border-green-200 dark:bg-green-500/10 dark:text-green-300 dark:border-green-500/20",
  queued: "bg-blue-50 text-[#3B82F6] border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  running: "bg-violet-50 text-[#7C3AED] border-violet-200 dark:bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/20",
  success: "bg-green-50 text-[#16A34A] border-green-200 dark:bg-green-500/10 dark:text-green-300 dark:border-green-500/20",
  failed: "bg-red-50 text-[#EF4444] border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
};

export function StatusBadge({ status }: Props) {
  const key = status.toLowerCase();
  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${palette[key] ?? "bg-slate-100 text-[#64748B] border-slate-200 dark:bg-white/5 dark:text-slate-300 dark:border-white/10"}`}>
      {status}
    </span>
  );
}
