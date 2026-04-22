"use client";

import { FormEvent, useState } from "react";

import { CredentialRecord, NodeRecord } from "@/lib/types";

type Props = {
  credentials: CredentialRecord[];
  initial?: NodeRecord | null;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
};

const defaultValues = {
  name: "",
  description: "",
  environment: "prod",
  host: "",
  port: "",
  url: "",
  health_check_type: "http",
  health_check_path: "/health",
  expected_status_code: "200",
  expected_response_contains: "",
  check_interval_seconds: "60",
  timeout_seconds: "5",
  retry_count: "3",
  execution_mode: "runner",
  execution_target: "local:raven-test",
  context_text: "",
  approved_command_policy: "",
  credential_id: "",
  is_enabled: true,
};

export function NodeForm({ credentials, initial, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState({
    ...defaultValues,
    ...(initial
      ? {
          ...initial,
          port: initial.port?.toString() ?? "",
          expected_status_code: initial.expected_status_code.toString(),
          check_interval_seconds: initial.check_interval_seconds.toString(),
          timeout_seconds: initial.timeout_seconds.toString(),
          retry_count: initial.retry_count.toString(),
          description: initial.description ?? "",
          health_check_path: initial.health_check_path ?? "",
          expected_response_contains: initial.expected_response_contains ?? "",
          url: initial.url ?? "",
          context_text: initial.context_text ?? "",
          approved_command_policy: initial.approved_command_policy ?? "",
          credential_id: initial.credential_id?.toString() ?? "",
        }
      : {}),
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    try {
      await onSubmit({
        ...form,
        port: form.port ? Number(form.port) : null,
        expected_status_code: Number(form.expected_status_code),
        check_interval_seconds: Number(form.check_interval_seconds),
        timeout_seconds: Number(form.timeout_seconds),
        retry_count: Number(form.retry_count),
        credential_id: form.credential_id ? Number(form.credential_id) : null,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
      {[
        ["Name", "name"],
        ["Environment", "environment"],
        ["Host / IP", "host"],
        ["Port", "port"],
        ["URL", "url"],
        ["Health Path", "health_check_path"],
        ["Expected Status", "expected_status_code"],
        ["Expected Text", "expected_response_contains"],
        ["Interval Seconds", "check_interval_seconds"],
        ["Timeout Seconds", "timeout_seconds"],
        ["Retry Count", "retry_count"],
        ["Execution Target", "execution_target"],
      ].map(([label, key]) => (
        <label key={key} className="text-sm text-slate-700 dark:text-slate-200">
          <span className="mb-2 block font-medium">{label}</span>
          <input
            value={String((form as Record<string, unknown>)[key] ?? "")}
            onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
          />
        </label>
      ))}

      <label className="text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Health Check Type</span>
        <select
          value={form.health_check_type}
          onChange={(event) => setForm((current) => ({ ...current, health_check_type: event.target.value }))}
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
        >
          <option value="ping">ping</option>
          <option value="http">http</option>
          <option value="https">https</option>
          <option value="api">api</option>
        </select>
      </label>

      <label className="text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Execution Mode</span>
        <select
          value={form.execution_mode}
          onChange={(event) => setForm((current) => ({ ...current, execution_mode: event.target.value }))}
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
        >
          <option value="runner">runner</option>
          <option value="agent">agent</option>
        </select>
      </label>

      <label className="text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Credential</span>
        <select
          value={form.credential_id}
          onChange={(event) => setForm((current) => ({ ...current, credential_id: event.target.value }))}
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
        >
          <option value="">No credential</option>
          {credentials.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {credential.name} ({credential.kind})
            </option>
          ))}
        </select>
      </label>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Node Context</span>
        <textarea
          value={form.context_text}
          onChange={(event) => setForm((current) => ({ ...current, context_text: event.target.value }))}
          className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
          placeholder="raven-test: a simple nginx container running on localhost:6767"
        />
      </label>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Approved Command Policy</span>
        <textarea
          value={form.approved_command_policy}
          onChange={(event) => setForm((current) => ({ ...current, approved_command_policy: event.target.value }))}
          className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
          placeholder="Allow curl diagnostics and targeted service restarts only."
        />
      </label>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Description</span>
        <textarea
          value={form.description}
          onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
          className="min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-white/10 dark:bg-white/5 dark:text-white"
        />
      </label>

      <label className="flex items-center gap-3 text-sm font-medium text-slate-700 dark:text-slate-200">
        <input
          type="checkbox"
          checked={form.is_enabled}
          onChange={(event) => setForm((current) => ({ ...current, is_enabled: event.target.checked }))}
          className="h-4 w-4 rounded border-slate-300 accent-ember"
        />
        Monitoring enabled
      </label>

      <div className="md:col-span-2 flex gap-3">
        <button disabled={saving} className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember disabled:opacity-60 dark:bg-ember">
          {saving ? "Saving..." : initial ? "Update Node" : "Create Node"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-white/15 dark:text-slate-200">
          Cancel
        </button>
      </div>
    </form>
  );
}
