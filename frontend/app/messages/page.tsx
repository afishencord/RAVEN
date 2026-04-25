"use client";

import { FormEvent, useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { ApprovalDecision, CommandProposal, ExecutionTask, IncidentNote, MessageIncident, Recommendation, User } from "@/lib/types";

type MessageView = "active" | "archived";
type TimelineEntry =
  | { id: string; at: string; kind: "incident"; message: MessageIncident }
  | { id: string; at: string; kind: "recommendation"; recommendation: Recommendation; isLatest: boolean; canAct: boolean; incidentId: number }
  | { id: string; at: string; kind: "execution"; execution: ExecutionTask }
  | { id: string; at: string; kind: "approval"; approval: ApprovalDecision }
  | { id: string; at: string; kind: "note"; note: IncidentNote };

function canOperate(user: User) {
  return user.role === "operator" || user.role === "admin";
}

function appearsResolved(message: MessageIncident) {
  if (message.incident.status === "investigating") {
    return false;
  }
  return (
    message.incident.status === "resolved" ||
    message.executions.some((execution) => execution.status === "success" && execution.post_validation_status === "healthy")
  );
}

function commandHasDecision(message: MessageIncident, command: CommandProposal) {
  return message.approvals.some((approval) => approval.action_key === command.proposal_id);
}

function recommendationHasApprovedDecision(message: MessageIncident, recommendation: Recommendation) {
  const proposalIds = new Set(recommendation.proposed_commands.map((command) => command.proposal_id));
  return message.approvals.some((approval) => approval.decision === "approved" && proposalIds.has(approval.action_key));
}

function buildTimeline(message: MessageIncident, operatorCanAct: boolean) {
  const latestId = message.latest_recommendation?.id;
  const commandActionsEnabled = operatorCanAct && !appearsResolved(message) && !message.incident.archived_at;
  const entries: TimelineEntry[] = [
    {
      id: `incident:${message.incident.id}`,
      at: message.incident.started_at,
      kind: "incident",
      message,
    },
  ];

  for (const recommendation of message.recommendations ?? []) {
    entries.push({
      id: `recommendation:${recommendation.id}`,
      at: recommendation.created_at,
      kind: "recommendation",
      recommendation,
      isLatest: recommendation.id === latestId,
      canAct: commandActionsEnabled && recommendation.id === latestId,
      incidentId: message.incident.id,
    });
  }

  for (const approval of message.approvals ?? []) {
    entries.push({
      id: `approval:${approval.id}`,
      at: approval.decided_at,
      kind: "approval",
      approval,
    });
  }

  for (const execution of message.executions ?? []) {
    entries.push({
      id: `execution:${execution.id}`,
      at: execution.finished_at ?? execution.started_at ?? execution.queued_at,
      kind: "execution",
      execution,
    });
  }

  for (const note of message.notes ?? []) {
    entries.push({
      id: `note:${note.id}`,
      at: note.created_at,
      kind: "note",
      note,
    });
  }

  return entries.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}

function latestActiveIncidentId(messages: MessageIncident[]) {
  const active = messages
    .filter((message) => !message.incident.archived_at)
    .sort((a, b) => new Date(b.incident.started_at).getTime() - new Date(a.incident.started_at).getTime());
  return active[0]?.incident.id ?? null;
}

export default function MessagesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<MessageIncident[]>([]);
  const [messageView, setMessageView] = useState<MessageView>("active");
  const [minimizedMessages, setMinimizedMessages] = useState<Set<number>>(() => new Set());
  const [manualMessageToggles, setManualMessageToggles] = useState<Set<number>>(() => new Set());
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  async function loadMessages(view: MessageView = messageView) {
    const payload = await apiFetch<MessageIncident[]>(`/messages${view === "archived" ? "?archived=true" : ""}`);
    setMessages(payload);
    setMinimizedMessages((current) => {
      const latestActiveId = view === "active" ? latestActiveIncidentId(payload) : null;
      const next = new Set<number>();
      for (const message of payload) {
        if (manualMessageToggles.has(message.incident.id)) {
          if (current.has(message.incident.id)) {
            next.add(message.incident.id);
          }
          continue;
        }
        if (message.incident.id !== latestActiveId) {
          next.add(message.incident.id);
        }
      }
      return next;
    });
    setLastSynced(new Date().toISOString());
  }

  useLiveRefresh(() => loadMessages(), {
    enabled: Boolean(user),
    intervalMs: 2500,
    onError: (err) => setError(err instanceof Error ? err.message : "Live message refresh failed"),
  });

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        loadMessages().catch((err) => setError(err instanceof Error ? err.message : "Failed to load messages"));
      });
    });
  }, [router]);

  function patchMessage(incidentId: number, updater: (message: MessageIncident) => MessageIncident) {
    setMessages((current) => current.map((message) => (message.incident.id === incidentId ? updater(message) : message)));
  }

  function toggleMinimized(incidentId: number) {
    setManualMessageToggles((current) => new Set(current).add(incidentId));
    setMinimizedMessages((current) => {
      const next = new Set(current);
      if (next.has(incidentId)) {
        next.delete(incidentId);
      } else {
        next.add(incidentId);
      }
      return next;
    });
  }

  async function changeMessageView(view: MessageView) {
    setMessageView(view);
    setError("");
    try {
      await loadMessages(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    }
  }

  async function refreshMessagesWithFollowUp() {
    await loadMessages();
    window.setTimeout(() => {
      loadMessages().catch((err) => setError(err instanceof Error ? err.message : "Failed to refresh messages"));
    }, 750);
  }

  async function postIncidentAction(incidentId: number, path: string, actionLabel: string, body: Record<string, unknown> = {}) {
    const actionKey = `${incidentId}:${path}:${actionLabel}`;
    setActiveAction(actionKey);
    setError("");
    try {
      await apiFetch(`/incidents/${incidentId}${path}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (path === "/close" && messageView === "active") {
        setMessages((current) => current.filter((message) => message.incident.id !== incidentId));
      }
      await refreshMessagesWithFollowUp();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
      await loadMessages();
    } finally {
      setActiveAction(null);
    }
  }

  async function setArchiveState(incidentId: number, archived: boolean) {
    await postIncidentAction(incidentId, archived ? "/archive" : "/unarchive", "manual");
    if (archived && messageView === "active") {
      setMessages((current) => current.filter((message) => message.incident.id !== incidentId));
    }
  }

  async function runAction(incidentId: number, path: string, proposalId: string) {
    if (path === "/acknowledge") {
      patchMessage(incidentId, (message) => ({
        ...message,
        incident: {
          ...message.incident,
          status: "acknowledged",
          acknowledged_at: new Date().toISOString(),
        },
      }));
    }
    await postIncidentAction(incidentId, path, proposalId, { proposal_id: proposalId });
  }

  async function rerunCheck(nodeId: number) {
    const actionKey = `node:${nodeId}:rerun`;
    setActiveAction(actionKey);
    setError("");
    try {
      const payload = await apiFetch<{ status: string; checked_at: string }>(`/nodes/${nodeId}/rerun-check`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMessages((current) =>
        current.map((message) =>
          message.node.id === nodeId
            ? {
                ...message,
                node: {
                  ...message.node,
                  current_status: payload.status,
                  last_check_at: payload.checked_at,
                },
              }
            : message,
        ),
      );
      await refreshMessagesWithFollowUp();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to re-run health check");
      await loadMessages();
    } finally {
      setActiveAction(null);
    }
  }

  async function submitNote(event: FormEvent<HTMLFormElement>, incidentId: number) {
    event.preventDefault();
    const note = noteDrafts[incidentId]?.trim();
    if (!note) {
      return;
    }
    const actionKey = `${incidentId}:/notes`;
    setActiveAction(actionKey);
    try {
      await apiFetch(`/incidents/${incidentId}/notes`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      setNoteDrafts((current) => ({ ...current, [incidentId]: "" }));
      await refreshMessagesWithFollowUp();
    } finally {
      setActiveAction(null);
    }
  }

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Internal message center"
    >
      {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

      <div className="mb-6 flex flex-col gap-3 rounded-[2rem] border border-[#E5E7EB] bg-white p-4 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">{messageView === "active" ? "Active remediation dialogues" : "Archived remediation dialogues"}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {messageView === "active" ? "Work failures as back-and-forth AI-assisted investigations." : "Closed and archived event threads remain available for review."}
          </p>
          <p className="mt-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            Live updates enabled{lastSynced ? ` | Synced ${new Date(lastSynced).toLocaleTimeString()}` : ""}
          </p>
        </div>
        <div className="flex rounded-full bg-panel p-1 dark:bg-[#0B1020]">
          {(["active", "archived"] as MessageView[]).map((view) => (
            <button
              key={view}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                messageView === view ? "bg-ink text-white dark:bg-ember" : "text-slate-600 hover:text-ink dark:text-slate-300 dark:hover:text-white"
              }`}
              onClick={() => changeMessageView(view)}
            >
              {view === "active" ? "Active" : "Archived"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6">
        {messages.map((message) => {
          const isMinimized = minimizedMessages.has(message.incident.id);
          const archiveAction = messageView === "active" ? "/archive" : "/unarchive";
          const archiveActionKey = `${message.incident.id}:${archiveAction}:manual`;
          const operatorCanAct = canOperate(user);
          const resolved = appearsResolved(message);
          const timeline = buildTimeline(message, operatorCanAct);

          return (
            <article key={message.incident.id} className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="text-2xl font-semibold">{message.node.name}</h3>
                    <StatusBadge status={message.incident.status} />
                    <StatusBadge status={message.node.is_enabled ? message.node.current_status : "disabled"} />
                  </div>
                  <p className="mt-3 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{message.incident.summary}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
                    Alerted {new Date(message.incident.started_at).toLocaleString()} | {message.incident.failure_type}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200"
                    onClick={() => toggleMinimized(message.incident.id)}
                  >
                    {isMinimized ? "Expand" : "Minimize"}
                  </button>
                  {operatorCanAct ? (
                    <button
                      className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-[#0B1020] dark:text-slate-200 dark:ring-slate-800"
                      disabled={activeAction === archiveActionKey}
                      onClick={() => setArchiveState(message.incident.id, messageView === "active")}
                    >
                      {activeAction === archiveActionKey ? "Updating..." : messageView === "active" ? "Archive" : "Restore"}
                    </button>
                  ) : null}
                  <button
                    className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200"
                    disabled={activeAction === `node:${message.node.id}:rerun`}
                    onClick={() => rerunCheck(message.node.id)}
                  >
                    {activeAction === `node:${message.node.id}:rerun` ? "Refreshing..." : "Re-run health check"}
                  </button>
                </div>
              </div>

              {!isMinimized ? (
                <>
                  <div className="mt-6 max-h-[680px] overflow-y-auto rounded-[2rem] border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]">
                    <div className="space-y-4">
                      {timeline.map((entry) => (
                        <TimelineBubble
                          key={entry.id}
                          entry={entry}
                          activeAction={activeAction}
                          message={message}
                          onRunAction={runAction}
                        />
                      ))}
                      {resolved && messageView === "active" && operatorCanAct ? (
                        <div className="grid gap-3 md:grid-cols-2">
                          <button
                            className="rounded-3xl border border-emerald-200 bg-emerald-50 p-5 text-left text-emerald-950 transition hover:border-emerald-400 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100"
                            disabled={activeAction === `${message.incident.id}:/close:manual`}
                            onClick={() => postIncidentAction(message.incident.id, "/close", "manual")}
                          >
                            <p className="text-sm font-semibold uppercase tracking-[0.2em]">Close incident</p>
                            <p className="mt-2 text-lg font-semibold">Validation is healthy</p>
                            <p className="mt-2 text-sm">Archive this thread and keep the remediation record available in past conversations.</p>
                          </button>
                          <button
                            className="rounded-3xl border border-amber-200 bg-amber-50 p-5 text-left text-amber-950 transition hover:border-amber-400 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
                            disabled={activeAction === `${message.incident.id}:/investigate-further:manual`}
                            onClick={() => postIncidentAction(message.incident.id, "/investigate-further", "manual")}
                          >
                            <p className="text-sm font-semibold uppercase tracking-[0.2em]">Investigate further</p>
                            <p className="mt-2 text-lg font-semibold">Start root cause analysis</p>
                            <p className="mt-2 text-sm">Keep the dialogue active and ask AI for evidence-driven follow-up commands.</p>
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <form className="mt-4 rounded-[2rem] border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]" onSubmit={(event) => submitNote(event, message.incident.id)}>
                    <label className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Operator message</label>
                    <div className="mt-3 flex flex-col gap-3 md:flex-row">
                      <textarea
                        value={noteDrafts[message.incident.id] ?? ""}
                        onChange={(event) => setNoteDrafts((current) => ({ ...current, [message.incident.id]: event.target.value }))}
                        className="min-h-20 flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-ember dark:border-slate-800 dark:bg-[#050814] dark:text-white"
                        placeholder="Add context for the next operator or AI-assisted investigation..."
                      />
                      <div className="flex flex-col gap-2 md:w-56">
                        {operatorCanAct ? (
                          <>
                            <button className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white dark:bg-ember" disabled={activeAction === `${message.incident.id}:/notes`}>
                              {activeAction === `${message.incident.id}:/notes` ? "Saving..." : "Add note"}
                            </button>
                            {!resolved && messageView === "active" ? (
                              <button
                                type="button"
                                className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-[#050814] dark:text-slate-200 dark:ring-slate-800"
                                disabled={activeAction === `${message.incident.id}:/recommendation/refresh:manual`}
                                onClick={() => runAction(message.incident.id, "/recommendation/refresh", "manual")}
                              >
                                {activeAction === `${message.incident.id}:/recommendation/refresh:manual` ? "Thinking..." : "Generate next AI step"}
                              </button>
                            ) : null}
                          </>
                        ) : (
                          <p className="text-xs text-slate-500 dark:text-slate-400">Read only</p>
                        )}
                      </div>
                    </div>
                  </form>
                </>
              ) : null}
            </article>
          );
        })}
        {!messages.length ? (
          <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-8 text-center text-sm text-slate-500 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:text-slate-400 dark:shadow-none">
            {messageView === "active" ? "No active remediation dialogues." : "No archived conversations yet."}
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

function TimelineBubble({
  entry,
  activeAction,
  message,
  onRunAction,
}: {
  entry: TimelineEntry;
  activeAction: string | null;
  message: MessageIncident;
  onRunAction: (incidentId: number, path: string, proposalId: string) => Promise<void>;
}) {
  if (entry.kind === "incident") {
    return (
      <div className="max-w-3xl rounded-3xl bg-white p-5 dark:bg-[#050814]">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">System alert</p>
        <p className="mt-2 text-lg font-semibold">{entry.message.incident.summary}</p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Failure type {entry.message.incident.failure_type} detected at {new Date(entry.message.incident.started_at).toLocaleString()}.
        </p>
      </div>
    );
  }

  if (entry.kind === "recommendation") {
    const approvedDecisionExists = recommendationHasApprovedDecision(message, entry.recommendation);
    const commandSetMinimized = !entry.isLatest || approvedDecisionExists;
    return (
      <div className="max-w-4xl rounded-3xl border border-purple-100 bg-white p-5 dark:border-purple-950 dark:bg-[#050814]">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs uppercase tracking-[0.2em] text-purple-700 dark:text-purple-300">AI recommendation</p>
          <StatusBadge status={entry.isLatest ? "latest" : "previous"} />
        </div>
        <p className="mt-3 text-lg font-semibold">{entry.recommendation.summary}</p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Classification: {entry.recommendation.suspected_issue_classification} | Model {entry.recommendation.model_name}
        </p>
        <ul className="mt-4 space-y-2 text-sm text-slate-600 dark:text-slate-300">
          {entry.recommendation.troubleshooting_steps.map((step) => (
            <li key={step}>- {step}</li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">{entry.recommendation.rationale}</p>

        {commandSetMinimized ? (
          <div className="mt-5 rounded-3xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]">
            <p className="text-sm font-semibold">Command cards minimized</p>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              {approvedDecisionExists ? "An operator approved a command from this recommendation. The execution output is shown below." : "A newer AI turn superseded this recommendation."}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {entry.recommendation.proposed_commands.map((command) => (
                <span key={command.proposal_id} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 dark:bg-[#050814] dark:text-slate-300 dark:ring-slate-800">
                  {command.title}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-5 space-y-3">
            {entry.recommendation.proposed_commands.map((command) => {
              const hasDecision = commandHasDecision(message, command);
              return (
                <div key={command.proposal_id} className="rounded-3xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">{command.title}</p>
                      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{command.rationale}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <StatusBadge status={command.execution_mode} />
                        <StatusBadge status={command.risk_level} />
                      </div>
                      <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{command.target_summary}</p>
                      <pre className="mt-3 overflow-auto rounded-2xl bg-ink p-3 text-xs text-white">{command.command}</pre>
                    </div>
                    {entry.canAct ? (
                      <div className="flex shrink-0 gap-2">
                        <button
                          className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white disabled:opacity-50 dark:bg-ember"
                          disabled={hasDecision || activeAction === `${entry.incidentId}:/approve:${command.proposal_id}`}
                          onClick={() => onRunAction(entry.incidentId, "/approve", command.proposal_id)}
                        >
                          {hasDecision ? "Decided" : activeAction === `${entry.incidentId}:/approve:${command.proposal_id}` ? "Queuing..." : "Approve"}
                        </button>
                        <button
                          className="rounded-full bg-rose-100 px-4 py-2 text-xs font-semibold text-rose-800 disabled:opacity-50 dark:border dark:border-rose-900 dark:bg-rose-950/70 dark:text-rose-300"
                          disabled={hasDecision}
                          onClick={() => onRunAction(entry.incidentId, "/reject", command.proposal_id)}
                        >
                          Reject
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  if (entry.kind === "approval") {
    return (
      <div className="ml-auto max-w-2xl rounded-3xl bg-ink p-4 text-white dark:bg-ember">
        <p className="text-xs uppercase tracking-[0.2em] text-white/70">Operator decision</p>
        <p className="mt-2 text-sm">
          {entry.approval.decision === "approved" ? "Approved" : "Rejected"} proposal {entry.approval.action_key}.
        </p>
        {entry.approval.note ? <p className="mt-2 text-sm text-white/80">{entry.approval.note}</p> : null}
      </div>
    );
  }

  if (entry.kind === "execution") {
    return (
      <div className="max-w-4xl rounded-3xl bg-slate-950 p-5 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-300">Command output</p>
          <StatusBadge status={entry.execution.status} />
        </div>
        <p className="mt-3 text-sm font-semibold">{entry.execution.proposal_title ?? entry.execution.proposal_id ?? "Approved command"}</p>
        <pre className="mt-3 overflow-auto rounded-2xl bg-black p-3 text-xs text-slate-100">{entry.execution.approved_command ?? entry.execution.command_preview}</pre>
        <p className="mt-3 text-sm text-slate-300">
          Exit code {entry.execution.exit_code ?? "pending"} | Post-check {entry.execution.post_validation_status ?? "pending"}
        </p>
        {entry.execution.output ? <pre className="mt-3 max-h-56 overflow-auto rounded-2xl bg-black p-3 text-xs text-slate-100">{entry.execution.output}</pre> : null}
      </div>
    );
  }

  return (
    <div className="ml-auto max-w-2xl rounded-3xl bg-white p-4 dark:bg-[#050814]">
      <p className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Operator note</p>
      <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{entry.note.note}</p>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{new Date(entry.note.created_at).toLocaleString()}</p>
    </div>
  );
}
