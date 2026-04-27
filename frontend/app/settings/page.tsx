"use client";

import { startTransition, useEffect, useState, type ReactNode } from "react";
import { Save, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { requireSession } from "@/lib/api";
import { User } from "@/lib/types";

const modelOptions = [
  "gpt-5.2",
  "gpt-5.2-mini",
  "gpt-5.1",
  "gpt-4.1",
];

const authModes = ["Local", "LDAP", "SAML SSO", "OIDC SSO"];
const approvalModes = ["Operator approval required", "Admin approval required", "Two-person approval"];

const defaultSettings = {
  organizationName: "Acme Corporation",
  defaultModel: "gpt-5.2",
  apiKeyOverride: "",
  authMode: "Local",
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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-[2rem] border border-[#E5E7EB] bg-white p-6 shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none">
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

        <div className="grid gap-6 xl:grid-cols-2">
          <Section title="AI Model">
            <FieldShell label="Default model">
              <select
                value={settings.defaultModel}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, defaultModel: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              >
                {modelOptions.map((model) => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
            </FieldShell>
            <FieldShell label="API key override">
              <input
                type="password"
                value={settings.apiKeyOverride}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, apiKeyOverride: event.target.value }))}
                placeholder="Use environment default"
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              />
            </FieldShell>
            <ToggleRow
              label="Require post-remediation validation"
              checked={settings.requirePostValidation}
              disabled={!canEdit}
              onChange={(checked) => setSettings((current) => ({ ...current, requirePostValidation: checked }))}
            />
          </Section>

          <Section title="Organization">
            <FieldShell label="Organization name">
              <input
                type="text"
                value={settings.organizationName}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, organizationName: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              />
            </FieldShell>
            <FieldShell label="Maintenance window">
              <input
                type="text"
                value={settings.maintenanceWindow}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, maintenanceWindow: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              />
            </FieldShell>
            <FieldShell label="License warning notifications">
              <select
                value={settings.notifyOnLicenseWarning ? "enabled" : "disabled"}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, notifyOnLicenseWarning: event.target.value === "enabled" }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              >
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
              </select>
            </FieldShell>
          </Section>

          <Section title="Authentication">
            <FieldShell label="Authentication mode">
              <select
                value={settings.authMode}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, authMode: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              >
                {authModes.map((mode) => (
                  <option key={mode} value={mode}>{mode}</option>
                ))}
              </select>
            </FieldShell>
            <div className="grid gap-4 md:grid-cols-2">
              <FieldShell label="LDAP URL">
                <input
                  type="url"
                  value={settings.ldapUrl}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, ldapUrl: event.target.value }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
              <FieldShell label="LDAP base DN">
                <input
                  type="text"
                  value={settings.ldapBaseDn}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, ldapBaseDn: event.target.value }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <FieldShell label="SSO issuer">
                <input
                  type="url"
                  value={settings.ssoIssuer}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, ssoIssuer: event.target.value }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
              <FieldShell label="SSO client ID">
                <input
                  type="text"
                  value={settings.ssoClientId}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, ssoClientId: event.target.value }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
            </div>
          </Section>

          <Section title="Notifications">
            <FieldShell label="Alert email">
              <input
                type="email"
                value={settings.alertEmail}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, alertEmail: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              />
            </FieldShell>
            <FieldShell label="Webhook URL">
              <input
                type="url"
                value={settings.webhookUrl}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, webhookUrl: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
              />
            </FieldShell>
            <ToggleRow
              label="Notify on outage resolution"
              checked={settings.notifyOnResolution}
              disabled={!canEdit}
              onChange={(checked) => setSettings((current) => ({ ...current, notifyOnResolution: checked }))}
            />
          </Section>

          <Section title="Data Retention">
            <div className="grid gap-4 md:grid-cols-2">
              <FieldShell label="Notification retention days">
                <input
                  type="number"
                  min={1}
                  value={settings.retentionDays}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, retentionDays: Number(event.target.value) }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
              <FieldShell label="Audit retention days">
                <input
                  type="number"
                  min={1}
                  value={settings.auditRetentionDays}
                  disabled={!canEdit}
                  onChange={(event) => setSettings((current) => ({ ...current, auditRetentionDays: Number(event.target.value) }))}
                  className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
                />
              </FieldShell>
            </div>
          </Section>

          <Section title="Execution Controls">
            <FieldShell label="Approval policy">
              <select
                value={settings.approvalMode}
                disabled={!canEdit}
                onChange={(event) => setSettings((current) => ({ ...current, approvalMode: event.target.value }))}
                className="h-10 w-full rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] outline-none focus:border-[#7C3AED] disabled:opacity-60 dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-100"
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
          </Section>
        </div>
      </div>
    </AppShell>
  );
}
