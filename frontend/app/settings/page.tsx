"use client";

import { startTransition, useEffect, useState, type ReactNode } from "react";
import { Save, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { requireSession } from "@/lib/api";
import { User } from "@/lib/types";

const modelProviders = [
  { value: "env_default", label: "Use default model from environment" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Claude / Anthropic" },
  { value: "self_hosted", label: "Self-hosted LLM" },
  { value: "custom", label: "Custom provider" },
];

const customModelOptions = [
  "gpt-5.2",
  "gpt-5.2-mini",
  "claude-3-5-sonnet",
  "llama-3.1-70b",
  "mistral-large",
  "custom-model",
];

const approvalModes = ["Operator approval required", "Admin approval required", "Two-person approval"];
const integrationRows = ["ServiceNow", "Slack", "Mattermost", "Microsoft Teams"];

const defaultSettings = {
  organizationName: "Acme Corporation",
  modelProvider: "env_default",
  customModel: "gpt-5.2",
  modelEndpoint: "",
  apiKeyOverride: "",
  localAuthEnabled: true,
  ldapEnabled: false,
  ssoEnabled: false,
  ldapUrl: "",
  ldapBaseDn: "",
  ssoIssuer: "",
  ssoClientId: "",
  alertEmail: "ops@example.com",
  webhookUrl: "",
  retentionDays: 180,
  auditRetentionDays: 365,
  approvalMode: "Operator approval required",
  maintenanceWindow: "Sunday 02:00-04:00",
  requirePostValidation: true,
  notifyOnResolution: true,
  notifyOnLicenseWarning: true,
  allowRunnerExecution: true,
};

function FieldShell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="text-sm text-slate-700 dark:text-slate-200">
      <span className="mb-2 block font-medium">{label}</span>
      {children}
    </label>
  );
}

function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-slate-200 px-6 py-6 last:border-b-0 dark:border-slate-800">
      <h3 className="text-xl font-semibold">{title}</h3>
      <div className="mt-5 grid gap-4">{children}</div>
    </section>
  );
}

function ToggleRow({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-2xl bg-panel px-4 py-3 text-sm dark:bg-[#0B1020]">
      <span className="font-medium text-slate-700 dark:text-slate-200">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5 rounded border-slate-300 text-[#7C3AED] focus:ring-[#7C3AED] disabled:opacity-50"
      />
    </label>
  );
}

function inputClass() {
  return "h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100";
}

function selectClass() {
  return "h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100";
}

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState(defaultSettings);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    startTransition(() => {
      requireSession().then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setUser(session);
      });
    });
  }, [router]);

  if (!user) {
    return null;
  }

  const canEdit = user.role === "admin";
  const usingEnvironmentModel = settings.modelProvider === "env_default";

  return (
    <AppShell
      user={user}
      title="Settings"
      headerActions={
        <button
          type="button"
          disabled={!canEdit}
          className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#7C3AED] px-4 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(124,58,237,0.25)] transition hover:bg-[#6D28D9] disabled:opacity-50 dark:shadow-none"
          onClick={() => setSavedAt(new Date().toISOString())}
        >
          <Save className="h-4 w-4" />
          Save changes
        </button>
      }
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-3 rounded-[1.5rem] border border-[#E5E7EB] bg-white px-5 py-4 text-sm text-slate-600 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:text-slate-300 dark:shadow-none sm:flex-row sm:items-center sm:justify-between">
          <span className="inline-flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-[#7C3AED]" />
            {canEdit ? "Administrative settings" : "Read-only settings"}
          </span>
          <span>{savedAt ? `Saved ${new Date(savedAt).toLocaleString()}` : "No changes saved in this session"}</span>
        </div>

        <section className="overflow-hidden rounded-[2rem] border border-[#E5E7EB] bg-white shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
          <SettingsSection title="AI Model">
            <div className="grid gap-4 lg:grid-cols-2">
              <FieldShell label="Configure custom model">
                <select
                  value={settings.modelProvider}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, modelProvider: event.target.value }))}
                  className={selectClass()}
                >
                  {modelProviders.map((provider) => (
                    <option key={provider.value} value={provider.value}>{provider.label}</option>
                  ))}
                </select>
              </FieldShell>
              <FieldShell label="Model">
                <select
                  value={settings.customModel}
                  disabled={!canEdit || usingEnvironmentModel}
                  onChange={(event) => setSettings((current) => ({ ...current, customModel: event.target.value }))}
                  className={selectClass()}
                >
                  {customModelOptions.map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </FieldShell>
              <FieldShell label="Model endpoint">
                <input
                  type="url"
                  value={settings.modelEndpoint}
                  disabled={!canEdit || usingEnvironmentModel}
                  onChange={(event) => setSettings((current) => ({ ...current, modelEndpoint: event.target.value }))}
                  placeholder={usingEnvironmentModel ? "Using environment configuration" : "https://llm.example.internal/v1"}
                  className={inputClass()}
                />
              </FieldShell>
              <FieldShell label="API key override">
                <input
                  type="password"
                  value={settings.apiKeyOverride}
                  disabled={!canEdit || usingEnvironmentModel}
                  onChange={(event) => setSettings((current) => ({ ...current, apiKeyOverride: event.target.value }))}
                  placeholder={usingEnvironmentModel ? "Using environment API key" : "Override provider key"}
                  className={inputClass()}
                />
              </FieldShell>
            </div>
            <ToggleRow
              label="Require post-remediation validation"
              checked={settings.requirePostValidation}
              disabled={!canEdit}
              onChange={(checked) => setSettings((current) => ({ ...current, requirePostValidation: checked }))}
            />
          </SettingsSection>

          <SettingsSection title="Organization">
            <div className="grid gap-4 lg:grid-cols-2">
              <FieldShell label="Organization name">
                <input
                  type="text"
                  value={settings.organizationName}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, organizationName: event.target.value }))}
                  className={inputClass()}
                />
              </FieldShell>
              <FieldShell label="Maintenance window">
                <input
                  type="text"
                  value={settings.maintenanceWindow}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, maintenanceWindow: event.target.value }))}
                  className={inputClass()}
                />
              </FieldShell>
            </div>
            <FieldShell label="License warning notifications">
              <select
                value={settings.notifyOnLicenseWarning ? "enabled" : "disabled"}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, notifyOnLicenseWarning: event.target.value === "enabled" }))}
                className={selectClass()}
              >
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
              </select>
            </FieldShell>
          </SettingsSection>

          <SettingsSection title="Authentication">
            <div className="grid gap-4">
              <div className="rounded-[1.5rem] bg-panel p-4 dark:bg-[#0B1020]">
                <ToggleRow
                  label="Local authentication"
                  checked={settings.localAuthEnabled}
                  disabled={!canEdit}
                  onChange={(checked) => setSettings((current) => ({ ...current, localAuthEnabled: checked }))}
                />
              </div>
              <div className="rounded-[1.5rem] bg-panel p-4 dark:bg-[#0B1020]">
                <ToggleRow
                  label="LDAP authentication"
                  checked={settings.ldapEnabled}
                  disabled={!canEdit}
                  onChange={(checked) => setSettings((current) => ({ ...current, ldapEnabled: checked }))}
                />
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <FieldShell label="LDAP URL">
                    <input
                      type="url"
                      value={settings.ldapUrl}
                      disabled={!canEdit || !settings.ldapEnabled}
                      onChange={(event) => setSettings((current) => ({ ...current, ldapUrl: event.target.value }))}
                      className={inputClass()}
                    />
                  </FieldShell>
                  <FieldShell label="LDAP base DN">
                    <input
                      type="text"
                      value={settings.ldapBaseDn}
                      disabled={!canEdit || !settings.ldapEnabled}
                      onChange={(event) => setSettings((current) => ({ ...current, ldapBaseDn: event.target.value }))}
                      className={inputClass()}
                    />
                  </FieldShell>
                </div>
              </div>
              <div className="rounded-[1.5rem] bg-panel p-4 dark:bg-[#0B1020]">
                <ToggleRow
                  label="SSO authentication"
                  checked={settings.ssoEnabled}
                  disabled={!canEdit}
                  onChange={(checked) => setSettings((current) => ({ ...current, ssoEnabled: checked }))}
                />
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <FieldShell label="SSO issuer">
                    <input
                      type="url"
                      value={settings.ssoIssuer}
                      disabled={!canEdit || !settings.ssoEnabled}
                      onChange={(event) => setSettings((current) => ({ ...current, ssoIssuer: event.target.value }))}
                      className={inputClass()}
                    />
                  </FieldShell>
                  <FieldShell label="SSO client ID">
                    <input
                      type="text"
                      value={settings.ssoClientId}
                      disabled={!canEdit || !settings.ssoEnabled}
                      onChange={(event) => setSettings((current) => ({ ...current, ssoClientId: event.target.value }))}
                      className={inputClass()}
                    />
                  </FieldShell>
                </div>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection title="Notifications">
            <div className="grid gap-4 lg:grid-cols-2">
              <FieldShell label="Alert email">
                <input
                  type="email"
                  value={settings.alertEmail}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, alertEmail: event.target.value }))}
                  className={inputClass()}
                />
              </FieldShell>
              <FieldShell label="Webhook URL">
                <input
                  type="url"
                  value={settings.webhookUrl}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, webhookUrl: event.target.value }))}
                  className={inputClass()}
                />
              </FieldShell>
            </div>
            <ToggleRow
              label="Notify on outage resolution"
              checked={settings.notifyOnResolution}
              disabled={!canEdit}
              onChange={(checked) => setSettings((current) => ({ ...current, notifyOnResolution: checked }))}
            />
          </SettingsSection>

          <SettingsSection title="Data Retention">
            <div className="grid gap-4 lg:grid-cols-2">
              <FieldShell label="Notification retention days">
                <input
                  type="number"
                  min={1}
                  value={settings.retentionDays}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, retentionDays: Number(event.target.value) }))}
                  className={inputClass()}
                />
              </FieldShell>
              <FieldShell label="Audit retention days">
                <input
                  type="number"
                  min={1}
                  value={settings.auditRetentionDays}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, auditRetentionDays: Number(event.target.value) }))}
                  className={inputClass()}
                />
              </FieldShell>
            </div>
          </SettingsSection>

          <SettingsSection title="Execution Controls">
            <FieldShell label="Approval policy">
              <select
                value={settings.approvalMode}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, approvalMode: event.target.value }))}
                className={selectClass()}
              >
                {approvalModes.map((mode) => (
                  <option key={mode} value={mode}>{mode}</option>
                ))}
              </select>
            </FieldShell>
            <ToggleRow
              label="Allow runner command execution"
              checked={settings.allowRunnerExecution}
              disabled={!canEdit}
              onChange={(checked) => setSettings((current) => ({ ...current, allowRunnerExecution: checked }))}
            />
          </SettingsSection>

          <SettingsSection title="Integrations">
            <div className="overflow-hidden rounded-[1.5rem] border border-slate-200 dark:border-slate-800">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-panel dark:bg-[#0B1020]">
                  <tr className="text-left text-slate-500 dark:text-slate-300">
                    <th className="px-4 py-3 font-medium">Integration</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Settings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white dark:divide-slate-800 dark:bg-[#050814]">
                  {integrationRows.map((integration) => (
                    <tr key={integration} className="bg-slate-50 dark:bg-[#0B1020]">
                      <td className="px-4 py-4 font-semibold text-ink dark:text-white">{integration}</td>
                      <td className="px-4 py-4 text-slate-600 dark:text-slate-300">Not enabled</td>
                      <td className="px-4 py-4 text-slate-600 dark:text-slate-300">Available after this integration is enabled.</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SettingsSection>
        </section>
      </div>
    </AppShell>
  );
}
