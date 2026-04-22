"use client";

import { FormEvent, useEffect, useState, startTransition } from "react";
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
      subtitle="Manage admin-only credentials used by runner and agent execution routes."
    >
      {error ? <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-900 dark:bg-rose-950/60 dark:text-rose-100">{error}</p> : null}

      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <form className="rounded-[2rem] border border-white/60 bg-white/70 p-6 shadow-panel backdrop-blur dark:border-white/10 dark:bg-slate-950/55" onSubmit={submitCredential}>
          <h3 className="text-xl font-semibold">Add credential</h3>
          <div className="mt-5 grid gap-4">
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
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
                />
              </label>
            ))}
            <label className="text-sm text-slate-700 dark:text-slate-200">
              <span className="mb-2 block font-medium">Kind</span>
              <select
                value={form.kind}
                onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
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
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
                />
              ) : (
                <input
                  type="password"
                  value={form.secret_value}
                  onChange={(event) => setForm((current) => ({ ...current, secret_value: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
                />
              )}
            </label>
            <button disabled={saving} className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember disabled:opacity-60 dark:bg-ember">
              {saving ? "Saving..." : "Create credential"}
            </button>
          </div>
        </form>

        <div className="rounded-[2rem] border border-white/60 bg-white/70 p-6 shadow-panel backdrop-blur dark:border-white/10 dark:bg-slate-950/55">
          <h3 className="text-xl font-semibold">Stored credentials</h3>
          <div className="mt-5 space-y-4">
            {credentials.map((credential) => (
              <div key={credential.id} className="rounded-3xl bg-panel p-4 dark:bg-white/5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold">{credential.name}</p>
                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{credential.kind}{credential.username ? ` | ${credential.username}` : ""}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{credential.masked_secret}</p>
                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{credential.description ?? "No description"}</p>
                  </div>
                  <button className="rounded-full bg-rose-100 px-4 py-2 text-xs font-semibold text-rose-800 dark:bg-rose-950/70 dark:text-rose-300 dark:border dark:border-rose-900" onClick={() => deleteCredential(credential.id)}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
            {!credentials.length ? <p className="text-sm text-slate-500 dark:text-slate-400">No credentials stored yet.</p> : null}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
