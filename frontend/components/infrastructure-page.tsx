"use client";

import { ChevronDown, ChevronRight, EyeOff, FolderPlus, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, startTransition, useEffect, useMemo, useState, type DragEvent, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { NodeForm } from "@/components/node-form";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { useLiveRefresh } from "@/lib/live-updates";
import { CredentialRecord, NodeAutomationAssignments, NodeAutomationEdgeInput, NodeGroupRecord, NodeRecord, RemediationDefinition, User, ValidationDefinition } from "@/lib/types";

const filters = ["all", "healthy", "degraded", "down", "disabled"] as const;
const tabs = ["nodes", "fleet"] as const;

type InfrastructureTab = (typeof tabs)[number];
type NodeFolder = {
  id?: number;
  name: string;
  nodes: NodeRecord[];
  visibleNodes: NodeRecord[];
  status: string;
};

function nodeStatus(node: NodeRecord) {
  return node.is_enabled ? node.current_status : "disabled";
}

function folderStatus(nodes: NodeRecord[]) {
  if (!nodes.length) {
    return "empty";
  }
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
  const [nodeGroups, setNodeGroups] = useState<NodeGroupRecord[]>([]);
  const [credentials, setCredentials] = useState<CredentialRecord[]>([]);
  const [validations, setValidations] = useState<ValidationDefinition[]>([]);
  const [remediations, setRemediations] = useState<RemediationDefinition[]>([]);
  const [formValidationIds, setFormValidationIds] = useState<number[]>([]);
  const [formRemediationIds, setFormRemediationIds] = useState<number[]>([]);
  const [formAutomationEdges, setFormAutomationEdges] = useState<NodeAutomationEdgeInput[]>([]);
  const [activeTab, setActiveTab] = useState<InfrastructureTab>("nodes");
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set());
  const [draggingNodeId, setDraggingNodeId] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<NodeRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [movingNode, setMovingNode] = useState(false);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  async function refreshInfrastructure() {
    const [nodeData, groupData] = await Promise.all([
      apiFetch<NodeRecord[]>("/nodes"),
      apiFetch<NodeGroupRecord[]>("/node-groups"),
    ]);
    setNodes(nodeData);
    setNodeGroups(groupData);
    setLastSynced(new Date().toISOString());
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        const requests: Promise<unknown>[] = [apiFetch<NodeRecord[]>("/nodes"), apiFetch<NodeGroupRecord[]>("/node-groups")];
        if (session.role === "admin") {
          requests.push(apiFetch<CredentialRecord[]>("/credentials"));
          requests.push(apiFetch<ValidationDefinition[]>("/validations"));
          requests.push(apiFetch<RemediationDefinition[]>("/remediations"));
        }
        Promise.all(requests)
          .then(([nodeData, groupData, credentialData, validationData, remediationData]) => {
            setNodes(nodeData as NodeRecord[]);
            setNodeGroups(groupData as NodeGroupRecord[]);
            setCredentials((credentialData as CredentialRecord[]) ?? []);
            setValidations((validationData as ValidationDefinition[]) ?? []);
            setRemediations((remediationData as RemediationDefinition[]) ?? []);
            setLastSynced(new Date().toISOString());
          })
          .catch((err) => setError(err instanceof Error ? err.message : "Failed to load infrastructure"))
          .finally(() => setLoading(false));
      });
    });
  }, [router]);

  useLiveRefresh(refreshInfrastructure, {
    enabled: Boolean(user) && !showForm && !movingNode && !creatingFolder,
    intervalMs: 3000,
    onError: (err) => setError(err instanceof Error ? err.message : "Live infrastructure refresh failed"),
  });

  async function saveNode(payload: Record<string, unknown>) {
    const validationIds = (payload.automation_validation_ids as number[] | undefined) ?? [];
    const remediationIds = (payload.automation_remediation_ids as number[] | undefined) ?? [];
    const automationEdges = (payload.automation_edges as NodeAutomationEdgeInput[] | undefined) ?? [];
    const { automation_validation_ids: _validationIds, automation_remediation_ids: _remediationIds, automation_edges: _automationEdges, ...nodePayload } = payload;
    const path = editing ? `/nodes/${editing.id}` : "/nodes";
    const method = editing ? "PUT" : "POST";
    const saved = await apiFetch<NodeRecord>(path, { method, body: JSON.stringify(nodePayload) });
    if (canAdminister) {
      await apiFetch<NodeAutomationAssignments>(`/nodes/${saved.id}/automation-assignments`, {
        method: "PUT",
        body: JSON.stringify({ validation_ids: validationIds, remediation_ids: remediationIds, edges: automationEdges }),
      });
    }
    setShowForm(false);
    setEditing(null);
    setFormValidationIds([]);
    setFormRemediationIds([]);
    setFormAutomationEdges([]);
    await refreshInfrastructure();
  }

  async function openEditNode(node: NodeRecord) {
    setEditing(node);
    setError("");
    if (canAdminister) {
      try {
        const assignments = await apiFetch<NodeAutomationAssignments>(`/nodes/${node.id}/automation-assignments`);
        setFormValidationIds(assignments.validations.map((item) => item.validation_id));
        setFormRemediationIds(assignments.remediations.map((item) => item.remediation_id));
        setFormAutomationEdges((assignments.edges ?? []).map((edge) => ({ validation_id: edge.validation_id, remediation_id: edge.remediation_id })));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load automation assignments");
        setFormValidationIds([]);
        setFormRemediationIds([]);
        setFormAutomationEdges([]);
      }
    }
    setShowForm(true);
  }

  function openCreateNode() {
    setEditing(null);
    setFormValidationIds([]);
    setFormRemediationIds([]);
    setFormAutomationEdges([]);
    setShowForm(true);
  }

  async function deleteNode(nodeId: number) {
    if (!window.confirm("Delete this node?")) {
      return;
    }
    await apiFetch(`/nodes/${nodeId}`, { method: "DELETE" });
    await refreshInfrastructure();
  }

  async function toggleNode(node: NodeRecord) {
    await apiFetch<NodeRecord>(`/nodes/${node.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !node.is_enabled }),
    });
    await refreshInfrastructure();
  }

  async function createFolder() {
    const name = newFolderName.trim();
    if (!name) {
      return;
    }
    setCreatingFolder(true);
    setError("");
    try {
      const group = await apiFetch<NodeGroupRecord>("/node-groups", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setNodeGroups((current) => [...current, group].sort((a, b) => a.name.localeCompare(b.name)));
      setExpandedFolders((current) => new Set(current).add(group.name));
      setNewFolderName("");
      setShowCreateFolder(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder");
    } finally {
      setCreatingFolder(false);
    }
  }

  async function moveNodeToFolder(nodeId: number, nextGroupName: string | null) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node || (node.group_name ?? null) === nextGroupName) {
      return;
    }
    setMovingNode(true);
    setError("");
    try {
      await apiFetch<NodeRecord>(`/nodes/${nodeId}`, {
        method: "PUT",
        body: JSON.stringify({ group_name: nextGroupName }),
      });
      setNodes((current) => current.map((item) => (item.id === nodeId ? { ...item, group_name: nextGroupName } : item)));
      if (nextGroupName) {
        setExpandedFolders((current) => new Set(current).add(nextGroupName));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to move node");
      await refreshInfrastructure();
    } finally {
      setMovingNode(false);
      setDraggingNodeId(null);
      setDropTarget(null);
    }
  }

  const grouped = useMemo(() => {
    const folders = new Map<string, { id?: number; nodes: NodeRecord[] }>();
    const looseNodes: NodeRecord[] = [];

    for (const group of nodeGroups) {
      folders.set(group.name, { id: group.id, nodes: [] });
    }

    for (const node of nodes) {
      const trimmedGroup = node.group_name?.trim();
      if (!trimmedGroup) {
        looseNodes.push(node);
        continue;
      }
      const existing = folders.get(trimmedGroup) ?? { nodes: [] };
      folders.set(trimmedGroup, { ...existing, nodes: [...existing.nodes, node] });
    }

    const folderRows = Array.from(folders.entries())
      .map(([name, folder]) => {
        const folderNodes = folder.nodes.sort((a, b) => a.name.localeCompare(b.name));
        return {
          id: folder.id,
          name,
          nodes: folderNodes,
          visibleNodes: folderNodes.filter((node) => matchesFilter(node, filter)),
          status: folderStatus(folderNodes),
        };
      })
      .filter((folder) => filter === "all" || folder.visibleNodes.length)
      .sort((a, b) => a.name.localeCompare(b.name));

    return {
      folders: folderRows,
      looseNodes: looseNodes.sort((a, b) => a.name.localeCompare(b.name)),
    };
  }, [filter, nodeGroups, nodes]);

  const visibleLooseNodes = grouped.looseNodes.filter((node) => matchesFilter(node, filter));
  const visibleCount = visibleLooseNodes.length + grouped.folders.reduce((sum, folder) => sum + folder.visibleNodes.length, 0);
  const canAdminister = user?.role === "admin";

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

  function handleDragStart(event: DragEvent<HTMLTableRowElement>, nodeId: number) {
    if (!canAdminister) {
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(nodeId));
    setDraggingNodeId(nodeId);
  }

  function handleDragOver(event: DragEvent, target: string) {
    if (!draggingNodeId) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setDropTarget(target);
  }

  function handleDrop(event: DragEvent, nextGroupName: string | null) {
    event.preventDefault();
    const nodeId = Number(event.dataTransfer.getData("text/plain") || draggingNodeId);
    if (!nodeId) {
      return;
    }
    void moveNodeToFolder(nodeId, nextGroupName);
  }

  function renderNodeRow(node: NodeRecord, nested = false) {
    return (
      <tr
        key={node.id}
        draggable={canAdminister}
        onDragStart={(event) => handleDragStart(event, node.id)}
        onDragEnd={() => {
          setDraggingNodeId(null);
          setDropTarget(null);
        }}
        className={`${nested ? "bg-slate-50/70 dark:bg-[#090E1B]" : ""} ${canAdminister ? "cursor-grab active:cursor-grabbing" : ""}`}
      >
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
                <IconButton label={`Edit ${node.name}`} onClick={() => { void openEditNode(node); }}>
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
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                  Status
                  <select
                    value={filter}
                    onChange={(event) => setFilter(event.target.value as (typeof filters)[number])}
                    className="h-10 rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] shadow-sm outline-none transition focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                  >
                    {filters.map((entry) => (
                      <option key={entry} value={entry}>
                        {entry.charAt(0).toUpperCase() + entry.slice(1)}
                      </option>
                    ))}
                  </select>
                </label>
                {canAdminister ? (
                  <>
                    <button
                      type="button"
                      className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-ember hover:text-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-200"
                      onClick={() => setShowCreateFolder((current) => !current)}
                    >
                      <FolderPlus className="h-4 w-4" />
                      Create folder
                    </button>
                    <button
                      className="h-10 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember"
                      onClick={openCreateNode}
                    >
                      Add node
                    </button>
                  </>
                ) : null}
              </div>
            </div>

            {showCreateFolder ? (
              <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020] sm:flex-row sm:items-center">
                <input
                  value={newFolderName}
                  onChange={(event) => setNewFolderName(event.target.value)}
                  placeholder="Folder name"
                  className="h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-ember dark:border-slate-800 dark:bg-[#050814] dark:text-white"
                />
                <button
                  type="button"
                  disabled={!newFolderName.trim() || creatingFolder}
                  className="h-10 rounded-xl bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ember disabled:cursor-not-allowed disabled:opacity-50 dark:bg-ember"
                  onClick={createFolder}
                >
                  {creatingFolder ? "Creating..." : "Create"}
                </button>
              </div>
            ) : null}

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-500 dark:text-slate-400">{visibleCount} visible nodes</p>
              {canAdminister ? <p className="text-sm text-slate-500 dark:text-slate-400">Drag a node onto a folder to group it.</p> : null}
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
                  {grouped.folders.map((folder) => {
                    const expanded = expandedFolders.has(folder.name);
                    const isDropTarget = dropTarget === folder.name;
                    return (
                      <Fragment key={`folder:${folder.name}`}>
                        <tr
                          onDragOver={(event) => handleDragOver(event, folder.name)}
                          onDragLeave={() => setDropTarget(null)}
                          onDrop={(event) => handleDrop(event, folder.name)}
                          className={`${isDropTarget ? "bg-purple-50 ring-2 ring-inset ring-[#7C3AED] dark:bg-purple-950/30" : "bg-slate-50 dark:bg-[#0B1020]"}`}
                        >
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
                  <tr
                    onDragOver={(event) => handleDragOver(event, "__ungrouped")}
                    onDragLeave={() => setDropTarget(null)}
                    onDrop={(event) => handleDrop(event, null)}
                    className={`${dropTarget === "__ungrouped" ? "bg-purple-50 ring-2 ring-inset ring-[#7C3AED] dark:bg-purple-950/30" : "bg-slate-50 dark:bg-[#0B1020]"}`}
                  >
                    <td className="px-4 py-4 font-semibold text-ink dark:text-white">Ungrouped nodes</td>
                    <td className="px-4 py-4 text-slate-600 dark:text-slate-300" colSpan={5}>
                      Drop a node here to remove it from a folder.
                    </td>
                  </tr>
                  {visibleLooseNodes.map((node) => renderNodeRow(node))}
                  {!visibleCount && !grouped.folders.length ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
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
                  setFormValidationIds([]);
                  setFormRemediationIds([]);
                  setFormAutomationEdges([]);
                }}
              >
                Close
              </button>
            </div>
            <NodeForm
              key={editing ? `edit:${editing.id}:${formValidationIds.join(",")}:${formRemediationIds.join(",")}:${formAutomationEdges.map((edge) => `${edge.validation_id}-${edge.remediation_id}`).join(",")}` : "create"}
              credentials={credentials}
              validations={validations}
              remediations={remediations}
              initialValidationIds={formValidationIds}
              initialRemediationIds={formRemediationIds}
              initialAutomationEdges={formAutomationEdges}
              initial={editing}
              onSubmit={saveNode}
              onCancel={() => {
                setShowForm(false);
                setEditing(null);
                setFormValidationIds([]);
                setFormRemediationIds([]);
                setFormAutomationEdges([]);
              }}
            />
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
