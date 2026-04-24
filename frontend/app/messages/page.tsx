"use client";

import { FormEvent, useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { MessageIncident, User } from "@/lib/types";

type MessageView = "active" | "archived";

export default function MessagesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<MessageIncident[]>([]);
  const [messageView, setMessageView] = useState<MessageView>("active");
  const [minimizedMessages, setMinimizedMessages] = useState<Set<number>>(() => new Set());
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  async function loadMessages(view: MessageView = messageView) {
    const payload = await apiFetch<MessageIncident[]>(`/messages${view === "archived" ? "?archived=true" : ""}`);
    setMessages(payload);
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
    setMessages((current) =>
      current.map((message) => (message.incident.id === incidentId ? updater(message) : message)),
    );
  }

  function toggleMinimized(incidentId: number) {
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

  async function setArchiveState(incidentId: number, archived: boolean) {
    const path = archived ? "/archive" : "/unarchive";
    const actionKey = `${incidentId}:${path}:manual`;
    setActiveAction(actionKey);
    setError("");
    try {
      await apiFetch(`/incidents/${incidentId}${path}`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMessages((current) => current.filter((message) => message.incident.id !== incidentId));
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : (archived ? "Failed to archive message" : "Failed to restore message"));
      await loadMessages();
    } finally {
      setActiveAction(null);
    }
  }

  async function runAction(incidentId: number, path: string, proposalId: string) {
    const actionKey = `${incidentId}:${path}:${proposalId}`;
    setActiveAction(actionKey);
    setError("");
    try {
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
      await apiFetch(`/incidents/${incidentId}${path}`, {
        method: "POST",
        body: JSON.stringify({ proposal_id: proposalId }),
      });
      await refreshMessagesWithFollowUp();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
      await loadMessages();
    } finally {
      setActiveAction(null);
    }
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
      subtitle="Review outage threads, inspect AI-generated remediation guidance, and record human decisions before anything is executed."
    >
      {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

      <div className="mb-6 flex flex-col gap-3 rounded-[2rem] border border-[#E5E7EB] bg-white p-4 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">{messageView === "active" ? "Active event conversations" : "Archived conversations"}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {messageView === "active" ? "Current message center events are shown here." : "Past archived event threads remain available for review."}
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
                {user.role === "operator" || user.role === "admin" ? (
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
            <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_0.95fr]">
              <section className="rounded-3xl bg-panel p-5 dark:bg-[#0B1020]">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">AI summary</p>
                <p className="mt-3 text-lg font-semibold">{message.latest_recommendation?.summary ?? "No recommendation generated yet."}</p>
                <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                  Classification: {message.latest_recommendation?.suspected_issue_classification ?? "pending"} | Model {message.latest_recommendation?.model_name ?? "n/a"}
                </p>
                <div className="mt-5">
                  <p className="text-sm font-semibold">Troubleshooting steps</p>
                  <ul className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                    {(message.latest_recommendation?.troubleshooting_steps ?? []).map((step) => (
                      <li key={step}>- {step}</li>
                    ))}
                  </ul>
                </div>
                <p className="mt-5 text-sm text-slate-600 dark:text-slate-300">{message.latest_recommendation?.rationale}</p>
              </section>

              <section className="rounded-3xl bg-panel p-5 dark:bg-[#0B1020]">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Proposed command cards</p>
                <div className="mt-4 space-y-3">
                  {(message.latest_recommendation?.proposed_commands ?? []).map((command) => (
                    <div key={command.proposal_id} className="rounded-3xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#050814]">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold">{command.title}</p>
                          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{command.rationale}</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <StatusBadge status={command.execution_mode} />
                            <StatusBadge status={command.risk_level} />
                          </div>
                          <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{command.target_summary}</p>
                          <pre className="mt-3 rounded-2xl bg-ink p-3 text-xs text-white">{command.command}</pre>
                        </div>
                        {user.role === "operator" || user.role === "admin" ? (
                          <div className="flex shrink-0 gap-2">
                            <button
                              className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white dark:bg-ember"
                              disabled={activeAction === `${message.incident.id}:/approve:${command.proposal_id}`}
                              onClick={() => runAction(message.incident.id, "/approve", command.proposal_id)}
                            >
                              {activeAction === `${message.incident.id}:/approve:${command.proposal_id}` ? "Queuing..." : "Approve"}
                            </button>
                            <button
                              className="rounded-full bg-rose-100 px-4 py-2 text-xs font-semibold text-rose-800 dark:bg-rose-950/70 dark:text-rose-300 dark:border dark:border-rose-900"
                              onClick={() => runAction(message.incident.id, "/reject", command.proposal_id)}
                            >
                              Reject
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  {user.role === "operator" || user.role === "admin" ? (
                    <>
                      <button
                        className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-[#0B1020] dark:text-slate-200 dark:ring-slate-800"
                        disabled={activeAction === `${message.incident.id}:/acknowledge:manual`}
                        onClick={() => runAction(message.incident.id, "/acknowledge", "manual")}
                      >
                        {activeAction === `${message.incident.id}:/acknowledge:manual` ? "Updating..." : "Acknowledge"}
                      </button>
                      <button
                        className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 dark:bg-[#0B1020] dark:text-slate-200 dark:ring-slate-800"
                        disabled={activeAction === `${message.incident.id}:/recommendation/refresh:manual`}
                        onClick={() => runAction(message.incident.id, "/recommendation/refresh", "manual")}
                      >
                        {activeAction === `${message.incident.id}:/recommendation/refresh:manual` ? "Refreshing..." : "Refresh recommendation"}
                      </button>
                    </>
                  ) : null}
                </div>
              </section>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
              <section className="rounded-3xl bg-panel p-5 dark:bg-[#0B1020]">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Operator notes</p>
                <form className="mt-4" onSubmit={(event) => submitNote(event, message.incident.id)}>
                  <textarea
                    value={noteDrafts[message.incident.id] ?? ""}
                    onChange={(event) => setNoteDrafts((current) => ({ ...current, [message.incident.id]: event.target.value }))}
                    className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#050814] dark:text-white"
                    placeholder="Add a note for the next operator..."
                  />
                  {user.role === "operator" || user.role === "admin" ? (
                    <button className="mt-3 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white dark:bg-ember" disabled={activeAction === `${message.incident.id}:/notes`}>
                      {activeAction === `${message.incident.id}:/notes` ? "Saving..." : "Add note"}
                    </button>
                  ) : null}
                </form>
                <div className="mt-4 space-y-3">
                  {message.notes.map((note) => (
                    <div key={note.id} className="rounded-2xl bg-white p-3 text-sm text-slate-600 dark:bg-[#050814] dark:text-slate-300">
                      <p>{note.note}</p>
                      <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{new Date(note.created_at).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-3xl bg-panel p-5 dark:bg-[#0B1020]">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Execution history</p>
                <div className="mt-4 space-y-3">
                  {message.executions.length ? (
                    message.executions.map((execution) => (
                      <div key={execution.id} className="rounded-2xl bg-white p-4 dark:bg-[#050814]">
                        <div className="flex items-center justify-between gap-3">
                          <StatusBadge status={execution.status} />
                          <span className="text-xs text-slate-500 dark:text-slate-400">{new Date(execution.queued_at).toLocaleString()}</span>
                        </div>
                        <p className="mt-3 text-sm font-semibold">{execution.proposal_title ?? execution.proposal_id ?? "Approved command"}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{execution.execution_mode} | {execution.target}</p>
                        <pre className="mt-3 rounded-2xl bg-ink p-3 text-xs text-white">{execution.approved_command ?? execution.command_preview}</pre>
                        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Exit code {execution.exit_code ?? "pending"} | Post-check {execution.post_validation_status ?? "pending"}</p>
                        {execution.output ? <pre className="mt-3 rounded-2xl bg-slate-950 p-3 text-xs text-white">{execution.output}</pre> : null}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500 dark:text-slate-400">No execution tasks have been queued for this incident.</p>
                  )}
                </div>
              </section>
            </div>
              </>
            ) : null}
          </article>
          );
        })}
        {!messages.length ? (
          <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-8 text-center text-sm text-slate-500 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:text-slate-400 dark:shadow-none">
            {messageView === "active" ? "No active event conversations." : "No archived conversations yet."}
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
