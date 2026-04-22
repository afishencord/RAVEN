"use client";

import { FormEvent, useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { MessageIncident, User } from "@/lib/types";

export default function MessagesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<MessageIncident[]>([]);
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [error, setError] = useState("");

  async function loadMessages() {
    const payload = await apiFetch<MessageIncident[]>("/messages");
    setMessages(payload);
  }

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

  async function runAction(incidentId: number, path: string, body?: Record<string, unknown>) {
    await apiFetch(`/incidents/${incidentId}${path}`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
    await loadMessages();
  }

  async function rerunCheck(nodeId: number) {
    await apiFetch(`/nodes/${nodeId}/rerun-check`, { method: "POST", body: JSON.stringify({}) });
    await loadMessages();
  }

  async function submitNote(event: FormEvent<HTMLFormElement>, incidentId: number) {
    event.preventDefault();
    const note = noteDrafts[incidentId]?.trim();
    if (!note) {
      return;
    }
    await runAction(incidentId, "/notes", { note });
    setNoteDrafts((current) => ({ ...current, [incidentId]: "" }));
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
      {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900">{error}</p> : null}

      <div className="grid gap-6">
        {messages.map((message) => (
          <article key={message.incident.id} className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-2xl font-semibold">{message.node.name}</h3>
                  <StatusBadge status={message.incident.status} />
                  <StatusBadge status={message.node.is_enabled ? message.node.current_status : "disabled"} />
                </div>
                <p className="mt-3 max-w-3xl text-sm text-slate-600">{message.incident.summary}</p>
                <p className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500">
                  Alerted {new Date(message.incident.started_at).toLocaleString()} | {message.incident.failure_type}
                </p>
              </div>
              <button className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700" onClick={() => rerunCheck(message.node.id)}>
                Re-run health check
              </button>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_0.95fr]">
              <section className="rounded-3xl bg-panel p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">AI summary</p>
                <p className="mt-3 text-lg font-semibold">{message.latest_recommendation?.summary ?? "No recommendation generated yet."}</p>
                <p className="mt-3 text-sm text-slate-600">
                  Classification: {message.latest_recommendation?.suspected_issue_classification ?? "pending"} | Model {message.latest_recommendation?.model_name ?? "n/a"}
                </p>
                <div className="mt-5">
                  <p className="text-sm font-semibold">Troubleshooting steps</p>
                  <ul className="mt-3 space-y-2 text-sm text-slate-600">
                    {(message.latest_recommendation?.troubleshooting_steps ?? []).map((step) => (
                      <li key={step}>- {step}</li>
                    ))}
                  </ul>
                </div>
                <p className="mt-5 text-sm text-slate-600">{message.latest_recommendation?.rationale}</p>
              </section>

              <section className="rounded-3xl bg-panel p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Recommended remediation steps</p>
                <div className="mt-4 space-y-3">
                  {(message.latest_recommendation?.proposed_actions ?? []).map((action) => (
                    <div key={action.action_key} className="rounded-3xl border border-slate-200 bg-white p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="font-semibold">{action.title}</p>
                          <p className="mt-2 text-sm text-slate-600">{action.reason}</p>
                          <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{action.action_key}</p>
                        </div>
                        {user.role === "operator" || user.role === "admin" ? (
                          <div className="flex shrink-0 gap-2">
                            <button className="rounded-full bg-ink px-4 py-2 text-xs font-semibold text-white" onClick={() => runAction(message.incident.id, "/approve", { action_key: action.action_key })}>
                              Approve
                            </button>
                            <button className="rounded-full bg-rose-100 px-4 py-2 text-xs font-semibold text-rose-800" onClick={() => runAction(message.incident.id, "/reject", { action_key: action.action_key })}>
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
                      <button className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200" onClick={() => runAction(message.incident.id, "/acknowledge")}>
                        Acknowledge
                      </button>
                      <button className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-200" onClick={() => runAction(message.incident.id, "/recommendation/refresh")}>
                        Refresh recommendation
                      </button>
                    </>
                  ) : null}
                </div>
              </section>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
              <section className="rounded-3xl bg-panel p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Operator notes</p>
                <form className="mt-4" onSubmit={(event) => submitNote(event, message.incident.id)}>
                  <textarea
                    value={noteDrafts[message.incident.id] ?? ""}
                    onChange={(event) => setNoteDrafts((current) => ({ ...current, [message.incident.id]: event.target.value }))}
                    className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember"
                    placeholder="Add a note for the next operator..."
                  />
                  {user.role === "operator" || user.role === "admin" ? (
                    <button className="mt-3 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">Add note</button>
                  ) : null}
                </form>
                <div className="mt-4 space-y-3">
                  {message.notes.map((note) => (
                    <div key={note.id} className="rounded-2xl bg-white p-3 text-sm text-slate-600">
                      <p>{note.note}</p>
                      <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{new Date(note.created_at).toLocaleString()}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-3xl bg-panel p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Execution history</p>
                <div className="mt-4 space-y-3">
                  {message.executions.length ? (
                    message.executions.map((execution) => (
                      <div key={execution.id} className="rounded-2xl bg-white p-4">
                        <div className="flex items-center justify-between gap-3">
                          <StatusBadge status={execution.status} />
                          <span className="text-xs text-slate-500">{new Date(execution.queued_at).toLocaleString()}</span>
                        </div>
                        <p className="mt-3 font-mono text-xs text-slate-700">{execution.command_preview}</p>
                        <p className="mt-2 text-sm text-slate-600">Exit code {execution.exit_code ?? "pending"} | Post-check {execution.post_validation_status ?? "pending"}</p>
                        {execution.output ? <pre className="mt-3 rounded-2xl bg-ink p-3 text-xs text-white">{execution.output}</pre> : null}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate-500">No execution tasks have been queued for this incident.</p>
                  )}
                </div>
              </section>
            </div>
          </article>
        ))}
      </div>
    </AppShell>
  );
}
