"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, startTransition } from "react";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { NodeAutomationAssignments, NodeDetail, RemediationDefinition, User, ValidationDefinition } from "@/lib/types";

export default function NodeDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [validations, setValidations] = useState<ValidationDefinition[]>([]);
  const [remediations, setRemediations] = useState<RemediationDefinition[]>([]);
  const [assignments, setAssignments] = useState<NodeAutomationAssignments | null>(null);
  const [selectedValidationIds, setSelectedValidationIds] = useState<Set<number>>(() => new Set());
  const [selectedRemediationIds, setSelectedRemediationIds] = useState<Set<number>>(() => new Set());
  const [error, setError] = useState("");
  const [automationSaving, setAutomationSaving] = useState(false);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  async function refreshDetail() {
    const payload = await apiFetch<NodeDetail>(`/nodes/${params.id}/detail`);
    setDetail(payload);
    setLastSynced(new Date().toISOString());
  }

  async function loadAutomation() {
    const [validationData, remediationData, assignmentData] = await Promise.all([
      apiFetch<ValidationDefinition[]>("/validations"),
      apiFetch<RemediationDefinition[]>("/remediations"),
      apiFetch<NodeAutomationAssignments>(`/nodes/${params.id}/automation-assignments`),
    ]);
    setValidations(validationData);
    setRemediations(remediationData);
    setAssignments(assignmentData);
    setSelectedValidationIds(new Set(assignmentData.validations.map((item) => item.validation_id)));
    setSelectedRemediationIds(new Set(assignmentData.remediations.map((item) => item.remediation_id)));
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        Promise.all([refreshDetail(), loadAutomation()])
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load node detail"));
      });
    });
  }, [params.id, router]);

  useLiveRefresh(refreshDetail, {
    enabled: Boolean(user),
    intervalMs: 2500,
    onError: (err) => setError(err instanceof Error ? err.message : "Live node detail refresh failed"),
  });

  function toggleSelection(setter: (value: Set<number>) => void, current: Set<number>, id: number) {
    const next = new Set(current);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setter(next);
  }

  async function saveAutomationAssignments() {
    setAutomationSaving(true);
    setError("");
    try {
      const validationIds = Array.from(selectedValidationIds);
      const remediationIds = Array.from(selectedRemediationIds);
      const preservedEdges = (assignments?.edges ?? [])
        .filter((edge) => selectedValidationIds.has(edge.validation_id) && selectedRemediationIds.has(edge.remediation_id))
        .map((edge) => ({ validation_id: edge.validation_id, remediation_id: edge.remediation_id }));
      const edges = preservedEdges.length
        ? preservedEdges
        : validationIds.flatMap((validationId) => remediationIds.map((remediationId) => ({ validation_id: validationId, remediation_id: remediationId })));
      const payload = await apiFetch<NodeAutomationAssignments>(`/nodes/${params.id}/automation-assignments`, {
        method: "PUT",
        body: JSON.stringify({
          validation_ids: validationIds,
          remediation_ids: remediationIds,
          edges,
        }),
      });
      setAssignments(payload);
      setSelectedValidationIds(new Set(payload.validations.map((item) => item.validation_id)));
      setSelectedRemediationIds(new Set(payload.remediations.map((item) => item.remediation_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save automation assignments");
    } finally {
      setAutomationSaving(false);
    }
  }

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title={detail ? detail.node.name : "Node detail"}
      subtitle="Inspect health history, incident context, command recommendations, and execution timeline for a single node."
    >
      <Link href="/infrastructure" className="inline-flex rounded-full bg-panel px-4 py-2 text-sm font-medium text-slate-700 dark:bg-[#0B1020] dark:text-slate-200">
        Back to infrastructure
      </Link>
      <p className="mt-3 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
        Live updates enabled{lastSynced ? ` | Synced ${new Date(lastSynced).toLocaleTimeString()}` : ""}
      </p>

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

          <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h3 className="text-xl font-semibold">Automation assignments</h3>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Assigned validations must pass before RAVEN can ask the model to choose an assigned remediation.
                </p>
              </div>
              {user.role === "admin" ? (
                <button
                  type="button"
                  disabled={automationSaving}
                  className="h-10 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ember disabled:opacity-60 dark:bg-ember"
                  onClick={saveAutomationAssignments}
                >
                  {automationSaving ? "Saving..." : "Save assignments"}
                </button>
              ) : null}
            </div>
            {assignments ? (
              <div className="mt-5 grid gap-5 lg:grid-cols-2">
                <div className="rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
                  <div className="border-b border-slate-200 bg-panel px-4 py-3 dark:border-slate-800 dark:bg-[#0B1020]">
                    <p className="text-sm font-semibold">Validations</p>
                  </div>
                  <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {validations.map((validation) => {
                      const checked = selectedValidationIds.has(validation.id);
                      return (
                        <button
                          key={validation.id}
                          type="button"
                          disabled={user.role !== "admin"}
                          className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left transition hover:bg-panel disabled:cursor-default disabled:hover:bg-transparent dark:hover:bg-[#0B1020]"
                          onClick={() => toggleSelection(setSelectedValidationIds, selectedValidationIds, validation.id)}
                        >
                          <span>
                            <span className="block text-sm font-semibold">{validation.name}</span>
                            <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{validation.validation_type} | {validation.is_enabled ? "enabled" : "disabled"}</span>
                          </span>
                          <span className={`flex h-6 w-11 items-center rounded-full p-1 transition ${checked ? "bg-[#7C3AED]" : "bg-slate-200 dark:bg-slate-800"}`}>
                            <span className={`h-4 w-4 rounded-full bg-white transition ${checked ? "translate-x-5" : ""}`} />
                          </span>
                        </button>
                      );
                    })}
                    {!validations.length ? <p className="px-4 py-6 text-sm text-slate-500 dark:text-slate-400">No validations have been created.</p> : null}
                  </div>
                </div>
                <div className="rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
                  <div className="border-b border-slate-200 bg-panel px-4 py-3 dark:border-slate-800 dark:bg-[#0B1020]">
                    <p className="text-sm font-semibold">Remediations</p>
                  </div>
                  <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {remediations.map((remediation) => {
                      const checked = selectedRemediationIds.has(remediation.id);
                      return (
                        <button
                          key={remediation.id}
                          type="button"
                          disabled={user.role !== "admin"}
                          className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left transition hover:bg-panel disabled:cursor-default disabled:hover:bg-transparent dark:hover:bg-[#0B1020]"
                          onClick={() => toggleSelection(setSelectedRemediationIds, selectedRemediationIds, remediation.id)}
                        >
                          <span>
                            <span className="block text-sm font-semibold">{remediation.name}</span>
                            <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{remediation.risk_level} risk | {remediation.is_enabled ? "enabled" : "disabled"}</span>
                          </span>
                          <span className={`flex h-6 w-11 items-center rounded-full p-1 transition ${checked ? "bg-[#7C3AED]" : "bg-slate-200 dark:bg-slate-800"}`}>
                            <span className={`h-4 w-4 rounded-full bg-white transition ${checked ? "translate-x-5" : ""}`} />
                          </span>
                        </button>
                      );
                    })}
                    {!remediations.length ? <p className="px-4 py-6 text-sm text-slate-500 dark:text-slate-400">No remediations have been created.</p> : null}
                  </div>
                </div>
              </div>
            ) : (
              <p className="mt-5 text-sm text-slate-500 dark:text-slate-400">Loading automation assignments...</p>
            )}
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
