"use client";

import {
  BarChart3,
  Bell,
  Bot,
  ChevronDown,
  KeyRound,
  LayoutDashboard,
  MessageSquare,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";

import { apiFetch, clearToken } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";
import { PlatformChatWidget } from "@/components/platform-chat-widget";
import { AuditLogRecord, MessageIncident, User } from "@/lib/types";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
};

type Props = {
  title: string;
  subtitle?: string;
  user: User;
  children: ReactNode;
  headerActions?: ReactNode;
  showHeaderControls?: boolean;
};

type ShellNotification = {
  id: string;
  at: string;
  title: string;
  detail: string;
  tone: "critical" | "success" | "info";
};

const NOTIFICATION_READ_KEY = "raven.notifications.readThrough";

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function titleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function isRoutineHealthCheckPassed(log: AuditLogRecord) {
  return log.entity_type === "node" && log.action === "health_check_passed";
}

function buildShellNotifications(activeMessages: MessageIncident[], archivedMessages: MessageIncident[], auditLogs: AuditLogRecord[]) {
  const notifications: ShellNotification[] = [];

  for (const message of [...activeMessages, ...archivedMessages]) {
    const nodeName = message.node?.name ?? `Node ${message.incident.node_id}`;
    notifications.push({
      id: `incident:${message.incident.id}:started`,
      at: message.incident.started_at,
      title: `${nodeName} outage detected`,
      detail: message.incident.summary,
      tone: "critical",
    });

    if (message.incident.resolved_at) {
      notifications.push({
        id: `incident:${message.incident.id}:resolved`,
        at: message.incident.resolved_at,
        title: `${nodeName} outage resolved`,
        detail: `Resolution recorded for ${message.incident.failure_type}.`,
        tone: "success",
      });
    }
  }

  for (const log of auditLogs.filter((item) => !isRoutineHealthCheckPassed(item)).slice(0, 25)) {
    notifications.push({
      id: `audit:${log.id}`,
      at: log.created_at,
      title: `${titleCase(log.entity_type)} ${titleCase(log.action)}`,
      detail: `Entity ${log.entity_id}${log.actor_user_id ? ` by user ${log.actor_user_id}` : ""}`,
      tone: "info",
    });
  }

  return notifications.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}

export function AppShell({ title, subtitle, user, children, headerActions, showHeaderControls = true }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notifications, setNotifications] = useState<ShellNotification[]>([]);
  const [readThrough, setReadThrough] = useState(() => {
    if (typeof window === "undefined") {
      return Date.now();
    }
    const stored = window.localStorage.getItem(NOTIFICATION_READ_KEY);
    if (stored) {
      return Number(stored);
    }
    const initial = Date.now();
    window.localStorage.setItem(NOTIFICATION_READ_KEY, String(initial));
    return initial;
  });
  const navItems: NavItem[] = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/messages", label: "Message Center", icon: MessageSquare },
    { href: "/alerts", label: "Alerts", icon: Bell },
    { href: "#validations", label: "Validations", icon: ShieldCheck, disabled: true },
    { href: "#remediations", label: "Remediations", icon: Zap, disabled: true },
    { href: "#automations", label: "Automations", icon: Bot, disabled: true },
    { href: "/infrastructure", label: "Infrastructure", icon: Server },
    { href: "#integrations", label: "Integrations", icon: Network, disabled: true },
    { href: "/reports", label: "Reports", icon: BarChart3 },
    { href: "/settings", label: "Settings", icon: Settings },
    ...(user.role === "admin" ? [{ href: "/credentials", label: "Credentials", icon: KeyRound }] : []),
  ];
  const userInitials = initials(user.full_name) || user.username.slice(0, 2).toUpperCase();
  const ToggleIcon = sidebarCollapsed ? PanelLeftOpen : PanelLeftClose;
  const unreadNotifications = useMemo(
    () => notifications.filter((notification) => new Date(notification.at).getTime() > readThrough),
    [notifications, readThrough],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadNotifications() {
      try {
        const [activeMessages, archivedMessages, auditLogs] = await Promise.all([
          apiFetch<MessageIncident[]>("/messages"),
          apiFetch<MessageIncident[]>("/messages?archived=true"),
          apiFetch<AuditLogRecord[]>("/audit/logs"),
        ]);
        if (!cancelled) {
          setNotifications(buildShellNotifications(activeMessages, archivedMessages, auditLogs));
        }
      } catch {
        if (!cancelled) {
          setNotifications([]);
        }
      }
    }

    void loadNotifications();
    const interval = window.setInterval(loadNotifications, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  function markNotificationsRead() {
    const nextReadThrough = Math.max(Date.now(), ...notifications.map((notification) => new Date(notification.at).getTime()));
    setReadThrough(nextReadThrough);
    window.localStorage.setItem(NOTIFICATION_READ_KEY, String(nextReadThrough));
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#F7F8FB] text-[#111827] dark:bg-[#070B16] dark:text-slate-100">
      <aside className={`hidden h-screen shrink-0 flex-col border-r border-slate-800 bg-[#050814] py-5 text-white shadow-[12px_0_30px_rgba(2,6,23,0.18)] transition-all duration-200 lg:flex ${sidebarCollapsed ? "w-[76px] px-2" : "w-[240px] px-3"}`}>
        <Link href="/" className={`flex items-center gap-3 ${sidebarCollapsed ? "justify-center px-0" : "px-3"}`} aria-label="RAVEN dashboard">
          <Image
            src="/brand/raven-square-logo.png"
            alt="RAVEN logo"
            width={40}
            height={40}
            className="h-10 w-10 rounded-2xl object-cover"
            priority
          />
          {sidebarCollapsed ? null : <span className="text-lg font-bold tracking-[0.22em]">RAVEN</span>}
        </Link>

        <nav className="mt-8 flex-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            const className = `flex items-center rounded-2xl text-sm font-medium transition ${
              active
                ? "bg-[#2B195D] text-white shadow-[0_10px_24px_rgba(124,58,237,0.28)] ring-1 ring-purple-400/20"
                : "text-slate-400 hover:bg-[#0B1020] hover:text-white"
            } ${sidebarCollapsed ? "h-11 justify-center px-0" : "gap-3 px-3 py-2.5"} ${item.disabled ? "cursor-default" : ""}`;

            if (item.disabled) {
              return (
                <div key={item.label} className={className} aria-disabled="true" title={sidebarCollapsed ? item.label : undefined}>
                  <Icon className={`${sidebarCollapsed ? "h-5 w-5" : "h-4 w-4"}`} />
                  {sidebarCollapsed ? null : <span>{item.label}</span>}
                </div>
              );
            }

            return (
              <Link key={item.label} href={item.href} className={className} title={sidebarCollapsed ? item.label : undefined} aria-label={sidebarCollapsed ? item.label : undefined}>
                <Icon className={`${sidebarCollapsed ? "h-5 w-5" : "h-4 w-4"}`} />
                {sidebarCollapsed ? null : <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {sidebarCollapsed ? (
          <div className="flex justify-center border-t border-slate-800 pt-4">
            <div
              className="grid h-10 w-10 place-items-center rounded-full bg-[#2B195D] text-sm font-bold text-white ring-1 ring-purple-400/30"
              title={`${user.full_name} (${user.role})`}
            >
              {userInitials}
            </div>
          </div>
        ) : (
          <div className="space-y-3 border-t border-slate-800 pt-4">
            <div className="rounded-2xl border border-slate-800 bg-[#0B1020] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">Organization</p>
              <p className="mt-1 text-sm font-semibold text-white">Acme Corporation</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-[#0B1020] p-3">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#2B195D] text-sm font-bold text-white ring-1 ring-purple-400/30">
                  {userInitials}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-white">{user.full_name}</p>
                  <p className="text-xs capitalize text-slate-400">{user.role}</p>
                </div>
                <ChevronDown className="h-4 w-4 text-slate-500" />
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <button
                  type="button"
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white"
                >
                  Manage
                </button>
                <button
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white"
                  onClick={() => {
                    clearToken();
                    router.replace("/login");
                  }}
                >
                  Sign out
                </button>
              </div>
            </div>
          </div>
        )}
      </aside>

      <main className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[#E5E7EB] bg-white px-4 shadow-sm dark:border-slate-800 dark:bg-[#050814] lg:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!sidebarCollapsed}
              className="grid h-10 w-10 place-items-center rounded-xl border border-[#E5E7EB] text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:text-slate-300 dark:hover:border-purple-500"
              onClick={() => setSidebarCollapsed((current) => !current)}
            >
              <ToggleIcon className="h-5 w-5" />
            </button>
            <div className="lg:hidden">
              <span className="text-sm font-bold tracking-[0.22em] text-[#111827] dark:text-white">RAVEN</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <label className="hidden h-10 w-[340px] items-center gap-2 rounded-2xl border border-[#E5E7EB] bg-[#F7F8FB] px-3 text-sm text-[#64748B] shadow-inner dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-400 md:flex">
              <Search className="h-4 w-4" />
              <input
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none placeholder:text-[#64748B] dark:placeholder:text-slate-500"
                placeholder="Search alerts, assets, workflows..."
              />
              <span className="rounded-md border border-[#E5E7EB] bg-white px-1.5 py-0.5 text-[11px] font-semibold text-[#64748B] dark:border-slate-800 dark:bg-[#050814]">⌘ K</span>
            </label>
            <div className="relative">
              <button
                type="button"
                aria-label="Open unread notifications"
                aria-expanded={notificationOpen}
                className="relative grid h-10 w-10 place-items-center rounded-xl border border-[#E5E7EB] bg-white text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-300"
                onClick={() => setNotificationOpen((current) => !current)}
              >
                <Bell className="h-5 w-5" />
                {unreadNotifications.length ? (
                  <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#7C3AED] dark:border-[#050814]" />
                ) : null}
              </button>
              {notificationOpen ? (
                <div className="absolute right-0 top-12 z-50 w-[360px] overflow-hidden rounded-[1.5rem] border border-[#E5E7EB] bg-white shadow-[0_24px_60px_rgba(15,23,42,0.18)] dark:border-slate-800 dark:bg-[#050814]">
                  <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
                    <div>
                      <p className="text-sm font-semibold text-[#111827] dark:text-white">Unread notifications</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{unreadNotifications.length} new</p>
                    </div>
                    <button
                      type="button"
                      className="rounded-full bg-panel px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:text-[#7C3AED] dark:bg-[#0B1020] dark:text-slate-200"
                      onClick={markNotificationsRead}
                      disabled={!unreadNotifications.length}
                    >
                      Mark read
                    </button>
                  </div>
                  <div className="max-h-[360px] overflow-y-auto">
                    {unreadNotifications.length ? unreadNotifications.slice(0, 8).map((notification) => (
                      <div key={notification.id} className="border-b border-slate-100 px-4 py-3 last:border-b-0 dark:border-slate-800">
                        <div className="flex items-start gap-3">
                          <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                            notification.tone === "critical"
                              ? "bg-rose-500"
                              : notification.tone === "success"
                                ? "bg-emerald-500"
                                : "bg-[#7C3AED]"
                          }`} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-[#111827] dark:text-white">{notification.title}</p>
                            <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{notification.detail}</p>
                            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">{new Date(notification.at).toLocaleString()}</p>
                          </div>
                        </div>
                      </div>
                    )) : (
                      <div className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                        No unread notifications.
                      </div>
                    )}
                  </div>
                  <Link
                    href="/alerts"
                    className="block border-t border-slate-200 px-4 py-3 text-center text-sm font-semibold text-[#7C3AED] transition hover:bg-panel dark:border-slate-800 dark:hover:bg-[#0B1020]"
                    onClick={() => setNotificationOpen(false)}
                  >
                    View all alerts
                  </Link>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <section className="border-b border-[#E5E7EB] bg-[#F7F8FB] px-4 py-6 dark:border-slate-800 dark:bg-[#070B16] lg:px-8">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-[#111827] dark:text-white">{title}</h1>
                {subtitle ? <p className="mt-2 text-sm text-[#64748B] dark:text-slate-400">{subtitle}</p> : null}
              </div>
              {headerActions ? (
                <div className="flex flex-wrap items-center gap-3">{headerActions}</div>
              ) : showHeaderControls ? (
                <div className="flex flex-wrap items-center gap-3">
                  <select className="h-10 rounded-xl border border-[#E5E7EB] bg-white px-3 text-sm font-medium text-[#111827] shadow-sm outline-none transition focus:border-[#7C3AED] dark:border-slate-800 dark:bg-[#050814] dark:text-slate-100">
                    <option>Last 24 hours</option>
                    <option>Last 7 days</option>
                    <option>Last 30 days</option>
                  </select>
                  <button className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#7C3AED] px-4 text-sm font-semibold text-white shadow-[0_10px_22px_rgba(124,58,237,0.25)] transition hover:bg-[#6D28D9] dark:shadow-none">
                    <SlidersHorizontal className="h-4 w-4" />
                    Customize
                  </button>
                </div>
              ) : null}
            </div>
          </section>

          <section className="px-4 py-6 lg:px-8">{children}</section>
        </div>
      </main>

      <PlatformChatWidget />
    </div>
  );
}
