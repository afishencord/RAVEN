"use client";

import { FormEvent, useEffect, useState, startTransition } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { apiFetch, requireSession } from "@/lib/api";
import { CredentialRecord, User } from "@/lib/types";

const defaultForm = {
  name: "",
  kind: "agent_token",
  username: "",
  description: "",
  secret_value: "",
};

export default function CredentialsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [credentials, setCredentials] = useState<CredentialRecord[]>([]);
  const [form, setForm] = useState(defaultForm);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);

  async function loadCredentials() {
    const payload = await apiFetch<CredentialRecord[]>("/credentials");
    setCredentials(payload);
  }

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        if (session.role !== "admin") {
          router.replace("/");
          return;
        }
        setUser(session);
        loadCredentials().catch((err) => setError(err instanceof Error ? err.message : "Failed to load credentials"));
      });
    });
  }, [router]);

  async function submitCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await apiFetch("/credentials", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          username: form.username || null,
          description: form.description || null,
          metadata_json: {},
        }),
      });
      setForm(defaultForm);
      setShowForm(false);
      await loadCredentials();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save credential");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCredential(id: number) {
    if (!window.confirm("Delete this credential?")) {
      return;
    }
    await apiFetch(`/credentials/${id}`, { method: "DELETE" });
    await loadCredentials();
  }

  if (!user) {
    return null;
  }

  return (
    <AppShell
      user={user}
      title="Execution credentials"
      headerActions={
        <button
          type="button"
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#7C3AED] px-4 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(124,58,237,0.25)] transition hover:bg-[#6D28D9] dark:shadow-none"
          onClick={() => {
            setForm(defaultForm);
            setShowForm(true);
          }}
        >
          <Plus className="h-4 w-4" />
          Add credentials
        </button>
      }
    >
      {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

      <section className="min-h-[calc(100vh-14rem)] rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-xl font-semibold">Stored credentials</h3>
          <span className="rounded-full bg-panel px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-[#0B1020] dark:text-slate-300">
            {credentials.length} configured
          </span>
        </div>

        <div className="mt-5 space-y-3">
          {credentials.map((credential) => (
            <article
              key={credential.id}
              className="flex flex-col gap-4 rounded-[1.5rem] border border-slate-200 bg-panel px-5 py-4 dark:border-slate-800 dark:bg-[#0B1020] lg:flex-row lg:items-center"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <p className="truncate text-base font-semibold text-ink dark:text-white">{credential.name}</p>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:bg-[#050814] dark:text-slate-300">
                    {credential.kind}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{credential.description ?? "No description"}</p>
              </div>

              <div className="grid gap-3 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-3 lg:w-[560px]">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Username</p>
                  <p className="mt-1 truncate font-medium">{credential.username ?? "Not set"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Secret</p>
                  <p className="mt-1 truncate font-mono text-xs">{credential.masked_secret}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">Updated</p>
                  <p className="mt-1 font-medium">{new Date(credential.updated_at).toLocaleDateString()}</p>
                </div>
              </div>

              <button
                type="button"
                aria-label={`Delete ${credential.name}`}
                title={`Delete ${credential.name}`}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-rose-500 hover:text-rose-600 dark:border-slate-800 dark:bg-[#050814] dark:text-slate-300 dark:hover:border-rose-800 dark:hover:text-rose-300"
                onClick={() => deleteCredential(credential.id)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </article>
          ))}
          {!credentials.length ? (
            <div className="rounded-[1.5rem] border border-dashed border-slate-300 px-5 py-10 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              No credentials stored yet.
            </div>
          ) : null}
        </div>
      </section>

      {showForm ? (
        <section className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/55 px-4 py-8">
          <form
            className="max-h-[calc(100vh-4rem)] w-full max-w-2xl overflow-auto rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none"
            onSubmit={submitCredential}
          >
            <div className="mb-5 flex items-center justify-between gap-4">
              <h3 className="text-xl font-semibold">Add credential</h3>
              <button
                type="button"
                aria-label="Close add credential form"
                className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 text-slate-600 transition hover:border-ember hover:text-ember dark:border-slate-800 dark:text-slate-300"
                onClick={() => setShowForm(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="grid gap-4">
              {[
                ["Name", "name"],
                ["Username", "username"],
                ["Description", "description"],
              ].map(([label, key]) => (
                <label key={key} className="text-sm text-slate-700 dark:text-slate-200">
                  <span className="mb-2 block font-medium">{label}</span>
                  <input
                    type="text"
                    value={String((form as Record<string, unknown>)[key] ?? "")}
                    onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
                  />
                </label>
              ))}
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Kind</span>
                <select
                  value={form.kind}
                  onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
                >
                  <option value="agent_token">agent_token</option>
                  <option value="bearer_token">bearer_token</option>
                  <option value="ssh_key">ssh_key</option>
                  <option value="ssh_password">ssh_password</option>
                </select>
              </label>
              <label className="text-sm text-slate-700 dark:text-slate-200">
                <span className="mb-2 block font-medium">Secret</span>
                {form.kind === "ssh_key" ? (
                  <textarea
                    value={form.secret_value}
                    onChange={(event) => setForm((current) => ({ ...current, secret_value: event.target.value }))}
                    rows={8}
                    spellCheck={false}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
                  />
                ) : (
                  <input
                    type="password"
                    value={form.secret_value}
                    onChange={(event) => setForm((current) => ({ ...current, secret_value: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
                  />
                )}
              </label>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="h-10 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-ember hover:text-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-200"
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </button>
                <button disabled={saving} className="h-10 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-ember disabled:opacity-60 dark:bg-ember">
                  {saving ? "Saving..." : "Create credential"}
                </button>
              </div>
            </div>
          </form>
        </section>
      ) : null}
    </AppShell>
  );
}
