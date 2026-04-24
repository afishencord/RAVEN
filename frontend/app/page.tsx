"use client";

import Link from "next/link";
import { useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { NodeForm } from "@/components/node-form";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { CredentialRecord, NodeRecord, User } from "@/lib/types";

const filters = ["all", "healthy", "degraded", "down", "disabled"] as const;

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [credentials, setCredentials] = useState<CredentialRecord[]>([]);
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<NodeRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        const requests: Promise<unknown>[] = [apiFetch<NodeRecord[]>("/nodes")];
        if (session.role === "admin") {
          requests.push(apiFetch<CredentialRecord[]>("/credentials"));
        }
        Promise.all(requests)
          .then(([nodeData, credentialData]) => {
            setNodes(nodeData as NodeRecord[]);
            setCredentials((credentialData as CredentialRecord[]) ?? []);
          })
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load dashboard"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  async function refreshNodes() {
    const nodeData = await apiFetch<NodeRecord[]>("/nodes");
    setNodes(nodeData);
  }

  async function saveNode(payload: Record<string, unknown>) {
    const path = editing ? `/nodes/${editing.id}` : "/nodes";
    const method = editing ? "PUT" : "POST";
    await apiFetch<NodeRecord>(path, { method, body: JSON.stringify(payload) });
    setShowForm(false);
    setEditing(null);
    await refreshNodes();
  }

  async function deleteNode(nodeId: number) {
    if (!window.confirm("Delete this node?")) {
      return;
    }
    await apiFetch(`/nodes/${nodeId}`, { method: "DELETE" });
    await refreshNodes();
  }

  async function toggleNode(node: NodeRecord) {
    await apiFetch<NodeRecord>(`/nodes/${node.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !node.is_enabled }),
    });
    await refreshNodes();
  }

  const filteredNodes = nodes.filter((node) => {
    if (filter === "all") {
      return true;
    }
    if (filter === "disabled") {
      return !node.is_enabled;
    }
    return node.is_enabled && node.current_status === filter;
  });

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Dashboard"
      subtitle="Real-time overview of your enterprise network operations"
    >
      <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <h3 className="text-xl font-semibold">Monitored nodes</h3>
            {user.role === "admin" ? (
              <button
                className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember"
                onClick={() => {
                  setEditing(null);
                  setShowForm(true);
                }}
              >
                Add node
              </button>
            ) : null}
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {filters.map((entry) => (
              <button
                key={entry}
                className={`rounded-full px-4 py-2 text-sm font-medium ${filter === entry ? "bg-ink text-white dark:bg-ember" : "bg-panel text-slate-700 dark:bg-[#0B1020] dark:text-slate-200"}`}
                onClick={() => setFilter(entry)}
              >
                {entry}
              </button>
            ))}
          </div>

          {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
          {loading ? <p className="mt-6 text-sm text-slate-600 dark:text-slate-300">Loading nodes...</p> : null}

          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-panel dark:bg-[#0B1020]">
                <tr className="text-left text-slate-500 dark:text-slate-300">
                  <th className="px-4 py-3 font-medium">Node</th>
                  <th className="px-4 py-3 font-medium">Execution</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last Check</th>
                  <th className="px-4 py-3 font-medium">Context</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
                {filteredNodes.map((node) => (
                  <tr key={node.id}>
                    <td className="px-4 py-4">
                      <Link className="font-semibold text-ink hover:text-ember dark:text-white" href={`/nodes/${node.id}`}>
                        {node.name}
                      </Link>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{node.environment}</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{node.host}{node.port ? `:${node.port}` : ""}</p>
                    </td>
                    <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
                      <p className="font-medium">{node.execution_mode}</p>
                      <p className="text-xs">{node.execution_target}</p>
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={node.is_enabled ? node.current_status : "disabled"} />
                    </td>
                    <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{node.last_check_at ? new Date(node.last_check_at).toLocaleString() : "Never"}</td>
                    <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
                      <p className="line-clamp-3 text-xs">{node.context_text ?? "No context configured."}</p>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        {user.role === "admin" ? (
                          <>
                            <button className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200" onClick={() => { setEditing(node); setShowForm(true); }}>
                              Edit
                            </button>
                            <button className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200" onClick={() => toggleNode(node)}>
                              {node.is_enabled ? "Disable" : "Enable"}
                            </button>
                            <button className="rounded-full bg-rose-100 px-3 py-2 text-xs font-semibold text-rose-800 dark:bg-rose-950/70 dark:text-rose-300 dark:border dark:border-rose-900" onClick={() => deleteNode(node.id)}>
                              Remove
                            </button>
                          </>
                        ) : (
                          <span className="text-xs text-slate-500 dark:text-slate-400">Read only</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredNodes.length ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                      No nodes match the current filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
            <h3 className="text-xl font-semibold">Fleet snapshot</h3>
            <div className="mt-5 grid gap-4">
              {[
                ["Runner Mode", nodes.filter((node) => node.execution_mode === "runner").length.toString()],
                ["Agent Mode", nodes.filter((node) => node.execution_mode === "agent").length.toString()],
                ["With Context", nodes.filter((node) => node.context_text?.trim()).length.toString()],
                ["With Credentials", nodes.filter((node) => node.credential_id).length.toString()],
              ].map(([label, value]) => (
                <div key={label} className="rounded-3xl bg-panel px-5 py-4 dark:bg-[#0B1020]">
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">{label}</p>
                  <p className="mt-2 text-3xl font-semibold">{value}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
            <h3 className="text-xl font-semibold">Execution modes</h3>
            <div className="mt-4 space-y-4">
              <div className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                <p className="font-semibold">Runner</p>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Centralized execution through `raven-runner` using local, SSH, or API dispatch.</p>
              </div>
              <div className="rounded-3xl bg-panel p-4 dark:bg-[#0B1020]">
                <p className="font-semibold">Agent</p>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Remote command execution through a node-local agent endpoint using approved command cards.</p>
              </div>
              {user.role === "admin" ? (
                <Link href="/credentials" className="inline-flex rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white dark:bg-ember">
                  Manage credentials
                </Link>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {showForm ? (
        <section className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/55 px-4 py-8 ">
          <div className="max-h-[calc(100vh-4rem)] w-full max-w-5xl overflow-auto rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
            <div className="mb-5 flex items-center justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold">{editing ? "Edit node" : "Add node"}</h3>
                <p className="text-sm text-slate-600 dark:text-slate-300">Node definitions drive troubleshooting context, command policy, and execution routing.</p>
              </div>
              <button
                className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200"
                onClick={() => {
                  setShowForm(false);
                  setEditing(null);
                }}
              >
                Close
              </button>
            </div>
            <NodeForm credentials={credentials} initial={editing} onSubmit={saveNode} onCancel={() => { setShowForm(false); setEditing(null); }} />
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
