"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, startTransition } from "react";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { NodeDetail, User } from "@/lib/types";

export default function NodeDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        apiFetch<NodeDetail>(`/nodes/${params.id}/detail`)
          .then(setDetail)
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load node detail"));
      });
    });
  }, [params.id, router]);

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title={detail ? detail.node.name : "Node detail"}
      subtitle="Inspect health history, incident context, command recommendations, and execution timeline for a single node."
    >
      <Link href="/" className="inline-flex rounded-full bg-panel px-4 py-2 text-sm font-medium text-slate-700 dark:bg-[#0B1020] dark:text-slate-200">
        Back to dashboard
      </Link>

      {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
      {!detail ? <p className="mt-6 text-sm text-slate-600 dark:text-slate-300">Loading node history...</p> : null}

      {detail ? (
        <div className="mt-6 grid gap-6">
          <section className="grid gap-6 lg:grid-cols-[1fr_1fr_1fr]">
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Status</p>
              <div className="mt-3">
                <StatusBadge status={detail.node.is_enabled ? detail.node.current_status : "disabled"} />
              </div>
              <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">{detail.node.host}{detail.node.port ? `:${detail.node.port}` : ""}</p>
              <p className="text-sm text-slate-600 dark:text-slate-300">{detail.node.url ?? "URL derived from host/port"}</p>
            </div>
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Execution</p>
              <p className="mt-3 text-lg font-semibold">{detail.node.execution_mode}</p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{detail.node.execution_target}</p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{detail.credential ? `${detail.credential.name} (${detail.credential.kind})` : "No credential attached"}</p>
            </div>
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500 dark:text-slate-400">Node context</p>
              <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{detail.node.context_text ?? "No troubleshooting context configured."}</p>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Approved command policy</p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{detail.node.approved_command_policy ?? "No command policy configured."}</p>
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-xl font-semibold">Health check history</h3>
              <div className="mt-4 space-y-3">
                {detail.health_checks.map((check) => (
                  <div key={check.id} className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={check.status} />
                      <span className="text-xs text-slate-500 dark:text-slate-400">{new Date(check.checked_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 text-sm text-slate-700 dark:text-slate-200">{check.error_detail ?? "Successful validation"}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Latency {check.latency_ms ?? "n/a"} ms | HTTP {check.http_status ?? "n/a"} | {check.error_type ?? "ok"}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-xl font-semibold">Incident history</h3>
              <div className="mt-4 space-y-3">
                {detail.incidents.map((incident) => (
                  <div key={incident.id} className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={incident.status} />
                      <span className="text-xs text-slate-500 dark:text-slate-400">{new Date(incident.started_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 text-sm font-semibold">{incident.summary}</p>
                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{incident.failure_type}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-xl font-semibold">Recommendation history</h3>
              <div className="mt-4 space-y-3">
                {detail.recommendations.map((recommendation) => (
                  <div key={recommendation.id} className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{recommendation.model_name}</p>
                    <p className="mt-2 font-semibold">{recommendation.summary}</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                      {recommendation.troubleshooting_steps.map((step) => (
                        <li key={step}>- {step}</li>
                      ))}
                    </ul>
                    <div className="mt-4 space-y-3">
                      {recommendation.proposed_commands.map((command) => (
                        <div key={command.proposal_id} className="rounded-2xl bg-white p-3 dark:bg-[#050814]">
                          <p className="font-semibold">{command.title}</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{command.target_summary}</p>
                          <pre className="mt-3 rounded-2xl bg-ink p-3 text-xs text-white">{command.command}</pre>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
              <h3 className="text-xl font-semibold">Execution history</h3>
              <div className="mt-4 space-y-3">
                {detail.executions.map((task) => (
                  <div key={task.id} className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={task.status} />
                      <span className="text-xs text-slate-500 dark:text-slate-400">{new Date(task.queued_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 text-sm font-semibold">{task.proposal_title ?? task.proposal_id ?? "Approved command"}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{task.execution_mode} | {task.target}</p>
                    <pre className="mt-3 rounded-2xl bg-ink/95 p-3 text-xs text-white">{task.approved_command ?? task.command_preview}</pre>
                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Exit code {task.exit_code ?? "pending"} | Post-check {task.post_validation_status ?? "pending"}</p>
                    {task.output ? <pre className="mt-3 rounded-2xl bg-slate-950 p-3 text-xs text-white">{task.output}</pre> : null}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}
