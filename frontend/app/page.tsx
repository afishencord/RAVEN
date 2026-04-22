"use client";

import Link from "next/link";
import { useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { NodeForm } from "@/components/node-form";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { NodeRecord, RemediationProfile, User } from "@/lib/types";

const filters = ["all", "healthy", "degraded", "down", "disabled"] as const;

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [profiles, setProfiles] = useState<RemediationProfile[]>([]);
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
        Promise.all([
          apiFetch<NodeRecord[]>("/nodes"),
          apiFetch<RemediationProfile[]>("/profiles"),
        ])
          .then(([nodeData, profileData]) => {
            setNodes(nodeData);
            setProfiles(profileData);
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
      title="Node dashboard"
      subtitle="Track monitored application nodes, adjust health-check coverage, and manage remediation profiles from one control surface."
    >
      <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="text-xl font-semibold">Monitored nodes</h3>
              <p className="mt-1 text-sm text-slate-600">Filter by live status or disablement state. Click any node for full telemetry and remediation history.</p>
            </div>
            {user.role === "admin" ? (
              <button
                className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white"
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
                className={`rounded-full px-4 py-2 text-sm font-medium ${filter === entry ? "bg-ink text-white" : "bg-panel text-slate-700"}`}
                onClick={() => setFilter(entry)}
              >
                {entry}
              </button>
            ))}
          </div>

          {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900">{error}</p> : null}
          {loading ? <p className="mt-6 text-sm text-slate-600">Loading nodes...</p> : null}

          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-panel">
                <tr className="text-left text-slate-500">
                  <th className="px-4 py-3 font-medium">Node</th>
                  <th className="px-4 py-3 font-medium">Check</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last Check</th>
                  <th className="px-4 py-3 font-medium">Last Incident</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {filteredNodes.map((node) => (
                  <tr key={node.id}>
                    <td className="px-4 py-4">
                      <Link className="font-semibold text-ink hover:text-ember" href={`/nodes/${node.id}`}>
                        {node.name}
                      </Link>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500">{node.environment}</p>
                      <p className="mt-1 text-xs text-slate-500">{node.host}{node.health_check_path ? ` ${node.health_check_path}` : ""}</p>
                    </td>
                    <td className="px-4 py-4 text-slate-600">
                      <p>{node.health_check_type}</p>
                      <p className="text-xs">{node.url ?? node.execution_target}</p>
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={node.is_enabled ? node.current_status : "disabled"} />
                    </td>
                    <td className="px-4 py-4 text-slate-600">{node.last_check_at ? new Date(node.last_check_at).toLocaleString() : "Never"}</td>
                    <td className="px-4 py-4 text-slate-600">{node.last_incident_at ? new Date(node.last_incident_at).toLocaleString() : "None"}</td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        {user.role === "admin" ? (
                          <>
                            <button className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-700" onClick={() => { setEditing(node); setShowForm(true); }}>
                              Edit
                            </button>
                            <button className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-700" onClick={() => toggleNode(node)}>
                              {node.is_enabled ? "Disable" : "Enable"}
                            </button>
                            <button className="rounded-full bg-rose-100 px-3 py-2 text-xs font-semibold text-rose-800" onClick={() => deleteNode(node.id)}>
                              Remove
                            </button>
                          </>
                        ) : (
                          <span className="text-xs text-slate-500">Read only</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredNodes.length ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">
                      No nodes match the current filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
            <h3 className="text-xl font-semibold">Fleet snapshot</h3>
            <div className="mt-5 grid gap-4">
              {[
                ["Healthy", nodes.filter((node) => node.is_enabled && node.current_status === "healthy").length.toString()],
                ["Degraded", nodes.filter((node) => node.is_enabled && node.current_status === "degraded").length.toString()],
                ["Down", nodes.filter((node) => node.is_enabled && node.current_status === "down").length.toString()],
                ["Disabled", nodes.filter((node) => !node.is_enabled).length.toString()],
              ].map(([label, value]) => (
                <div key={label} className="rounded-3xl bg-panel px-5 py-4">
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-500">{label}</p>
                  <p className="mt-2 text-3xl font-semibold">{value}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
            <h3 className="text-xl font-semibold">Remediation profiles</h3>
            <div className="mt-4 space-y-4">
              {profiles.map((profile) => (
                <div key={profile.id} className="rounded-3xl bg-panel p-4">
                  <p className="font-semibold">{profile.name}</p>
                  <p className="mt-2 text-sm text-slate-600">{profile.description}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">{profile.allowed_action_keys.join(" | ")}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {showForm ? (
        <section className="mt-6 rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-panel backdrop-blur">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h3 className="text-xl font-semibold">{editing ? "Edit node" : "Add node"}</h3>
              <p className="text-sm text-slate-600">Node definitions drive monitoring cadence, AI context, and allowed remediation targeting.</p>
            </div>
          </div>
          <NodeForm profiles={profiles} initial={editing} onSubmit={saveNode} onCancel={() => { setShowForm(false); setEditing(null); }} />
        </section>
      ) : null}
    </AppShell>
  );
}
