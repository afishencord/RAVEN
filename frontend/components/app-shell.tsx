"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode } from "react";

import { clearToken } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";
import { User } from "@/lib/types";

type Props = {
  title: string;
  subtitle: string;
  user: User;
  children: ReactNode;
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/messages", label: "Message Center" },
];

export function AppShell({ title, subtitle, user, children }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const showChromeCopy = pathname !== "/" && pathname !== "/messages";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(139,92,246,0.22),_transparent_22%),radial-gradient(circle_at_bottom_right,_rgba(139,92,246,0.1),_transparent_30%),linear-gradient(180deg,_#faf5ff_0%,_#efe7ff_100%)] text-ink dark:bg-[radial-gradient(circle_at_top_left,_rgba(139,92,246,0.08),_transparent_16%),radial-gradient(circle_at_bottom_right,_rgba(124,58,237,0.05),_transparent_22%),linear-gradient(180deg,_#09090f_0%,_#120d1d_100%)] dark:text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6 lg:px-8">
        <aside className="hidden w-72 shrink-0 rounded-[2rem] border border-white/60 bg-white/65 p-6 shadow-panel backdrop-blur dark:border-white/10 dark:bg-slate-950/55 lg:flex lg:flex-col">
          <div>
            <p className="text-2xl font-semibold uppercase tracking-[0.35em] text-ember">RAVEN</p>
            {showChromeCopy ? <h1 className="mt-4 text-3xl font-semibold leading-tight">Semi-autonomous remediation, gated by humans.</h1> : null}
            {showChromeCopy ? <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">Monitor application nodes, surface AI recommendations, and queue only approved remediations.</p> : null}
          </div>
          <nav className="mt-10 space-y-2">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`block rounded-2xl px-4 py-3 text-sm font-medium transition ${active ? "bg-ink text-white dark:bg-ember dark:text-white" : "bg-panel text-slate-700 hover:bg-white dark:bg-white/5 dark:text-slate-200 dark:hover:bg-white/10"}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto rounded-2xl bg-ink p-4 text-white dark:bg-white/5 dark:ring-1 dark:ring-white/10">
            <p className="text-xs uppercase tracking-[0.2em] text-white/60">{user.role}</p>
            <p className="mt-2 font-semibold">{user.full_name}</p>
            <p className="text-sm text-white/70">@{user.username}</p>
            <div className="mt-4">
              <ThemeToggle />
            </div>
            <button
              className="mt-4 rounded-full border border-white/20 px-4 py-2 text-sm"
              onClick={() => {
                clearToken();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </aside>

        <main className="flex-1">
          <header className="rounded-[2rem] border border-white/60 bg-white/65 p-6 shadow-panel backdrop-blur dark:border-white/10 dark:bg-slate-950/55">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-ember">Control Center</p>
                <h2 className="mt-2 text-3xl font-semibold">{title}</h2>
                {showChromeCopy ? <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{subtitle}</p> : null}
              </div>
              <div className="flex items-center gap-3 self-start md:self-auto">
                <div className="rounded-2xl bg-panel px-4 py-3 text-sm text-slate-600 dark:bg-white/5 dark:text-slate-300">
                  <span className="font-semibold text-ink dark:text-white">{user.role}</span> privileges active
                </div>
                <div className="lg:hidden">
                  <ThemeToggle />
                </div>
              </div>
            </div>
          </header>
          <div className="mt-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
