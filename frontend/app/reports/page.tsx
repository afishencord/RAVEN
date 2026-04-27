"use client";

import { startTransition, useEffect, useMemo, useState } from "react";
import { Download, FileJson, FileSpreadsheet } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { apiFetch, requireSession } from "@/lib/api";
import { AuditLogRecord, DashboardMetrics, MessageIncident, MetricBreakdownItem, NodeRecord, User } from "@/lib/types";

type ReportType = "executive" | "node_health" | "remediation" | "incident_history" | "audit";
type ReportRow = Record<string, string | number>;

const reportTypes: { value: ReportType; label: string }[] = [
  { value: "executive", label: "Executive summary" },
  { value: "node_health", label: "Node health" },
  { value: "remediation", label: "Remediation performance" },
  { value: "incident_history", label: "Incident history" },
  { value: "audit", label: "Audit activity" },
];

const chartColors = ["#7C3AED", "#16A34A", "#F59E0B", "#EF4444", "#0EA5E9", "#64748B"];

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function toDateInput(date: Date) {
  return date.toISOString().slice(0, 10);
}

function metricTotal(items: MetricBreakdownItem[]) {
  return items.reduce((sum, item) => sum + item.value, 0);
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
      {!items.length ? <p className="text-sm text-slate-500 dark:text-slate-400">No data available.</p> : null}
    </div>
  );
}

function csvEscape(value: string | number) {
  const raw = String(value);
  if (/[",\n]/.test(raw)) {
    return `"${raw.replaceAll("\"", "\"\"")}"`;
  }
  return raw;
}

function downloadFile(filename: string, mimeType: string, content: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function rowsToCsv(rows: ReportRow[]) {
  if (!rows.length) {
    return "";
  }
  const headers = Object.keys(rows[0]);
  return [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header] ?? "")).join(",")),
  ].join("\n");
}

function withinDateRange(value: string, startDate: string, endDate: string) {
  const time = new Date(value).getTime();
  const start = startDate ? new Date(`${startDate}T00:00:00`).getTime() : null;
  const end = endDate ? new Date(`${endDate}T23:59:59`).getTime() : null;
  return (start === null || time >= start) && (end === null || time <= end);
}

function buildReportRows(type: ReportType, metrics: DashboardMetrics | null, nodes: NodeRecord[], messages: MessageIncident[], auditLogs: AuditLogRecord[], startDate: string, endDate: string): ReportRow[] {
  if (!metrics) {
    return [];
  }

  if (type === "executive") {
    return [
      { metric: "Monitored nodes", value: metrics.total_nodes },
      { metric: "Enabled nodes", value: metrics.enabled_nodes },
      { metric: "Active incidents", value: metrics.active_incidents },
      { metric: "Resolved incidents", value: metrics.resolved_incidents },
      { metric: "Successful remediations", value: metrics.successful_remediations },
      { metric: "Average resolution minutes", value: metrics.average_resolution_minutes ?? "n/a" },
    ];
  }

  if (type === "node_health") {
    return nodes.map((node) => ({
      node: node.name,
      environment: node.environment,
      status: node.is_enabled ? node.current_status : "disabled",
      host: `${node.host}${node.port ? `:${node.port}` : ""}`,
      execution_mode: node.execution_mode,
      folder: node.group_name ?? "Ungrouped",
      last_check: node.last_check_at ? new Date(node.last_check_at).toLocaleString() : "Never",
    }));
  }

  if (type === "remediation") {
    return [
      ...metrics.execution_status_counts.map((item) => ({ section: "Execution outcome", label: titleCase(item.label), value: item.value })),
      ...metrics.approval_decision_counts.map((item) => ({ section: "Approval decision", label: titleCase(item.label), value: item.value })),
      ...metrics.successful_remediations_over_time.map((point) => ({ section: "Successful remediations", label: point.date, value: point.value })),
    ];
  }

  if (type === "incident_history") {
    return messages
      .filter((message) => withinDateRange(message.incident.started_at, startDate, endDate))
      .map((message) => ({
        incident: message.incident.id,
        node: message.node.name,
        status: message.incident.status,
        severity: message.incident.severity,
        failure_type: message.incident.failure_type,
        started: new Date(message.incident.started_at).toLocaleString(),
        resolved: message.incident.resolved_at ? new Date(message.incident.resolved_at).toLocaleString() : "Unresolved",
        summary: message.incident.summary,
      }));
  }

  return auditLogs
    .filter((log) => withinDateRange(log.created_at, startDate, endDate))
    .map((log) => ({
      id: log.id,
      entity_type: log.entity_type,
      entity_id: log.entity_id,
      action: log.action,
      actor_user_id: log.actor_user_id ?? "system",
      created: new Date(log.created_at).toLocaleString(),
    }));
}

export default function ReportsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [messages, setMessages] = useState<MessageIncident[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [reportType, setReportType] = useState<ReportType>("executive");
  const [startDate, setStartDate] = useState(() => toDateInput(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)));
  const [endDate, setEndDate] = useState(() => toDateInput(new Date()));
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadReportData() {
    const [metricData, nodeData, activeMessages, archivedMessages, logs] = await Promise.all([
      apiFetch<DashboardMetrics>("/dashboard/metrics"),
      apiFetch<NodeRecord[]>("/nodes"),
      apiFetch<MessageIncident[]>("/messages"),
      apiFetch<MessageIncident[]>("/messages?archived=true"),
      apiFetch<AuditLogRecord[]>("/audit/logs"),
    ]);
    setMetrics(metricData);
    setNodes(nodeData);
    setMessages([...activeMessages, ...archivedMessages]);
    setAuditLogs(logs);
    setGeneratedAt(new Date().toISOString());
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        loadReportData()
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load report data"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  const reportRows = useMemo(
    () => buildReportRows(reportType, metrics, nodes, messages, auditLogs, startDate, endDate),
    [reportType, metrics, nodes, messages, auditLogs, startDate, endDate],
  );

  const reportName = reportTypes.find((entry) => entry.value === reportType)?.label ?? "Report";
  const filenameBase = `raven-${reportType}-${new Date().toISOString().slice(0, 10)}`;
  const tableHeaders = Object.keys(reportRows[0] ?? { report: "No data" });

  function exportCsv() {
    downloadFile(`${filenameBase}.csv`, "text/csv;charset=utf-8", rowsToCsv(reportRows));
  }

  function exportJson() {
    downloadFile(`${filenameBase}.json`, "application/json;charset=utf-8", JSON.stringify({ report: reportName, generated_at: generatedAt, rows: reportRows }, null, 2));
  }

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Reports"
      headerActions={
        <>
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#E5E7EB] bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:bg-[#050814] dark:text-slate-200"
            onClick={exportJson}
            disabled={!reportRows.length}
          >
            <FileJson className="h-4 w-4" />
            JSON
          </button>
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#7C3AED] px-4 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(124,58,237,0.25)] transition hover:bg-[#6D28D9] disabled:opacity-50 dark:shadow-none"
            onClick={exportCsv}
            disabled={!reportRows.length}
          >
            <Download className="h-4 w-4" />
            CSV
          </button>
        </>
      }
    >
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <h3 className="text-xl font-semibold">Report builder</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{generatedAt ? `Generated ${new Date(generatedAt).toLocaleString()}` : "Not generated yet"}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-[220px_160px_160px_auto]">
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Report</span>
                <select
                  value={reportType}
                  onChange={(event) => setReportType(event.target.value as ReportType)}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                >
                  {reportTypes.map((entry) => (
                    <option key={entry.value} value={entry.value}>{entry.label}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Start</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">End</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </label>
              <button
                type="button"
                className="mt-7 inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember"
                onClick={() => {
                  setGeneratedAt(new Date().toISOString());
                  void loadReportData().catch((err) => setError(err instanceof Error ? err.message : "Failed to refresh report"));
                }}
              >
                <FileSpreadsheet className="h-4 w-4" />
                Create
              </button>
            </div>
          </div>
        </section>

        {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
        {loading ? <p className="text-sm text-slate-600 dark:text-slate-300">Loading report data...</p> : null}

        {metrics ? (
          <section className="grid gap-6 xl:grid-cols-3">
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-lg font-semibold">Node State</h3>
              <div className="mt-5">
                <BarList items={metrics.node_state_counts} />
              </div>
            </div>
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-lg font-semibold">Execution Outcomes</h3>
              <div className="mt-5">
                <BarList items={metrics.execution_status_counts} />
              </div>
            </div>
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-lg font-semibold">Report Scope</h3>
              <div className="mt-5 grid gap-3 text-sm">
                <div className="flex items-center justify-between rounded-2xl bg-panel px-4 py-3 dark:bg-[#0B1020]">
                  <span className="text-slate-500 dark:text-slate-400">Rows</span>
                  <span className="font-semibold">{reportRows.length}</span>
                </div>
                <div className="flex items-center justify-between rounded-2xl bg-panel px-4 py-3 dark:bg-[#0B1020]">
                  <span className="text-slate-500 dark:text-slate-400">Automations</span>
                  <span className="font-semibold">{metricTotal(metrics.execution_status_counts)}</span>
                </div>
                <div className="flex items-center justify-between rounded-2xl bg-panel px-4 py-3 dark:bg-[#0B1020]">
                  <span className="text-slate-500 dark:text-slate-400">Decisions</span>
                  <span className="font-semibold">{metricTotal(metrics.approval_decision_counts)}</span>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-xl font-semibold">{reportName}</h3>
            <span className="rounded-full bg-panel px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-[#0B1020] dark:text-slate-300">
              {reportRows.length} rows
            </span>
          </div>
          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-panel dark:bg-[#0B1020]">
                <tr className="text-left text-slate-500 dark:text-slate-300">
                  {tableHeaders.map((key) => (
                    <th key={key} className="px-4 py-3 font-medium">{titleCase(key)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
                {reportRows.map((row, index) => (
                  <tr key={index} className="bg-slate-50 dark:bg-[#0B1020]">
                    {tableHeaders.map((key) => (
                      <td key={key} className="max-w-[380px] px-4 py-4 text-slate-600 dark:text-slate-300">
                        <span className="line-clamp-2">{row[key]}</span>
                      </td>
                    ))}
                  </tr>
                ))}
                {!reportRows.length ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">No rows for the selected report.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
