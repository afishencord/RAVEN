"use client";

import { ChevronDown, ChevronRight, EyeOff, FolderPlus, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, startTransition, useEffect, useMemo, useState, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { NodeForm } from "@/components/node-form";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { CredentialRecord, NodeRecord, User } from "@/lib/types";

const filters = ["all", "healthy", "degraded", "down", "disabled"] as const;
const tabs = ["nodes", "fleet"] as const;

type InfrastructureTab = (typeof tabs)[number];
type NodeFolder = {
  name: string;
  nodes: NodeRecord[];
  status: string;
};

function nodeStatus(node: NodeRecord) {
  return node.is_enabled ? node.current_status : "disabled";
}

function folderStatus(nodes: NodeRecord[]) {
  const statuses = nodes.map(nodeStatus);
  if (statuses.every((status) => status === "disabled")) {
    return "disabled";
  }
  if (statuses.includes("down")) {
    return "down";
  }
  if (statuses.includes("degraded") || statuses.includes("disabled")) {
    return "degraded";
  }
  return "healthy";
}

function matchesFilter(node: NodeRecord, filter: (typeof filters)[number]) {
  if (filter === "all") {
    return true;
  }
  if (filter === "disabled") {
    return !node.is_enabled;
  }
  return node.is_enabled && node.current_status === filter;
}

function IconButton({ label, className, children, onClick }: { label: string; className?: string; children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={`grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-300 ${className ?? ""}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function FleetSnapshot({ nodes }: { nodes: NodeRecord[] }) {
  return (
    <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
      <h3 className="text-xl font-semibold">Fleet snapshot</h3>
      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
    </section>
  );
}

export function InfrastructurePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [credentials, setCredentials] = useState<CredentialRecord[]>([]);
  const [activeTab, setActiveTab] = useState<InfrastructureTab>("nodes");
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set());
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<number>>(() => new Set());
  const [groupName, setGroupName] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<NodeRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [grouping, setGrouping] = useState(false);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

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
            setLastSynced(new Date().toISOString());
          })
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load infrastructure"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  async function refreshNodes() {
    const nodeData = await apiFetch<NodeRecord[]>("/nodes");
    setNodes(nodeData);
    setLastSynced(new Date().toISOString());
  }

  useLiveRefresh(refreshNodes, {
    enabled: Boolean(user) && !showForm && !grouping,
    intervalMs: 3000,
    onError: (err) => setError(err instanceof Error ? err.message : "Live infrastructure refresh failed"),
  });

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
    setSelectedNodeIds((current) => {
      const next = new Set(current);
      next.delete(nodeId);
      return next;
    });
    await refreshNodes();
  }

  async function toggleNode(node: NodeRecord) {
    await apiFetch<NodeRecord>(`/nodes/${node.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !node.is_enabled }),
    });
    await refreshNodes();
  }

  async function updateSelectedGroups(nextGroupName: string | null) {
    const ids = Array.from(selectedNodeIds);
    if (!ids.length) {
      return;
    }
    setGrouping(true);
    setError("");
    try {
      await Promise.all(
        ids.map((nodeId) =>
          apiFetch<NodeRecord>(`/nodes/${nodeId}`, {
            method: "PUT",
            body: JSON.stringify({ group_name: nextGroupName }),
          }),
        ),
      );
      setSelectedNodeIds(new Set());
      setGroupName("");
      if (nextGroupName) {
        setExpandedFolders((current) => new Set(current).add(nextGroupName));
      }
      await refreshNodes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update node folder");
    } finally {
      setGrouping(false);
    }
  }

  const grouped = useMemo(() => {
    const folders = new Map<string, NodeRecord[]>();
    const looseNodes: NodeRecord[] = [];

    for (const node of nodes) {
      const trimmedGroup = node.group_name?.trim();
      if (!trimmedGroup) {
        looseNodes.push(node);
        continue;
      }
      folders.set(trimmedGroup, [...(folders.get(trimmedGroup) ?? []), node]);
    }

    const folderRows: NodeFolder[] = Array.from(folders.entries())
      .map(([name, folderNodes]) => ({
        name,
        nodes: folderNodes.sort((a, b) => a.name.localeCompare(b.name)),
        status: folderStatus(folderNodes),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));

    return {
      folders: folderRows,
      looseNodes: looseNodes.sort((a, b) => a.name.localeCompare(b.name)),
    };
  }, [nodes]);

  const visibleFolders = grouped.folders
    .map((folder) => ({ ...folder, visibleNodes: folder.nodes.filter((node) => matchesFilter(node, filter)) }))
    .filter((folder) => folder.visibleNodes.length);
  const visibleLooseNodes = grouped.looseNodes.filter((node) => matchesFilter(node, filter));
  const visibleCount = visibleLooseNodes.length + visibleFolders.reduce((sum, folder) => sum + folder.visibleNodes.length, 0);
  const selectedCount = selectedNodeIds.size;
  const canAdminister = user?.role === "admin";

  function toggleSelected(nodeId: number) {
    setSelectedNodeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }

  function toggleFolder(name: string) {
    setExpandedFolders((current) => {
      const next = new Set(current);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  function renderNodeRow(node: NodeRecord, nested = false) {
    return (
      <tr key={node.id} className={nested ? "bg-slate-50/70 dark:bg-[#090E1B]" : undefined}>
        {canAdminister ? (
          <td className="w-12 px-4 py-4">
            <input
              type="checkbox"
              checked={selectedNodeIds.has(node.id)}
              onChange={() => toggleSelected(node.id)}
              className="h-4 w-4 rounded border-slate-300 accent-ember"
              aria-label={`Select ${node.name}`}
            />
          </td>
        ) : null}
        <td className="px-4 py-4">
          <Link className="font-semibold text-ink hover:text-ember dark:text-white" href={`/nodes/${node.id}`}>
            {nested ? <span className="mr-2 text-slate-400">└</span> : null}
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
          <StatusBadge status={nodeStatus(node)} />
        </td>
        <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{node.last_check_at ? new Date(node.last_check_at).toLocaleString() : "Never"}</td>
        <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
          <p className="line-clamp-3 text-xs">{node.context_text ?? "No context configured."}</p>
        </td>
        <td className="px-4 py-4">
          <div className="flex flex-wrap gap-2">
            {canAdminister ? (
              <>
                <IconButton label={`Edit ${node.name}`} onClick={() => { setEditing(node); setShowForm(true); }}>
                  <Pencil className="h-4 w-4" />
                </IconButton>
                <IconButton label={`${node.is_enabled ? "Disable" : "Enable"} ${node.name}`} onClick={() => toggleNode(node)}>
                  <EyeOff className="h-4 w-4" />
                </IconButton>
                <IconButton label={`Remove ${node.name}`} className="hover:border-rose-500 hover:text-rose-600 dark:hover:border-rose-800 dark:hover:text-rose-300" onClick={() => deleteNode(node.id)}>
                  <Trash2 className="h-4 w-4" />
                </IconButton>
              </>
            ) : (
              <span className="text-xs text-slate-500 dark:text-slate-400">Read only</span>
            )}
          </div>
        </td>
      </tr>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Infrastructure"
      subtitle="Monitored nodes, execution routes, and fleet configuration"
      showHeaderControls={false}
    >
      <div className="space-y-6">
        <div className="border-b border-slate-200 dark:border-slate-800">
          <div className="flex flex-wrap gap-1">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`border-b-2 px-5 py-3 text-sm font-semibold capitalize transition ${
                  activeTab === tab
                    ? "border-[#7C3AED] text-[#7C3AED] dark:text-purple-300"
                    : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"
                }`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {activeTab === "nodes" ? (
          <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <h3 className="text-xl font-semibold">Monitored nodes</h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Live updates enabled{lastSynced ? ` | Synced ${new Date(lastSynced).toLocaleTimeString()}` : ""}
                </p>
              </div>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                {canAdminister ? (
                  <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-panel p-2 dark:border-slate-800 dark:bg-[#0B1020]">
                    <FolderPlus className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                    <input
                      value={groupName}
                      onChange={(event) => setGroupName(event.target.value)}
                      placeholder="Folder name"
                      className="h-9 w-40 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-ember dark:border-slate-800 dark:bg-[#050814] dark:text-white"
                    />
                    <button
                      type="button"
                      disabled={!selectedCount || !groupName.trim() || grouping}
                      className="h-9 rounded-xl bg-ink px-3 text-xs font-semibold text-white transition hover:bg-ember disabled:cursor-not-allowed disabled:opacity-50 dark:bg-ember"
                      onClick={() => updateSelectedGroups(groupName.trim())}
                    >
                      Group {selectedCount || ""}
                    </button>
                    <button
                      type="button"
                      disabled={!selectedCount || grouping}
                      className="h-9 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-700 transition hover:border-ember hover:text-ember disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
                      onClick={() => updateSelectedGroups(null)}
                    >
                      Ungroup
                    </button>
                  </div>
                ) : null}
                {canAdminister ? (
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
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
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
              <p className="text-sm text-slate-500 dark:text-slate-400">{visibleCount} visible nodes</p>
            </div>

            {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}
            {loading ? <p className="mt-6 text-sm text-slate-600 dark:text-slate-300">Loading nodes...</p> : null}

            <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-panel dark:bg-[#0B1020]">
                  <tr className="text-left text-slate-500 dark:text-slate-300">
                    {canAdminister ? <th className="w-12 px-4 py-3 font-medium" /> : null}
                    <th className="px-4 py-3 font-medium">Node</th>
                    <th className="px-4 py-3 font-medium">Execution</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Last Check</th>
                    <th className="px-4 py-3 font-medium">Context</th>
                    <th className="px-4 py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
                  {visibleFolders.map((folder) => {
                    const expanded = expandedFolders.has(folder.name);
                    return (
                      <Fragment key={`folder:${folder.name}`}>
                        <tr className="bg-slate-50 dark:bg-[#0B1020]">
                          {canAdminister ? <td className="px-4 py-4" /> : null}
                          <td className="px-4 py-4">
                            <button
                              type="button"
                              className="inline-flex items-center gap-2 font-semibold text-ink hover:text-ember dark:text-white"
                              onClick={() => toggleFolder(folder.name)}
                            >
                              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              {folder.name}
                            </button>
                            <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{folder.nodes.length} nodes</p>
                          </td>
                          <td className="px-4 py-4 text-slate-600 dark:text-slate-300">Cluster folder</td>
                          <td className="px-4 py-4">
                            <StatusBadge status={folder.status} />
                          </td>
                          <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
                            {folder.nodes.some((node) => node.last_check_at)
                              ? new Date(Math.max(...folder.nodes.map((node) => node.last_check_at ? new Date(node.last_check_at).getTime() : 0))).toLocaleString()
                              : "Never"}
                          </td>
                          <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
                            <p className="text-xs">{folder.visibleNodes.length} matching nodes in current filter</p>
                          </td>
                          <td className="px-4 py-4">
                            <button
                              type="button"
                              className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-700 dark:bg-[#050814] dark:text-slate-200"
                              onClick={() => toggleFolder(folder.name)}
                            >
                              {expanded ? "Collapse" : "Expand"}
                            </button>
                          </td>
                        </tr>
                        {expanded ? folder.visibleNodes.map((node) => renderNodeRow(node, true)) : null}
                      </Fragment>
                    );
                  })}
                  {visibleLooseNodes.map((node) => renderNodeRow(node))}
                  {!visibleCount ? (
                    <tr>
                      <td colSpan={canAdminister ? 7 : 6} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                        No nodes match the current filter.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <FleetSnapshot nodes={nodes} />
        )}
      </div>

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
