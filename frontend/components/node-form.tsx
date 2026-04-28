"use client";

import { FormEvent, useMemo, useState, type DragEvent } from "react";
import { GitBranch, Plus, Search, Trash2, X } from "lucide-react";

import { CredentialRecord, NodeAutomationEdgeInput, NodeRecord, RemediationDefinition, ValidationDefinition } from "@/lib/types";

type Props = {
  credentials: CredentialRecord[];
  validations?: ValidationDefinition[];
  remediations?: RemediationDefinition[];
  initialValidationIds?: number[];
  initialRemediationIds?: number[];
  initialAutomationEdges?: NodeAutomationEdgeInput[];
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
  execution_target: "local:raven-backend",
  group_name: "",
  context_text: "",
  approved_command_policy: "",
  credential_id: "",
  is_enabled: true,
};

export function NodeForm({
  credentials,
  validations = [],
  remediations = [],
  initialValidationIds = [],
  initialRemediationIds = [],
  initialAutomationEdges = [],
  initial,
  onSubmit,
  onCancel,
}: Props) {
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
          group_name: initial.group_name ?? "",
          context_text: initial.context_text ?? "",
          approved_command_policy: initial.approved_command_policy ?? "",
          credential_id: initial.credential_id?.toString() ?? "",
        }
      : {}),
  });
  const [selectedValidationIds, setSelectedValidationIds] = useState<Set<number>>(() => new Set(initialValidationIds));
  const [selectedRemediationIds, setSelectedRemediationIds] = useState<Set<number>>(() => new Set(initialRemediationIds));
  const [automationEdges, setAutomationEdges] = useState<NodeAutomationEdgeInput[]>(() => initialAutomationEdges);
  const [showPlaybookBuilder, setShowPlaybookBuilder] = useState(false);
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
        group_name: form.group_name.trim() || null,
        automation_validation_ids: Array.from(selectedValidationIds),
        automation_remediation_ids: Array.from(selectedRemediationIds),
        automation_edges: automationEdges,
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
        ["Folder", "group_name"],
      ].map(([label, key]) => (
        <label key={key} className="text-sm text-slate-700 dark:text-slate-200">
          <span className="mb-2 block font-medium">{label}</span>
          <input
            value={String((form as Record<string, unknown>)[key] ?? "")}
            onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
            className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
          />
        </label>
      ))}

      <label className="text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Health Check Type</span>
        <select
          value={form.health_check_type}
          onChange={(event) => setForm((current) => ({ ...current, health_check_type: event.target.value }))}
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
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
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
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
          className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
        >
          <option value="">No credential</option>
          {credentials.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {credential.name} ({credential.kind})
            </option>
          ))}
        </select>
      </label>

      <section className="md:col-span-2 rounded-[1.5rem] border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-[#0B1020]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-white">Automatic remediation playbook</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {selectedValidationIds.size} validations, {selectedRemediationIds.size} remediations, {automationEdges.length} connections
            </p>
          </div>
          <button
            type="button"
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember"
            onClick={() => setShowPlaybookBuilder(true)}
          >
            <GitBranch className="h-4 w-4" />
            Manage Automatic Remediations
          </button>
        </div>
      </section>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Node Context</span>
        <textarea
          value={form.context_text}
          onChange={(event) => setForm((current) => ({ ...current, context_text: event.target.value }))}
          className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
          placeholder="Describe the service, owner, dependencies, and known failure modes."
        />
      </label>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Approved Command Policy</span>
        <textarea
          value={form.approved_command_policy}
          onChange={(event) => setForm((current) => ({ ...current, approved_command_policy: event.target.value }))}
          className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
          placeholder="Allow curl diagnostics and targeted service restarts only."
        />
      </label>

      <label className="md:col-span-2 text-sm text-slate-700 dark:text-slate-200">
        <span className="mb-2 block font-medium">Description</span>
        <textarea
          value={form.description}
          onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
          className="min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none transition focus:border-ember dark:border-slate-800 dark:bg-[#0B1020] dark:text-white"
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
        <button type="button" onClick={onCancel} className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200">
          Cancel
        </button>
      </div>

      {showPlaybookBuilder ? (
        <PlaybookBuilder
          validations={validations}
          remediations={remediations}
          selectedValidationIds={Array.from(selectedValidationIds)}
          selectedRemediationIds={Array.from(selectedRemediationIds)}
          edges={automationEdges}
          executionMode={form.execution_mode}
          onApply={(next) => {
            setSelectedValidationIds(new Set(next.validationIds));
            setSelectedRemediationIds(new Set(next.remediationIds));
            setAutomationEdges(next.edges);
            setShowPlaybookBuilder(false);
          }}
          onClose={() => setShowPlaybookBuilder(false)}
        />
      ) : null}
    </form>
  );
}

type PlaybookBuilderProps = {
  validations: ValidationDefinition[];
  remediations: RemediationDefinition[];
  selectedValidationIds: number[];
  selectedRemediationIds: number[];
  edges: NodeAutomationEdgeInput[];
  executionMode: string;
  onApply: (value: { validationIds: number[]; remediationIds: number[]; edges: NodeAutomationEdgeInput[] }) => void;
  onClose: () => void;
};

function PlaybookBuilder({
  validations,
  remediations,
  selectedValidationIds,
  selectedRemediationIds,
  edges,
  executionMode,
  onApply,
  onClose,
}: PlaybookBuilderProps) {
  const [validationIds, setValidationIds] = useState<number[]>(selectedValidationIds);
  const [remediationIds, setRemediationIds] = useState<number[]>(selectedRemediationIds);
  const [playbookEdges, setPlaybookEdges] = useState<NodeAutomationEdgeInput[]>(edges);
  const [picker, setPicker] = useState<"validation" | "remediation">("validation");
  const [query, setQuery] = useState("");
  const [connectingValidationId, setConnectingValidationId] = useState<number | null>(null);

  const selectedValidations = useMemo(
    () => validationIds.map((id) => validations.find((item) => item.id === id)).filter((item): item is ValidationDefinition => Boolean(item)),
    [validationIds, validations],
  );
  const selectedRemediations = useMemo(
    () => remediationIds.map((id) => remediations.find((item) => item.id === id)).filter((item): item is RemediationDefinition => Boolean(item)),
    [remediationIds, remediations],
  );
  const pickerItems = useMemo(() => {
    const lower = query.trim().toLowerCase();
    const source = picker === "validation" ? validations : remediations;
    return source.filter((item) => {
      const haystack = `${item.name} ${item.description ?? ""} ${"validation_type" in item ? item.validation_type : item.command}`.toLowerCase();
      return !lower || haystack.includes(lower);
    });
  }, [picker, query, remediations, validations]);

  function addValidation(id: number) {
    setValidationIds((current) => (current.includes(id) ? current : [...current, id]));
  }

  function addRemediation(id: number) {
    setRemediationIds((current) => (current.includes(id) ? current : [...current, id]));
  }

  function removeValidation(id: number) {
    setValidationIds((current) => current.filter((item) => item !== id));
    setPlaybookEdges((current) => current.filter((edge) => edge.validation_id !== id));
    if (connectingValidationId === id) {
      setConnectingValidationId(null);
    }
  }

  function removeRemediation(id: number) {
    setRemediationIds((current) => current.filter((item) => item !== id));
    setPlaybookEdges((current) => current.filter((edge) => edge.remediation_id !== id));
  }

  function addEdge(validationId: number, remediationId: number) {
    setPlaybookEdges((current) => {
      if (current.some((edge) => edge.validation_id === validationId && edge.remediation_id === remediationId)) {
        return current;
      }
      return [...current, { validation_id: validationId, remediation_id: remediationId }];
    });
    setConnectingValidationId(null);
  }

  function removeEdge(validationId: number, remediationId: number) {
    setPlaybookEdges((current) => current.filter((edge) => edge.validation_id !== validationId || edge.remediation_id !== remediationId));
  }

  function handleDragStart(event: DragEvent<HTMLButtonElement>, kind: "validation" | "remediation", id: number) {
    event.dataTransfer.effectAllowed = "copy";
    event.dataTransfer.setData("application/raven-automation", JSON.stringify({ kind, id }));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const raw = event.dataTransfer.getData("application/raven-automation");
    if (!raw) {
      return;
    }
    try {
      const payload = JSON.parse(raw) as { kind?: string; id?: number };
      if (payload.kind === "validation" && payload.id) {
        addValidation(payload.id);
      }
      if (payload.kind === "remediation" && payload.id) {
        addRemediation(payload.id);
      }
    } catch {
      return;
    }
  }

  function yFor(kind: "validation" | "remediation", id: number) {
    const index = kind === "validation" ? validationIds.indexOf(id) : remediationIds.indexOf(id);
    return 64 + Math.max(index, 0) * 96;
  }

  const validEdges = playbookEdges.filter((edge) => validationIds.includes(edge.validation_id) && remediationIds.includes(edge.remediation_id));

  return (
    <section className="fixed inset-0 z-[70] flex items-start justify-center bg-slate-950/65 px-4 py-8">
      <div className="max-h-[calc(100vh-4rem)] w-full max-w-6xl overflow-hidden rounded-[2rem] border border-[#E5E7EB] bg-white shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
        <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-6 py-5 dark:border-slate-800">
          <div>
            <h3 className="text-xl font-semibold text-slate-950 dark:text-white">Manage Automatic Remediations</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Playbooks run left to right through this node&apos;s {executionMode} path.</p>
          </div>
          <button type="button" aria-label="Close playbook builder" className="grid h-10 w-10 place-items-center rounded-xl bg-panel text-slate-700 dark:bg-[#0B1020] dark:text-slate-200" onClick={onClose}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid max-h-[calc(100vh-11rem)] grid-cols-1 overflow-auto lg:grid-cols-[20rem_1fr]">
          <aside className="border-b border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020] lg:border-b-0 lg:border-r">
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${picker === "validation" ? "bg-ink text-white dark:bg-ember" : "bg-white text-slate-700 dark:bg-[#050814] dark:text-slate-200"}`}
                onClick={() => setPicker("validation")}
              >
                Add Validation
              </button>
              <button
                type="button"
                className={`rounded-xl px-3 py-2 text-sm font-semibold transition ${picker === "remediation" ? "bg-ink text-white dark:bg-ember" : "bg-white text-slate-700 dark:bg-[#050814] dark:text-slate-200"}`}
                onClick={() => setPicker("remediation")}
              >
                Add Remediation
              </button>
            </div>
            <label className="mt-4 flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-slate-800 dark:bg-[#050814]">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="min-w-0 flex-1 bg-transparent outline-none dark:text-white"
                placeholder={`Search ${picker}s`}
              />
            </label>
            <div className="mt-4 max-h-[28rem] space-y-2 overflow-y-auto pr-1">
              {pickerItems.map((item) => {
                const isValidation = picker === "validation";
                const selected = isValidation ? validationIds.includes(item.id) : remediationIds.includes(item.id);
                return (
                  <button
                    key={`${picker}:${item.id}`}
                    type="button"
                    draggable
                    className="w-full rounded-2xl border border-slate-200 bg-white p-3 text-left transition hover:border-[#7C3AED] dark:border-slate-800 dark:bg-[#050814]"
                    onClick={() => (isValidation ? addValidation(item.id) : addRemediation(item.id))}
                    onDragStart={(event) => handleDragStart(event, picker, item.id)}
                  >
                    <span className="flex items-start justify-between gap-3">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-slate-900 dark:text-white">{item.name}</span>
                        <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">
                          {isValidation ? (item as ValidationDefinition).validation_type : `${(item as RemediationDefinition).risk_level} risk`}
                        </span>
                      </span>
                      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${selected ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300" : "bg-panel text-slate-600 dark:bg-[#0B1020] dark:text-slate-300"}`}>
                        <Plus className="h-4 w-4" />
                      </span>
                    </span>
                  </button>
                );
              })}
              {!pickerItems.length ? <p className="rounded-2xl bg-white p-4 text-sm text-slate-500 dark:bg-[#050814] dark:text-slate-400">No matching items.</p> : null}
            </div>
          </aside>

          <div
            className="relative min-h-[36rem] overflow-auto bg-white p-5 dark:bg-[#050814]"
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <div className="grid min-w-[44rem] grid-cols-[1fr_8rem_1fr] gap-4">
              <div>
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Validations</p>
                <div className="space-y-4">
                  {selectedValidations.map((validation) => (
                    <div key={validation.id} className="group relative rounded-2xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]">
                      <button
                        type="button"
                        title="Start connection"
                        aria-label={`Connect ${validation.name}`}
                        className={`absolute -right-3 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-white bg-[#7C3AED] text-white opacity-0 shadow-sm transition group-hover:opacity-100 dark:border-[#050814] ${connectingValidationId === validation.id ? "opacity-100 ring-4 ring-purple-200 dark:ring-purple-950" : ""}`}
                        onClick={() => setConnectingValidationId((current) => (current === validation.id ? null : validation.id))}
                      >
                        <span className="h-2 w-2 rounded-full bg-white" />
                      </button>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{validation.name}</p>
                          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{validation.validation_type} | {validation.is_enabled ? "enabled" : "disabled"}</p>
                          {validation.expected_response_contains ? <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{validation.expected_response_contains}</p> : null}
                        </div>
                        <button type="button" aria-label={`Remove ${validation.name}`} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-500 transition hover:bg-white hover:text-rose-600 dark:hover:bg-[#050814]" onClick={() => removeValidation(validation.id)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                  {!selectedValidations.length ? <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">Drag validations here or select them from the list.</p> : null}
                </div>
              </div>

              <div className="relative">
                <svg className="absolute inset-0 h-full w-full overflow-visible" preserveAspectRatio="none">
                  {validEdges.map((edge) => {
                    const fromY = yFor("validation", edge.validation_id);
                    const toY = yFor("remediation", edge.remediation_id);
                    return (
                      <g key={`${edge.validation_id}:${edge.remediation_id}`}>
                        <path d={`M 0 ${fromY} C 40 ${fromY}, 88 ${toY}, 128 ${toY}`} stroke="#7C3AED" strokeWidth="2" fill="none" />
                        <circle cx="0" cy={fromY} r="4" fill="#7C3AED" />
                        <circle cx="128" cy={toY} r="4" fill="#7C3AED" />
                      </g>
                    );
                  })}
                </svg>
                <div className="relative z-10 flex h-full items-center justify-center">
                  <span className="rounded-full bg-panel px-3 py-2 text-xs font-semibold text-slate-500 dark:bg-[#0B1020] dark:text-slate-400">All connected validations must pass</span>
                </div>
              </div>

              <div>
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Remediations</p>
                <div className="space-y-4">
                  {selectedRemediations.map((remediation) => (
                    <div key={remediation.id} className="group relative rounded-2xl border border-slate-200 bg-panel p-4 dark:border-slate-800 dark:bg-[#0B1020]">
                      <button
                        type="button"
                        title="Complete connection"
                        aria-label={`Connect to ${remediation.name}`}
                        disabled={connectingValidationId === null}
                        className="absolute -left-3 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full border border-white bg-[#7C3AED] text-white opacity-0 shadow-sm transition enabled:group-hover:opacity-100 disabled:bg-slate-300 dark:border-[#050814] dark:disabled:bg-slate-700"
                        onClick={() => {
                          if (connectingValidationId !== null) {
                            addEdge(connectingValidationId, remediation.id);
                          }
                        }}
                      >
                        <span className="h-2 w-2 rounded-full bg-white" />
                      </button>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{remediation.name}</p>
                          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{remediation.risk_level} risk | {remediation.is_enabled ? "enabled" : "disabled"}</p>
                          <p className="mt-2 line-clamp-2 font-mono text-xs text-slate-500 dark:text-slate-400">{remediation.command}</p>
                        </div>
                        <button type="button" aria-label={`Remove ${remediation.name}`} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-500 transition hover:bg-white hover:text-rose-600 dark:hover:bg-[#050814]" onClick={() => removeRemediation(remediation.id)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {validEdges
                          .filter((edge) => edge.remediation_id === remediation.id)
                          .map((edge) => {
                            const validation = validations.find((item) => item.id === edge.validation_id);
                            return (
                              <button
                                key={`${edge.validation_id}:${edge.remediation_id}:chip`}
                                type="button"
                                className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:text-rose-600 dark:bg-[#050814] dark:text-slate-300"
                                onClick={() => removeEdge(edge.validation_id, edge.remediation_id)}
                              >
                                {validation?.name ?? `Validation ${edge.validation_id}`} x
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  ))}
                  {!selectedRemediations.length ? <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">Drag remediations here or select them from the list.</p> : null}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-slate-200 px-6 py-4 dark:border-slate-800 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500 dark:text-slate-400">{validationIds.length} validations, {remediationIds.length} remediations, {validEdges.length} connections</p>
          <div className="flex gap-3">
            <button type="button" className="rounded-full border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-slate-800 dark:text-slate-200" onClick={onClose}>
              Cancel
            </button>
            <button type="button" className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-ember dark:bg-ember" onClick={() => onApply({ validationIds, remediationIds, edges: validEdges })}>
              Save playbook
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
