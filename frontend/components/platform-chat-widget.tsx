"use client";

import { Bot, MessageCircle, Send, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import { AuditLogRecord, DashboardMetrics, MessageIncident, NodeRecord } from "@/lib/types";

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  createdAt: string;
};

type PlatformSnapshot = {
  metrics: DashboardMetrics | null;
  nodes: NodeRecord[];
  activeMessages: MessageIncident[];
  archivedMessages: MessageIncident[];
  auditLogs: AuditLogRecord[];
};

const PLATFORM_TERMS = [
  "alert",
  "alerts",
  "approval",
  "audit",
  "automation",
  "credential",
  "credentials",
  "dashboard",
  "disabled",
  "enabled",
  "execution",
  "failure",
  "fleet",
  "health",
  "healthy",
  "incident",
  "incidents",
  "infrastructure",
  "license",
  "message",
  "model",
  "network",
  "node",
  "nodes",
  "outage",
  "remediation",
  "remediations",
  "report",
  "reports",
  "resolved",
  "runner",
  "settings",
  "status",
  "system",
  "unhealthy",
];

const OUT_OF_SCOPE_PATTERNS = [
  /\b(recipe|recipes|cook|cooking|meal|bake|baking)\b/i,
  /\b(bird|birds|species|animal|animals|wildlife)\b/i,
  /\b(weather|sports|movie|movies|music|song|songs|travel)\b/i,
  /\b(write|generate|create|code|build)\s+(me\s+)?(a\s+)?(script|program|poem|story|essay)\b/i,
];

const DISALLOWED_GENERATION_PATTERN = /\b(write|generate|create|code|build)\s+(me\s+)?(a\s+)?(script|program|poem|story|essay)\b/i;

function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatList(items: string[], emptyMessage: string) {
  if (!items.length) {
    return emptyMessage;
  }
  return items.map((item) => `- ${item}`).join("\n");
}

function countBy<T>(items: T[], getKey: (item: T) => string | null | undefined) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = getKey(item) || "unknown";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

function summarizeCounts(counts: Record<string, number>) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries.map(([key, value]) => `${titleCase(key)}: ${value}`).join(", ") : "No data";
}

function isPlatformQuestion(prompt: string) {
  const normalized = prompt.toLowerCase();
  if (DISALLOWED_GENERATION_PATTERN.test(normalized)) {
    return false;
  }

  const explicitScopeBlock = OUT_OF_SCOPE_PATTERNS.some((pattern) => pattern.test(normalized));
  const mentionsPlatform = PLATFORM_TERMS.some((term) => normalized.includes(term));
  const operationalShortcuts = /\b(what'?s down|what is down|anything down|what failed|what changed|current state|current health|how are we looking)\b/i.test(normalized);

  if (explicitScopeBlock && !mentionsPlatform) {
    return false;
  }
  return mentionsPlatform || operationalShortcuts;
}

function buildOverview(snapshot: PlatformSnapshot) {
  const totalNodes = snapshot.metrics?.total_nodes ?? snapshot.nodes.length;
  const enabledNodes = snapshot.metrics?.enabled_nodes ?? snapshot.nodes.filter((node) => node.is_enabled).length;
  const activeIncidents = snapshot.metrics?.active_incidents ?? snapshot.activeMessages.filter((message) => message.incident.is_active).length;
  const resolvedIncidents = snapshot.metrics?.resolved_incidents ?? snapshot.archivedMessages.filter((message) => message.incident.resolved_at).length;
  const successfulRemediations = snapshot.metrics?.successful_remediations ?? 0;
  const averageResolution = snapshot.metrics?.average_resolution_minutes;
  const stateSummary = snapshot.metrics?.node_state_counts?.length
    ? snapshot.metrics.node_state_counts.map((item) => `${titleCase(item.label)}: ${item.value}`).join(", ")
    : summarizeCounts(countBy(snapshot.nodes, (node) => (node.is_enabled ? node.current_status : "disabled")));

  return [
    `Current platform snapshot: ${totalNodes} nodes tracked, ${enabledNodes} enabled, ${activeIncidents} active incidents, ${resolvedIncidents} resolved incidents, and ${successfulRemediations} successful remediations recorded.`,
    `Node state: ${stateSummary}.`,
    averageResolution === null || averageResolution === undefined
      ? "Average resolution time is not available yet."
      : `Average resolution time is ${averageResolution.toFixed(1)} minutes.`,
  ].join("\n");
}

function answerIncidentQuestion(snapshot: PlatformSnapshot) {
  const unhealthyNodes = snapshot.nodes.filter((node) => node.is_enabled && !["healthy", "ok", "online"].includes(node.current_status.toLowerCase()));
  const activeIncidentLines = snapshot.activeMessages
    .filter((message) => !message.incident.archived_at)
    .slice(0, 6)
    .map((message) => `${message.node.name}: ${message.incident.summary} (${titleCase(message.incident.status)}, ${titleCase(message.incident.severity)})`);
  const unhealthyLines = unhealthyNodes
    .slice(0, 6)
    .map((node) => `${node.name}: ${titleCase(node.current_status)}${node.last_check_at ? `, last checked ${new Date(node.last_check_at).toLocaleString()}` : ""}`);

  if (!activeIncidentLines.length && !unhealthyLines.length) {
    return "I do not see active incidents or unhealthy enabled nodes in the current RAVEN data.";
  }

  return [
    "Current outage and health view:",
    formatList(activeIncidentLines, "No active incidents are currently reported."),
    unhealthyLines.length ? "\nEnabled nodes outside healthy state:\n" + formatList(unhealthyLines, "") : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function answerNodeQuestion(snapshot: PlatformSnapshot) {
  const statusCounts = summarizeCounts(countBy(snapshot.nodes, (node) => (node.is_enabled ? node.current_status : "disabled")));
  const environmentCounts = summarizeCounts(countBy(snapshot.nodes, (node) => node.environment));
  const groupCounts = summarizeCounts(countBy(snapshot.nodes, (node) => node.group_name || "ungrouped"));
  const recentNodes = snapshot.nodes
    .slice()
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 5)
    .map((node) => `${node.name}: ${titleCase(node.current_status)} in ${node.environment}${node.group_name ? `, group ${node.group_name}` : ""}`);

  return [
    `Fleet status by node state: ${statusCounts}.`,
    `Environment distribution: ${environmentCounts}.`,
    `Grouping: ${groupCounts}.`,
    `Recent node records:\n${formatList(recentNodes, "No nodes are configured yet.")}`,
  ].join("\n");
}

function answerRemediationQuestion(snapshot: PlatformSnapshot) {
  const executions = [...snapshot.activeMessages, ...snapshot.archivedMessages].flatMap((message) =>
    message.executions.map((execution) => ({
      execution,
      nodeName: message.node.name,
      incidentSummary: message.incident.summary,
    })),
  );
  const recentExecutions = executions
    .slice()
    .sort((a, b) => new Date(b.execution.queued_at).getTime() - new Date(a.execution.queued_at).getTime())
    .slice(0, 6)
    .map(({ execution, nodeName }) => `${nodeName}: ${execution.proposal_title ?? "Command"} is ${titleCase(execution.status)}${execution.post_validation_status ? `, validation ${titleCase(execution.post_validation_status)}` : ""}`);

  return [
    `Successful remediations recorded: ${snapshot.metrics?.successful_remediations ?? executions.filter(({ execution }) => execution.status === "success").length}.`,
    `Execution status: ${snapshot.metrics?.execution_status_counts?.length ? snapshot.metrics.execution_status_counts.map((item) => `${titleCase(item.label)}: ${item.value}`).join(", ") : summarizeCounts(countBy(executions, ({ execution }) => execution.status))}.`,
    `Recent execution activity:\n${formatList(recentExecutions, "No execution tasks have been recorded yet.")}`,
  ].join("\n");
}

function answerAuditQuestion(snapshot: PlatformSnapshot) {
  const recentAudit = snapshot.auditLogs.slice(0, 8).map((log) => {
    const actor = log.actor_user_id ? ` by user ${log.actor_user_id}` : "";
    return `${new Date(log.created_at).toLocaleString()}: ${titleCase(log.entity_type)} ${titleCase(log.action)} (${log.entity_id})${actor}`;
  });
  return `Recent audit activity:\n${formatList(recentAudit, "No audit records are available.")}`;
}

function answerLicenseQuestion(snapshot: PlatformSnapshot) {
  const licenseEvents = snapshot.auditLogs.filter((log) => log.entity_type.toLowerCase().includes("license") || log.action.toLowerCase().includes("license"));
  if (!licenseEvents.length) {
    return "I do not see license-related events in the current audit stream. The Alerts page will surface license status events when they are available.";
  }
  return `Recent license events:\n${formatList(licenseEvents.slice(0, 5).map((log) => `${new Date(log.created_at).toLocaleString()}: ${titleCase(log.action)} (${log.entity_id})`), "No license events found.")}`;
}

function answerPrompt(prompt: string, snapshot: PlatformSnapshot) {
  if (!isPlatformQuestion(prompt)) {
    return "I can only answer questions about the RAVEN platform, monitored network/system state, deployed nodes, alerts, incidents, remediations, reports, credentials, and settings.";
  }

  const normalized = prompt.toLowerCase();
  if (/\b(outage|outages|incident|incidents|down|failed|failure|unhealthy|alert|alerts)\b/.test(normalized)) {
    return answerIncidentQuestion(snapshot);
  }
  if (/\b(remediation|remediations|execution|executions|command|approval|approved|automation|runner)\b/.test(normalized)) {
    return answerRemediationQuestion(snapshot);
  }
  if (/\b(audit|changed|change|activity|history)\b/.test(normalized)) {
    return answerAuditQuestion(snapshot);
  }
  if (/\b(license|licensing)\b/.test(normalized)) {
    return answerLicenseQuestion(snapshot);
  }
  if (/\b(node|nodes|fleet|infrastructure|network|environment|group|cluster|enabled|disabled|health|healthy|status)\b/.test(normalized)) {
    return answerNodeQuestion(snapshot);
  }

  return buildOverview(snapshot);
}

async function loadPlatformSnapshot(): Promise<PlatformSnapshot> {
  const [metrics, nodes, activeMessages, archivedMessages, auditLogs] = await Promise.all([
    apiFetch<DashboardMetrics>("/dashboard/metrics"),
    apiFetch<NodeRecord[]>("/nodes"),
    apiFetch<MessageIncident[]>("/messages"),
    apiFetch<MessageIncident[]>("/messages?archived=true"),
    apiFetch<AuditLogRecord[]>("/audit/logs"),
  ]);

  return { metrics, nodes, activeMessages, archivedMessages, auditLogs };
}

export function PlatformChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [snapshot, setSnapshot] = useState<PlatformSnapshot>({ metrics: null, nodes: [], activeMessages: [], archivedMessages: [], auditLogs: [] });
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Ask about RAVEN platform status, node health, active incidents, remediation activity, audit events, or license alerts.",
      createdAt: new Date().toISOString(),
    },
  ]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const hasState = useMemo(
    () => Boolean(snapshot.metrics || snapshot.nodes.length || snapshot.activeMessages.length || snapshot.archivedMessages.length || snapshot.auditLogs.length),
    [snapshot],
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;

    async function refreshSnapshot() {
      try {
        const nextSnapshot = await loadPlatformSnapshot();
        if (!cancelled) {
          setSnapshot(nextSnapshot);
        }
      } catch {
        if (!cancelled) {
          setMessages((current) => {
            const alreadyShown = current.some((message) => message.id === "snapshot-error");
            if (alreadyShown) {
              return current;
            }
            return [
              ...current,
              {
                id: "snapshot-error",
                role: "assistant",
                content: "I could not refresh platform state. Check your session and API connectivity, then try again.",
                createdAt: new Date().toISOString(),
              },
            ];
          });
        }
      }
    }

    void refreshSnapshot();
    const interval = window.setInterval(refreshSnapshot, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, open]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || loading) {
      return;
    }

    const userMessage: ChatMessage = {
      id: makeId("user"),
      role: "user",
      content: prompt,
      createdAt: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const freshSnapshot = await loadPlatformSnapshot();
      setSnapshot(freshSnapshot);
      const answer = answerPrompt(prompt, freshSnapshot);
      setMessages((current) => [
        ...current,
        {
          id: makeId("assistant"),
          role: "assistant",
          content: answer,
          createdAt: new Date().toISOString(),
        },
      ]);
    } catch {
      const fallbackAnswer = hasState
        ? answerPrompt(prompt, snapshot)
        : "I could not reach the platform APIs, so I cannot answer from current RAVEN state yet.";
      setMessages((current) => [
        ...current,
        {
          id: makeId("assistant"),
          role: "assistant",
          content: fallbackAnswer,
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {open ? (
        <section className="fixed bottom-24 left-4 right-4 z-50 overflow-hidden rounded-[1.5rem] border border-[#E5E7EB] bg-white shadow-none dark:border-slate-800 dark:bg-[#050814] sm:left-auto sm:w-[430px]" aria-label="RAVEN state chat">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#2B195D] text-white">
                <Bot className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[#111827] dark:text-white">RAVEN Assistant</p>
              </div>
            </div>
            <button
              type="button"
              className="grid h-9 w-9 place-items-center rounded-xl text-slate-500 transition hover:bg-panel hover:text-[#7C3AED] dark:text-slate-400 dark:hover:bg-[#0B1020]"
              aria-label="Close RAVEN state chat"
              onClick={() => setOpen(false)}
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="h-[420px] overflow-y-auto bg-[#F7F8FB] px-4 py-4 dark:bg-[#070B16]">
            <div className="space-y-3">
              {messages.map((message) => (
                <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[86%] whitespace-pre-line rounded-2xl px-4 py-3 text-sm leading-6 ${
                      message.role === "user"
                        ? "bg-[#7C3AED] text-white"
                        : "border border-slate-200 bg-white text-slate-700 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-200"
                    }`}
                  >
                    {message.content}
                    <p className={`mt-2 text-[11px] ${message.role === "user" ? "text-purple-100" : "text-slate-400 dark:text-slate-500"}`}>
                      {new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              ))}
              {loading ? (
                <div className="flex justify-start">
                  <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-400">
                    Checking current platform state...
                  </div>
                </div>
              ) : null}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <form className="flex items-end gap-2 border-t border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-[#050814]" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="raven-state-chat-input">
              Ask RAVEN state agent
            </label>
            <textarea
              id="raven-state-chat-input"
              rows={2}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              className="max-h-28 min-h-[44px] flex-1 resize-none rounded-2xl border border-[#E5E7EB] bg-[#F7F8FB] px-3 py-2 text-sm text-[#111827] outline-none transition placeholder:text-slate-400 focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              placeholder="Ask about nodes, incidents, remediations..."
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#7C3AED] text-white transition hover:bg-[#6D28D9] disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-800"
              aria-label="Send message"
            >
              <Send className="h-5 w-5" />
            </button>
          </form>
        </section>
      ) : null}

      <button
        type="button"
        className="fixed bottom-6 right-6 z-40 grid h-14 w-14 place-items-center rounded-full bg-[#7C3AED] text-white shadow-[0_18px_40px_rgba(124,58,237,0.35)] transition hover:-translate-y-0.5 hover:bg-[#6D28D9] dark:shadow-none"
        aria-label={open ? "Close RAVEN state chat" : "Open RAVEN state chat"}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    </>
  );
}
