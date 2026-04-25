"use client";

import {
  BarChart3,
  Bell,
  Bot,
  ChevronDown,
  KeyRound,
  LayoutDashboard,
  Menu,
  MessageCircle,
  MessageSquare,
  Network,
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
import { ReactNode } from "react";

import { clearToken } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";
import { User } from "@/lib/types";

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

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function AppShell({ title, subtitle, user, children, headerActions, showHeaderControls = true }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const navItems: NavItem[] = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/messages", label: "Message Center", icon: MessageSquare },
    { href: "#alerts", label: "Alerts", icon: Bell, disabled: true },
    { href: "#validations", label: "Validations", icon: ShieldCheck, disabled: true },
    { href: "#remediations", label: "Remediations", icon: Zap, disabled: true },
    { href: "#automations", label: "Automations", icon: Bot, disabled: true },
    { href: "/infrastructure", label: "Infrastructure", icon: Server },
    { href: "#integrations", label: "Integrations", icon: Network, disabled: true },
    { href: "#reports", label: "Reports", icon: BarChart3, disabled: true },
    { href: "#settings", label: "Settings", icon: Settings, disabled: true },
    ...(user.role === "admin" ? [{ href: "/credentials", label: "Credentials", icon: KeyRound }] : []),
  ];
  const userInitials = initials(user.full_name) || user.username.slice(0, 2).toUpperCase();

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#F7F8FB] text-[#111827] dark:bg-[#070B16] dark:text-slate-100">
      <aside className="hidden h-screen w-[240px] shrink-0 flex-col border-r border-slate-800 bg-[#050814] px-3 py-5 text-white shadow-[12px_0_30px_rgba(2,6,23,0.18)] lg:flex">
        <Link href="/" className="flex items-center gap-3 px-3">
          <Image
            src="/brand/raven-square-logo.png"
            alt="RAVEN logo"
            width={40}
            height={40}
            className="h-10 w-10 rounded-2xl object-cover"
            priority
          />
          <span className="text-lg font-bold tracking-[0.22em]">RAVEN</span>
        </Link>

        <nav className="mt-8 flex-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            const className = `flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition ${
              active
                ? "bg-[#2B195D] text-white shadow-[0_10px_24px_rgba(124,58,237,0.28)] ring-1 ring-purple-400/20"
                : "text-slate-400 hover:bg-[#0B1020] hover:text-white"
            } ${item.disabled ? "cursor-default" : ""}`;

            if (item.disabled) {
              return (
                <div key={item.label} className={className} aria-disabled="true">
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </div>
              );
            }

            return (
              <Link key={item.label} href={item.href} className={className}>
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

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
              <ThemeToggle />
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
      </aside>

      <main className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[#E5E7EB] bg-white px-4 shadow-sm dark:border-slate-800 dark:bg-[#050814] lg:px-6">
          <div className="flex items-center gap-3">
            <button className="grid h-10 w-10 place-items-center rounded-xl border border-[#E5E7EB] text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:text-slate-300 dark:hover:border-purple-500">
              <Menu className="h-5 w-5" />
            </button>
            <div className="lg:hidden">
              <span className="text-sm font-bold tracking-[0.22em] text-[#111827] dark:text-white">RAVEN</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <label className="hidden h-10 w-[340px] items-center gap-2 rounded-2xl border border-[#E5E7EB] bg-[#F7F8FB] px-3 text-sm text-[#64748B] shadow-inner dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-400 md:flex">
              <Search className="h-4 w-4" />
              <input
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm outline-none placeholder:text-[#64748B] dark:placeholder:text-slate-500"
                placeholder="Search alerts, assets, workflows..."
              />
              <span className="rounded-md border border-[#E5E7EB] bg-white px-1.5 py-0.5 text-[11px] font-semibold text-[#64748B] dark:border-slate-800 dark:bg-[#050814]">⌘ K</span>
            </label>
            <button className="relative grid h-10 w-10 place-items-center rounded-xl border border-[#E5E7EB] bg-white text-slate-600 transition hover:border-[#7C3AED] hover:text-[#7C3AED] dark:border-slate-800 dark:bg-[#0B1020] dark:text-slate-300">
              <Bell className="h-5 w-5" />
              <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#7C3AED] dark:border-[#050814]" />
            </button>
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

      <Link
        href="/messages"
        className="fixed bottom-6 right-6 z-40 grid h-14 w-14 place-items-center rounded-full bg-[#7C3AED] text-white shadow-[0_18px_40px_rgba(124,58,237,0.35)] transition hover:-translate-y-0.5 hover:bg-[#6D28D9] dark:shadow-none"
        aria-label="Open message center"
      >
        <MessageCircle className="h-6 w-6" />
      </Link>
    </div>
  );
}
