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
      subtitle="Inspect the health history, incidents, recommendations, execution timeline, and assigned remediation profile for a single node."
    >
      <Link href="/" className="inline-flex rounded-full bg-panel px-4 py-2 text-sm font-medium text-slate-700">
        Back to dashboard
      </Link>

      {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900">{error}</p> : null}
      {!detail ? <p className="mt-6 text-sm text-slate-600">Loading node history...</p> : null}

      {detail ? (
        <div className="mt-6 grid gap-6">
          <section className="grid gap-6 lg:grid-cols-[1fr_1fr_1fr]">
            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Status</p>
              <div className="mt-3">
                <StatusBadge status={detail.node.is_enabled ? detail.node.current_status : "disabled"} />
              </div>
              <p className="mt-4 text-sm text-slate-600">{detail.node.host}{detail.node.port ? `:${detail.node.port}` : ""}</p>
              <p className="text-sm text-slate-600">{detail.node.url ?? "URL derived from host/port"}</p>
            </div>
            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Check config</p>
              <p className="mt-3 text-lg font-semibold">{detail.node.health_check_type}</p>
              <p className="mt-2 text-sm text-slate-600">Interval {detail.node.check_interval_seconds}s | Timeout {detail.node.timeout_seconds}s | Retry {detail.node.retry_count}</p>
              <p className="mt-2 text-sm text-slate-600">Expected {detail.node.expected_status_code}{detail.node.expected_response_contains ? ` + "${detail.node.expected_response_contains}"` : ""}</p>
            </div>
            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Remediation profile</p>
              <p className="mt-3 text-lg font-semibold">{detail.remediation_profile?.name ?? detail.node.remediation_profile}</p>
              <p className="mt-2 text-sm text-slate-600">{detail.remediation_profile?.description ?? "Profile metadata unavailable."}</p>
              <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{detail.node.execution_target}</p>
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <h3 className="text-xl font-semibold">Health check history</h3>
              <div className="mt-4 space-y-3">
                {detail.health_checks.map((check) => (
                  <div key={check.id} className="rounded-3xl bg-panel p-4">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={check.status} />
                      <span className="text-xs text-slate-500">{new Date(check.checked_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 text-sm text-slate-700">{check.error_detail ?? "Successful validation"}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">
                      Latency {check.latency_ms ?? "n/a"} ms | HTTP {check.http_status ?? "n/a"} | {check.error_type ?? "ok"}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <h3 className="text-xl font-semibold">Incident history</h3>
              <div className="mt-4 space-y-3">
                {detail.incidents.map((incident) => (
                  <div key={incident.id} className="rounded-3xl bg-panel p-4">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={incident.status} />
                      <span className="text-xs text-slate-500">{new Date(incident.started_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 text-sm font-semibold">{incident.summary}</p>
                    <p className="mt-2 text-sm text-slate-600">{incident.failure_type}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <h3 className="text-xl font-semibold">Recommendation history</h3>
              <div className="mt-4 space-y-3">
                {detail.recommendations.map((recommendation) => (
                  <div key={recommendation.id} className="rounded-3xl bg-panel p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{recommendation.model_name}</p>
                    <p className="mt-2 font-semibold">{recommendation.summary}</p>
                    <ul className="mt-3 space-y-2 text-sm text-slate-600">
                      {recommendation.troubleshooting_steps.map((step) => (
                        <li key={step}>- {step}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
              <h3 className="text-xl font-semibold">Execution history</h3>
              <div className="mt-4 space-y-3">
                {detail.executions.map((task) => (
                  <div key={task.id} className="rounded-3xl bg-panel p-4">
                    <div className="flex items-center justify-between gap-3">
                      <StatusBadge status={task.status} />
                      <span className="text-xs text-slate-500">{new Date(task.queued_at).toLocaleString()}</span>
                    </div>
                    <p className="mt-3 font-mono text-xs text-slate-700">{task.command_preview}</p>
                    <p className="mt-2 text-sm text-slate-600">Exit code {task.exit_code ?? "pending"} | Post-check {task.post_validation_status ?? "pending"}</p>
                    {task.output ? <pre className="mt-3 rounded-2xl bg-ink/95 p-3 text-xs text-white">{task.output}</pre> : null}
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
