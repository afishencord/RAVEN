"use client";

import { Activity, AlertTriangle, CheckCircle2, Clock3, Server, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { startTransition, useEffect, useMemo, useState, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { DashboardMetrics, MetricBreakdownItem, TimeSeriesPoint, User } from "@/lib/types";

const chartColors = ["#7C3AED", "#16A34A", "#F59E0B", "#EF4444", "#0EA5E9", "#64748B"];

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatMinutes(minutes: number | null) {
  if (minutes === null) {
    return "n/a";
  }
  if (minutes < 60) {
    return `${minutes.toFixed(1)}m`;
  }
  return `${(minutes / 60).toFixed(1)}h`;
}

function total(items: MetricBreakdownItem[]) {
  return items.reduce((sum, item) => sum + item.value, 0);
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        {subtitle ? <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p> : null}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function KpiCard({ label, value, detail, icon: Icon }: { label: string; value: string; detail: string; icon: typeof Activity }) {
  return (
    <div className="rounded-[1.5rem] border border-[#E5E7EB] bg-white p-5 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</p>
          <p className="mt-3 text-3xl font-semibold text-[#111827] dark:text-white">{value}</p>
        </div>
        <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#F3E8FF] text-[#7C3AED] dark:bg-[#2B195D] dark:text-purple-200">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">{detail}</p>
    </div>
  );
}

function DonutChart({ items }: { items: MetricBreakdownItem[] }) {
  const itemTotal = total(items);
  let cursor = 0;
  const segments = items.map((item, index) => {
    const start = cursor;
    const next = itemTotal ? cursor + (item.value / itemTotal) * 100 : cursor;
    cursor = next;
    return `${chartColors[index % chartColors.length]} ${start}% ${next}%`;
  });
  const background = itemTotal ? `conic-gradient(${segments.join(", ")})` : "#E2E8F0";

  return (
    <div className="grid gap-6 md:grid-cols-[220px_1fr] md:items-center">
      <div className="relative mx-auto h-52 w-52 rounded-full" style={{ background }}>
        <div className="absolute inset-10 grid place-items-center rounded-full bg-white text-center dark:bg-[#050814]">
          <p className="text-3xl font-semibold">{itemTotal}</p>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">nodes</p>
        </div>
      </div>
      <BreakdownList items={items} />
    </div>
  );
}

function LineChart({ points }: { points: TimeSeriesPoint[] }) {
  const width = 640;
  const height = 220;
  const padding = 28;
  const maxValue = Math.max(1, ...points.map((point) => point.value));
  const plotted = points.map((point, index) => {
    const x = points.length <= 1 ? width / 2 : padding + (index / (points.length - 1)) * (width - padding * 2);
    const y = height - padding - (point.value / maxValue) * (height - padding * 2);
    return { ...point, x, y };
  });
  const polylinePoints = plotted.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="overflow-hidden rounded-[1.5rem] bg-panel p-4 dark:bg-[#0B1020]">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full" role="img" aria-label="Successful remediations over time">
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#CBD5E1" strokeWidth="1" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#CBD5E1" strokeWidth="1" />
        <polyline points={polylinePoints} fill="none" stroke="#7C3AED" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        {plotted.map((point) => (
          <g key={point.date}>
            <circle cx={point.x} cy={point.y} r="5" fill="#7C3AED" />
            {point.value > 0 ? (
              <text x={point.x} y={point.y - 12} textAnchor="middle" className="fill-slate-600 text-xs dark:fill-slate-300">
                {point.value}
              </text>
            ) : null}
          </g>
        ))}
        {plotted.length ? (
          <>
            <text x={padding} y={height - 6} className="fill-slate-500 text-xs dark:fill-slate-400">
              {new Date(plotted[0].date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
            <text x={width - padding} y={height - 6} textAnchor="end" className="fill-slate-500 text-xs dark:fill-slate-400">
              {new Date(plotted[plotted.length - 1].date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          </>
        ) : null}
      </svg>
    </div>
  );
}

function BarList({ items }: { items: MetricBreakdownItem[] }) {
  const maxValue = Math.max(1, ...items.map((item) => item.value));
  return (
    <div className="space-y-4">
      {items.map((item, index) => (
        <div key={item.label}>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{titleCase(item.label)}</span>
            <span className="text-slate-500 dark:text-slate-400">{item.value}</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-slate-100 dark:bg-[#0B1020]">
            <div
              className="h-full rounded-full"
              style={{ width: `${(item.value / maxValue) * 100}%`, backgroundColor: chartColors[index % chartColors.length] }}
            />
          </div>
        </div>
      ))}
      {!items.length ? <p className="text-sm text-slate-500 dark:text-slate-400">No data yet.</p> : null}
    </div>
  );
}

function BreakdownList({ items }: { items: MetricBreakdownItem[] }) {
  const itemTotal = total(items);
  return (
    <div className="space-y-3">
      {items.map((item, index) => {
        const percent = itemTotal ? Math.round((item.value / itemTotal) * 100) : 0;
        return (
          <div key={item.label} className="flex items-center justify-between gap-4 rounded-2xl bg-panel px-4 py-3 dark:bg-[#0B1020]">
            <div className="flex min-w-0 items-center gap-3">
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: chartColors[index % chartColors.length] }} />
              <span className="truncate text-sm font-medium">{titleCase(item.label)}</span>
            </div>
            <span className="shrink-0 text-sm text-slate-500 dark:text-slate-400">{item.value} | {percent}%</span>
          </div>
        );
      })}
      {!items.length ? <p className="text-sm text-slate-500 dark:text-slate-400">No data yet.</p> : null}
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  async function refreshMetrics() {
    const payload = await apiFetch<DashboardMetrics>("/dashboard/metrics");
    setMetrics(payload);
    setLastSynced(new Date().toISOString());
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        refreshMetrics()
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load dashboard"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  useLiveRefresh(refreshMetrics, {
    enabled: Boolean(user),
    intervalMs: 3000,
    onError: (err) => setError(err instanceof Error ? err.message : "Live dashboard refresh failed"),
  });

  const remediationRate = useMemo(() => {
    if (!metrics) {
      return "n/a";
    }
    const completed = metrics.execution_status_counts
      .filter((item) => item.label === "success" || item.label === "failed")
      .reduce((sum, item) => sum + item.value, 0);
    if (!completed) {
      return "n/a";
    }
    return `${Math.round((metrics.successful_remediations / completed) * 100)}%`;
  }, [metrics]);

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Dashboard"
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-2 rounded-[1.5rem] border border-[#E5E7EB] bg-white px-5 py-4 text-sm text-slate-600 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:text-slate-300 dark:shadow-none md:flex-row md:items-center md:justify-between">
          <span>Live analytics enabled{lastSynced ? ` | Synced ${new Date(lastSynced).toLocaleTimeString()}` : ""}</span>
          <span>Read-only metrics from monitored nodes, incidents, approvals, and execution tasks.</span>
        </div>

        {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
        {loading ? <p className="text-sm text-slate-600 dark:text-slate-300">Loading dashboard analytics...</p> : null}

        {metrics ? (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label="Monitored Nodes"
                value={metrics.total_nodes.toString()}
                detail={`${metrics.enabled_nodes} enabled across the fleet`}
                icon={Server}
              />
              <KpiCard
                label="Active Incidents"
                value={metrics.active_incidents.toString()}
                detail={`${metrics.resolved_incidents} incidents resolved historically`}
                icon={AlertTriangle}
              />
              <KpiCard
                label="Healthy Remediations"
                value={metrics.successful_remediations.toString()}
                detail={`${remediationRate} success rate after validation`}
                icon={CheckCircle2}
              />
              <KpiCard
                label="Avg Resolution"
                value={formatMinutes(metrics.average_resolution_minutes)}
                detail="Based on incidents with recorded resolution time"
                icon={Clock3}
              />
            </section>

            <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
              <Card title="Node State" subtitle="Current health distribution across enabled and disabled nodes">
                <DonutChart items={metrics.node_state_counts} />
              </Card>
              <Card title="Successful Remediations" subtitle="Validated successful command executions over the last 14 days">
                <LineChart points={metrics.successful_remediations_over_time} />
              </Card>
            </section>

            <section className="grid gap-6 xl:grid-cols-3">
              <Card title="Execution Outcomes" subtitle="Task status distribution from approved command runs">
                <BarList items={metrics.execution_status_counts} />
              </Card>
              <Card title="Approval Decisions" subtitle="Operator and admin command decisions">
                <BarList items={metrics.approval_decision_counts} />
              </Card>
              <Card title="Execution Modes" subtitle="How remediation routes are configured across nodes">
                <BarList items={metrics.execution_mode_counts} />
              </Card>
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <Card title="Environments" subtitle="Node coverage by configured environment">
                <BreakdownList items={metrics.environment_counts} />
              </Card>
              <Card title="Top Failure Types" subtitle="Most frequent incident classifications">
                <BreakdownList items={metrics.failure_type_counts} />
              </Card>
            </section>

            <section className="grid gap-4 md:grid-cols-3">
              <div className="rounded-[1.5rem] bg-[#111827] p-5 text-white dark:bg-[#0B1020]">
                <Activity className="h-5 w-5 text-purple-300" />
                <p className="mt-4 text-sm text-slate-300">Automation throughput</p>
                <p className="mt-2 text-2xl font-semibold">{total(metrics.execution_status_counts)}</p>
              </div>
              <div className="rounded-[1.5rem] bg-[#111827] p-5 text-white dark:bg-[#0B1020]">
                <ShieldCheck className="h-5 w-5 text-emerald-300" />
                <p className="mt-4 text-sm text-slate-300">Human decisions</p>
                <p className="mt-2 text-2xl font-semibold">{total(metrics.approval_decision_counts)}</p>
              </div>
              <div className="rounded-[1.5rem] bg-[#111827] p-5 text-white dark:bg-[#0B1020]">
                <Server className="h-5 w-5 text-sky-300" />
                <p className="mt-4 text-sm text-slate-300">Environment groups</p>
                <p className="mt-2 text-2xl font-semibold">{metrics.environment_counts.length}</p>
              </div>
            </section>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
