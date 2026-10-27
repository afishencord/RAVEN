"use client";

import { FormEvent, useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import { API_BASE, requireSession, setToken } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    requireSession().then((user) => {
      if (user) {
        router.replace("/");
      }
    });
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        throw new Error("Invalid credentials");
      }
      const payload = await response.json();
      setToken(payload.access_token);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#F7F8FB] px-4 py-10 text-[#111827] dark:bg-[#070B16] dark:text-slate-100">
      <div className="mx-auto flex max-w-[1780px] justify-end pb-4">
        <ThemeToggle />
      </div>
      <div className="mx-auto grid max-w-[1780px] gap-8 lg:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1300px)_420px]">
        <section className="flex aspect-[13/6] w-full max-w-[1300px] items-center justify-center overflow-hidden rounded-[2rem] border border-[#E5E7EB] bg-white shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none lg:h-[600px]">
          <Image
            src="/brand/raven-landing-light.png"
            alt="RAVEN platform overview"
            width={1254}
            height={521}
            className="h-full w-full object-cover dark:hidden"
            priority
          />
          <Image
            src="/brand/raven-landing-dark.png"
            alt="RAVEN platform overview"
            width={1254}
            height={574}
            className="hidden h-full w-full object-cover dark:block"
            priority
          />
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-[#050814] p-8 text-white shadow-panel dark:border-slate-800 dark:bg-[#050814] dark:shadow-none lg:min-h-[600px]">
          <p className="text-xs uppercase tracking-[0.35em] text-white/60">Access</p>
          <h2 className="mt-4 text-3xl font-semibold">Sign in to the control plane</h2>
          <p className="mt-3 text-sm text-white/70">Use the account provisioned by your RAVEN administrator.</p>
          <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
            <label className="block text-sm">
              <span className="mb-2 block text-white/70">Username</span>
              <input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} className="w-full rounded-2xl border border-slate-700 bg-[#0B1020] px-4 py-3 text-white caret-white outline-none focus:border-ember" />
            </label>
            <label className="block text-sm">
              <span className="mb-2 block text-white/70">Password</span>
              <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-2xl border border-slate-700 bg-[#0B1020] px-4 py-3 text-white caret-white outline-none focus:border-ember" />
            </label>
            {error ? <p className="rounded-2xl bg-rose-500/15 px-4 py-3 text-sm text-rose-100">{error}</p> : null}
            <button disabled={loading} className="w-full rounded-full bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:text-ember">
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
