"use client";

import { FormEvent, ReactNode, startTransition, useEffect, useState } from "react";
import { EyeOff, Pencil, Play, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { RemediationDefinition, User } from "@/lib/types";

const emptyForm = {
  name: "",
  description: "",
  command: "",
  risk_level: "medium",
  execution_mode: "",
  is_enabled: true,
};

type RemediationForm = typeof emptyForm;

function IconButton({ label, children, onClick, className = "" }: { label: string; children: ReactNode; onClick: () => void; className?: string }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={`grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-300 ${className}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function formFromRemediation(item: RemediationDefinition): RemediationForm {
  return {
    name: item.name,
    description: item.description ?? "",
    command: item.command,
    risk_level: item.risk_level,
    execution_mode: item.execution_mode ?? "",
    is_enabled: item.is_enabled,
  };
}

export default function RemediationsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<RemediationDefinition[]>([]);
  const [editing, setEditing] = useState<RemediationDefinition | null>(null);
  const [form, setForm] = useState<RemediationForm>(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<string | null>(null);

  async function loadRemediations() {
    setItems(await apiFetch<RemediationDefinition[]>("/remediations"));
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        loadRemediations().catch((err) => setError(err instanceof Error ? err.message : "Failed to load remediations"));
      });
    });
  }, [router]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
    setPreview(null);
  }

  function openEdit(item: RemediationDefinition) {
    setEditing(item);
    setForm(formFromRemediation(item));
    setShowForm(true);
    setPreview(null);
  }

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const payload = {
      ...form,
      description: form.description.trim() || null,
      execution_mode: form.execution_mode || null,
    };
    const path = editing ? `/remediations/${editing.id}` : "/remediations";
    const method = editing ? "PUT" : "POST";
    await apiFetch<RemediationDefinition>(path, { method, body: JSON.stringify(payload) });
    setShowForm(false);
    await loadRemediations();
  }

  async function toggleRemediation(item: RemediationDefinition) {
    await apiFetch<RemediationDefinition>(`/remediations/${item.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !item.is_enabled }),
    });
    await loadRemediations();
  }

  async function deleteRemediation(item: RemediationDefinition) {
    if (!window.confirm(`Delete remediation ${item.name}?`)) {
      return;
    }
    await apiFetch(`/remediations/${item.id}`, { method: "DELETE" });
    await loadRemediations();
  }

  async function previewRemediation(item: RemediationDefinition) {
    setError("");
    try {
      const payload = await apiFetch<{ command: string; risk_level: string; execution_mode?: string | null }>(`/remediations/${item.id}/test-preview`, { method: "POST", body: JSON.stringify({}) });
      setPreview(`${item.name}: ${payload.command}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    }
  }

  if (!user) {
    return null;
  }

  const canAdminister = user.role === "admin";
  const canOperate = user.role === "operator" || user.role === "admin";

  return (
    <AppShell user={user} title="Remediations" showHeaderControls={false} headerActions={canAdminister ? <button className="h-10 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember" onClick={openCreate}>Add remediation</button> : null}>
      <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-xl font-semibold">Remediation library</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{items.length} assigned-command actions | auto-run inherits each node&apos;s execution type</p>
          </div>
          {preview ? (
            <div className="max-w-xl rounded-2xl bg-panel px-4 py-3 text-sm text-slate-700 dark:bg-[#0B1020] dark:text-slate-200">
              <span className="font-semibold">Preview</span>: {preview}
            </div>
          ) : null}
        </div>
        {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

        <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-panel dark:bg-[#0B1020]">
              <tr className="text-left text-slate-500 dark:text-slate-300">
                <th className="px-4 py-3 font-medium">Remediation</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Command Preview</th>
                <th className="px-4 py-3 font-medium">Assigned Nodes</th>
                <th className="px-4 py-3 font-medium">Last Run</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="px-4 py-4">
                    <p className="font-semibold text-ink dark:text-white">{item.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{item.description ?? "No description configured."}</p>
                  </td>
                  <td className="px-4 py-4"><StatusBadge status={item.risk_level} /></td>
                  <td className="px-4 py-4">
                    <pre className="max-w-lg overflow-auto rounded-2xl bg-ink p-3 text-xs text-white">{item.command}</pre>
                  </td>
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{item.assigned_node_count}</td>
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{item.last_run_at ? new Date(item.last_run_at).toLocaleString() : "Never"}</td>
                  <td className="px-4 py-4"><StatusBadge status={item.is_enabled ? item.last_run_status ?? "enabled" : "disabled"} /></td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      {canOperate ? <IconButton label={`Preview ${item.name}`} onClick={() => previewRemediation(item)}><Play className="h-4 w-4" /></IconButton> : null}
                      {canAdminister ? (
                        <>
                          <IconButton label={`Edit ${item.name}`} onClick={() => openEdit(item)}><Pencil className="h-4 w-4" /></IconButton>
                          <IconButton label={`${item.is_enabled ? "Disable" : "Enable"} ${item.name}`} onClick={() => toggleRemediation(item)}><EyeOff className="h-4 w-4" /></IconButton>
                          <IconButton label={`Delete ${item.name}`} className="hover:border-rose-500 hover:text-rose-600 dark:hover:border-rose-800 dark:hover:text-rose-300" onClick={() => deleteRemediation(item)}><Trash2 className="h-4 w-4" /></IconButton>
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {!items.length ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">No remediations configured.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {showForm ? (
        <section className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/55 px-4 py-8">
          <form className="max-h-[calc(100vh-4rem)] w-full max-w-4xl overflow-auto rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none" onSubmit={submitForm}>
            <div className="mb-5 flex items-center justify-between gap-4">
              <h3 className="text-xl font-semibold">{editing ? "Edit remediation" : "Add remediation"}</h3>
              <button type="button" className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200" onClick={() => setShowForm(false)}>Close</button>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Name</span>
                <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" required />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Risk Level</span>
                <select value={form.risk_level} onChange={(event) => setForm((current) => ({ ...current, risk_level: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white">
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
              <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Command</span>
                <input value={form.command} onChange={(event) => setForm((current) => ({ ...current, command: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" required />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Execution Mode Override</span>
                <select value={form.execution_mode} onChange={(event) => setForm((current) => ({ ...current, execution_mode: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white">
                  <option value="">Use node mode</option>
                  <option value="runner">runner</option>
                  <option value="agent">agent</option>
                </select>
                <span className="mt-2 block text-xs text-slate-500 dark:text-slate-400">Automatic remediations always use the assigned node&apos;s execution type.</span>
              </label>
              <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Description</span>
                <textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
              </label>
              <label className="flex items-center gap-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                <input type="checkbox" checked={form.is_enabled} onChange={(event) => setForm((current) => ({ ...current, is_enabled: event.target.checked }))} className="h-4 w-4 rounded border-slate-300 accent-ember" />
                Enabled
              </label>
            </div>
            <div className="mt-5 flex gap-3">
              <button className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember">{editing ? "Update remediation" : "Create remediation"}</button>
              <button type="button" className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </section>
      ) : null}
    </AppShell>
  );
}
