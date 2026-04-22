"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode } from "react";

import { clearToken } from "@/lib/api";
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

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(217,119,6,0.22),_transparent_28%),linear-gradient(180deg,_#f6f0e6_0%,_#ece4d8_100%)] text-ink">
      <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6 lg:px-8">
        <aside className="hidden w-72 shrink-0 rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur lg:flex lg:flex-col">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-ember">RAVEN</p>
            <h1 className="mt-4 text-3xl font-semibold leading-tight">Semi-autonomous remediation, gated by humans.</h1>
            <p className="mt-3 text-sm text-slate-600">Monitor application nodes, surface AI recommendations, and queue only approved remediations.</p>
          </div>
          <nav className="mt-10 space-y-2">
            {navItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`block rounded-2xl px-4 py-3 text-sm font-medium transition ${active ? "bg-ink text-white" : "bg-panel text-slate-700 hover:bg-white"}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto rounded-2xl bg-ink p-4 text-white">
            <p className="text-xs uppercase tracking-[0.2em] text-white/60">{user.role}</p>
            <p className="mt-2 font-semibold">{user.full_name}</p>
            <p className="text-sm text-white/70">@{user.username}</p>
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
          <header className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-panel backdrop-blur">
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-ember">Control Center</p>
                <h2 className="mt-2 text-3xl font-semibold">{title}</h2>
                <p className="mt-2 max-w-3xl text-sm text-slate-600">{subtitle}</p>
              </div>
              <div className="rounded-2xl bg-panel px-4 py-3 text-sm text-slate-600">
                <span className="font-semibold text-ink">{user.role}</span> privileges active
              </div>
            </div>
          </header>
          <div className="mt-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
