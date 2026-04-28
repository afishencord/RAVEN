"use client";

import { FormEvent, ReactNode, startTransition, useEffect, useState } from "react";
import { EyeOff, Pencil, Play, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, requireSession } from "@/lib/api";
import { User, ValidationDefinition, ValidationRun } from "@/lib/types";

const emptyForm = {
  name: "",
  description: "",
  validation_type: "http",
  command: "",
  url: "",
  path: "",
  expected_status_code: "200",
  expected_exit_code: "0",
  expected_response_contains: "",
  timeout_seconds: "10",
  is_enabled: true,
};

type ValidationForm = typeof emptyForm;

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

function formFromValidation(item: ValidationDefinition): ValidationForm {
  return {
    name: item.name,
    description: item.description ?? "",
    validation_type: item.validation_type,
    command: item.command ?? "",
    url: item.url ?? "",
    path: item.path ?? "",
    expected_status_code: item.expected_status_code?.toString() ?? "",
    expected_exit_code: item.expected_exit_code.toString(),
    expected_response_contains: item.expected_response_contains ?? "",
    timeout_seconds: item.timeout_seconds.toString(),
    is_enabled: item.is_enabled,
  };
}

export default function ValidationsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [items, setItems] = useState<ValidationDefinition[]>([]);
  const [editing, setEditing] = useState<ValidationDefinition | null>(null);
  const [form, setForm] = useState<ValidationForm>(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<ValidationRun | null>(null);

  async function loadValidations() {
    setItems(await apiFetch<ValidationDefinition[]>("/validations"));
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
        loadValidations().catch((err) => setError(err instanceof Error ? err.message : "Failed to load validations"));
      });
    });
  }, [router]);

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
    setTestResult(null);
  }

  function openEdit(item: ValidationDefinition) {
    setEditing(item);
    setForm(formFromValidation(item));
    setShowForm(true);
    setTestResult(null);
  }

  async function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const payload = {
      ...form,
      command: form.command.trim() || null,
      url: form.url.trim() || null,
      path: form.path.trim() || null,
      description: form.description.trim() || null,
      expected_status_code: form.expected_status_code ? Number(form.expected_status_code) : null,
      expected_exit_code: Number(form.expected_exit_code),
      expected_response_contains: form.expected_response_contains.trim() || null,
      timeout_seconds: Number(form.timeout_seconds),
    };
    const path = editing ? `/validations/${editing.id}` : "/validations";
    const method = editing ? "PUT" : "POST";
    await apiFetch<ValidationDefinition>(path, { method, body: JSON.stringify(payload) });
    setShowForm(false);
    await loadValidations();
  }

  async function toggleValidation(item: ValidationDefinition) {
    await apiFetch<ValidationDefinition>(`/validations/${item.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_enabled: !item.is_enabled }),
    });
    await loadValidations();
  }

  async function deleteValidation(item: ValidationDefinition) {
    if (!window.confirm(`Delete validation ${item.name}?`)) {
      return;
    }
    await apiFetch(`/validations/${item.id}`, { method: "DELETE" });
    await loadValidations();
  }

  async function testValidation(item: ValidationDefinition) {
    setTestingId(item.id);
    setError("");
    setTestResult(null);
    try {
      setTestResult(await apiFetch<ValidationRun>(`/validations/${item.id}/test`, { method: "POST", body: JSON.stringify({}) }));
      await loadValidations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation test failed");
    } finally {
      setTestingId(null);
    }
  }

  if (!user) {
    return null;
  }

  const canAdminister = user.role === "admin";
  const canOperate = user.role === "operator" || user.role === "admin";

  return (
    <AppShell user={user} title="Validations" showHeaderControls={false} headerActions={canAdminister ? <button className="h-10 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember" onClick={openCreate}>Add validation</button> : null}>
      <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-xl font-semibold">Validation library</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{items.length} reusable checks</p>
          </div>
          {testResult ? (
            <div className="rounded-2xl bg-panel px-4 py-3 text-sm text-slate-700 dark:bg-[#0B1020] dark:text-slate-200">
              Last test: <span className="font-semibold">{testResult.validation_name ?? `Validation ${testResult.validation_id}`}</span> returned {testResult.status}.
            </div>
          ) : null}
        </div>
        {error ? <p className="mt-4 rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

        <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-panel dark:bg-[#0B1020]">
              <tr className="text-left text-slate-500 dark:text-slate-300">
                <th className="px-4 py-3 font-medium">Validation</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">LLM Match Condition</th>
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
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{item.validation_type}</td>
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">
                    <p>{item.validation_type === "command" ? `Exit ${item.expected_exit_code}` : `HTTP ${item.expected_status_code ?? 200}`}</p>
                    <p className="mt-1 text-xs">{item.expected_response_contains || "No semantic condition required"}</p>
                  </td>
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{item.assigned_node_count}</td>
                  <td className="px-4 py-4 text-slate-600 dark:text-slate-300">{item.last_run_at ? new Date(item.last_run_at).toLocaleString() : "Never"}</td>
                  <td className="px-4 py-4"><StatusBadge status={item.is_enabled ? item.last_run_status ?? "enabled" : "disabled"} /></td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      {canOperate ? <IconButton label={`Test ${item.name}`} onClick={() => testValidation(item)}><Play className="h-4 w-4" /></IconButton> : null}
                      {canAdminister ? (
                        <>
                          <IconButton label={`Edit ${item.name}`} onClick={() => openEdit(item)}><Pencil className="h-4 w-4" /></IconButton>
                          <IconButton label={`${item.is_enabled ? "Disable" : "Enable"} ${item.name}`} onClick={() => toggleValidation(item)}><EyeOff className="h-4 w-4" /></IconButton>
                          <IconButton label={`Delete ${item.name}`} className="hover:border-rose-500 hover:text-rose-600 dark:hover:border-rose-800 dark:hover:text-rose-300" onClick={() => deleteValidation(item)}><Trash2 className="h-4 w-4" /></IconButton>
                        </>
                      ) : null}
                      {testingId === item.id ? <span className="self-center text-xs text-slate-500 dark:text-slate-400">Testing...</span> : null}
                    </div>
                  </td>
                </tr>
              ))}
              {!items.length ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">No validations configured.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {showForm ? (
        <section className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 py-8">
          <form className="max-h-[calc(100vh-4rem)] w-full max-w-4xl overflow-auto rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-none dark:border-slate-800 dark:bg-[#050814]" onSubmit={submitForm}>
            <div className="mb-5 flex items-center justify-between gap-4">
              <h3 className="text-xl font-semibold">{editing ? "Edit validation" : "Add validation"}</h3>
              <button type="button" className="rounded-full bg-panel px-4 py-2 text-sm font-semibold text-slate-700 dark:bg-[#0B1020] dark:text-slate-200" onClick={() => setShowForm(false)}>Close</button>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Name</span>
                <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" required />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Type</span>
                <select value={form.validation_type} onChange={(event) => setForm((current) => ({ ...current, validation_type: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white">
                  <option value="http">HTTP</option>
                  <option value="command">Command</option>
                </select>
              </label>
              {form.validation_type === "command" ? (
                <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
                  <span className="mb-2 block font-medium">Command</span>
                  <input value={form.command} onChange={(event) => setForm((current) => ({ ...current, command: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" required />
                </label>
              ) : (
                <>
                  <label className="text-sm text-slate-700 dark:text-slate-200">
                    <span className="mb-2 block font-medium">URL Override</span>
                    <input value={form.url} onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))} placeholder="Use node URL when blank" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
                  </label>
                  <label className="text-sm text-slate-700 dark:text-slate-200">
                    <span className="mb-2 block font-medium">Path</span>
                    <input value={form.path} onChange={(event) => setForm((current) => ({ ...current, path: event.target.value }))} placeholder="Use node health path when blank" className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
                  </label>
                </>
              )}
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Expected HTTP Status</span>
                <input value={form.expected_status_code} onChange={(event) => setForm((current) => ({ ...current, expected_status_code: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Expected Exit Code</span>
                <input value={form.expected_exit_code} onChange={(event) => setForm((current) => ({ ...current, expected_exit_code: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Expected Text</span>
                <input
                  value={form.expected_response_contains}
                  onChange={(event) => setForm((current) => ({ ...current, expected_response_contains: event.target.value }))}
                  placeholder="Example: systemctl service appears to be stopped or crashed"
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
                />
                <span className="mt-2 block text-xs text-slate-500 dark:text-slate-400">Optional natural-language condition. When provided, RAVEN asks the model whether the output matches this condition.</span>
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Timeout Seconds</span>
                <input value={form.timeout_seconds} onChange={(event) => setForm((current) => ({ ...current, timeout_seconds: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white" />
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
              <button className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember">{editing ? "Update validation" : "Create validation"}</button>
              <button type="button" className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </section>
      ) : null}
    </AppShell>
  );
}
