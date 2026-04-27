"use client";

import { startTransition, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { AuditLogRecord, MessageIncident, NodeRecord, User } from "@/lib/types";

type AlertCategory = "all" | "outage" | "resolution" | "license" | "node" | "audit";
type AlertSeverity = "critical" | "warning" | "info" | "success";
type AlertEvent = {
  id: string;
  at: string;
  category: Exclude<AlertCategory, "all">;
  severity: AlertSeverity;
  title: string;
  detail: string;
  source: string;
};

const categories: AlertCategory[] = ["all", "outage", "resolution", "license", "node", "audit"];

function toDateTimeInput(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function severityClass(severity: AlertSeverity) {
  if (severity === "critical") {
    return "bg-rose-100 text-rose-800 dark:bg-rose-950/70 dark:text-rose-300";
  }
  if (severity === "warning") {
    return "bg-amber-100 text-amber-800 dark:bg-amber-950/70 dark:text-amber-300";
  }
  if (severity === "success") {
    return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-300";
  }
  return "bg-slate-100 text-slate-700 dark:bg-[#0B1020] dark:text-slate-300";
}

function categoryIcon(category: AlertEvent["category"]) {
  if (category === "outage") {
    return AlertTriangle;
  }
  if (category === "resolution") {
    return CheckCircle2;
  }
  if (category === "license") {
    return ShieldCheck;
  }
  return Clock3;
}

function buildAlerts(messages: MessageIncident[], archivedMessages: MessageIncident[], auditLogs: AuditLogRecord[], nodes: NodeRecord[]) {
  const combinedMessages = [...messages, ...archivedMessages];
  const events: AlertEvent[] = [
    {
      id: "license:active",
      at: new Date().toISOString(),
      category: "license",
      severity: "success",
      title: "Enterprise license active",
      detail: "License validation is current for the local RAVEN deployment.",
      source: "License service",
    },
  ];

  for (const message of combinedMessages) {
    const nodeName = message.node?.name ?? `Node ${message.incident.node_id}`;
    events.push({
      id: `incident:${message.incident.id}:outage`,
      at: message.incident.started_at,
      category: "outage",
      severity: message.incident.is_active && !message.incident.archived_at ? "critical" : "warning",
      title: `${nodeName} outage detected`,
      detail: message.incident.summary,
      source: `Incident ${message.incident.id}`,
    });

    if (message.incident.resolved_at) {
      events.push({
        id: `incident:${message.incident.id}:resolution`,
        at: message.incident.resolved_at,
        category: "resolution",
        severity: "success",
        title: `${nodeName} outage resolved`,
        detail: `Resolution recorded for ${message.incident.failure_type}.`,
        source: `Incident ${message.incident.id}`,
      });
    }
  }

  for (const node of nodes) {
    if (!node.is_enabled || node.current_status === "healthy") {
      continue;
    }
    events.push({
      id: `node:${node.id}:${node.current_status}`,
      at: node.last_check_at ?? node.updated_at,
      category: "node",
      severity: node.current_status === "down" ? "critical" : "warning",
      title: `${node.name} is ${node.current_status}`,
      detail: `${node.environment} node at ${node.host}${node.port ? `:${node.port}` : ""}`,
      source: "Node monitor",
    });
  }

  for (const log of auditLogs) {
    events.push({
      id: `audit:${log.id}`,
      at: log.created_at,
      category: "audit",
      severity: "info",
      title: `${titleCase(log.entity_type)} ${titleCase(log.action)}`,
      detail: `Entity ${log.entity_id}${log.actor_user_id ? ` by user ${log.actor_user_id}` : ""}`,
      source: "Audit log",
    });
  }

  return events.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}

export default function AlertsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<MessageIncident[]>([]);
  const [archivedMessages, setArchivedMessages] = useState<MessageIncident[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [category, setCategory] = useState<AlertCategory>("all");
  const [fromDate, setFromDate] = useState(() => toDateTimeInput(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)));
  const [toDate, setToDate] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadAlerts() {
    const [active, archived, logs, nodeData] = await Promise.all([
      apiFetch<MessageIncident[]>("/messages"),
      apiFetch<MessageIncident[]>("/messages?archived=true"),
      apiFetch<AuditLogRecord[]>("/audit/logs"),
      apiFetch<NodeRecord[]>("/nodes"),
    ]);
    setMessages(active);
    setArchivedMessages(archived);
    setAuditLogs(logs);
    setNodes(nodeData);
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        loadAlerts()
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load alerts"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  useLiveRefresh(loadAlerts, {
    enabled: Boolean(user),
    intervalMs: 5000,
    onError: (err) => setError(err instanceof Error ? err.message : "Live alert refresh failed"),
  });

  const alertEvents = useMemo(() => buildAlerts(messages, archivedMessages, auditLogs, nodes), [messages, archivedMessages, auditLogs, nodes]);
  const filteredEvents = useMemo(() => {
    const fromTime = fromDate ? new Date(fromDate).getTime() : null;
    const toTime = toDate ? new Date(toDate).getTime() : null;
    return alertEvents.filter((event) => {
      const eventTime = new Date(event.at).getTime();
      return (
        (category === "all" || event.category === category) &&
        (fromTime === null || eventTime >= fromTime) &&
        (toTime === null || eventTime <= toTime)
      );
    });
  }, [alertEvents, category, fromDate, toDate]);

  if (!user) {
    return null;
  }

  return (
    <AppShell user={user} title="Alerts" showHeaderControls={false}>
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <h3 className="text-xl font-semibold">Notifications</h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{filteredEvents.length} visible events</p>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">From</span>
                <input
                  type="datetime-local"
                  value={fromDate}
                  onChange={(event) => setFromDate(event.target.value)}
                  className="h-10 rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">To</span>
                <input
                  type="datetime-local"
                  value={toDate}
                  onChange={(event) => setToDate(event.target.value)}
                  className="h-10 rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Category</span>
                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value as AlertCategory)}
                  className="h-10 rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                >
                  {categories.map((entry) => (
                    <option key={entry} value={entry}>
                      {titleCase(entry)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
          {loading ? <p className="mt-6 text-sm text-slate-600 dark:text-slate-300">Loading notifications...</p> : null}

          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-panel dark:bg-[#0B1020]">
                <tr className="text-left text-slate-500 dark:text-slate-300">
                  <th className="px-4 py-3 font-medium">Notification</th>
                  <th className="px-4 py-3 font-medium">Category</th>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
                {filteredEvents.map((event) => {
                  const Icon = categoryIcon(event.category);
                  return (
                    <tr key={event.id} className="bg-slate-50 dark:bg-[#0B1020]">
                      <td className="px-4 py-4">
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[#7C3AED] dark:bg-[#050814] dark:text-purple-300">
                            <Icon className="h-4 w-4" />
                          </div>
                          <div>
                            <p className="font-semibold text-ink dark:text-white">{event.title}</p>
                            <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{event.detail}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{titleCase(event.category)}</td>
                      <td className="px-4 py-4">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${severityClass(event.severity)}`}>{event.severity}</span>
                      </td>
                      <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{event.source}</td>
                      <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{new Date(event.at).toLocaleString()}</td>
                    </tr>
                  );
                })}
                {!filteredEvents.length ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                      No notifications match the current filters.
                    </td>
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
