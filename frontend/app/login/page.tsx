"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { API_BASE, requireSession, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123!");
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
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_right,_rgba(166,61,64,0.18),_transparent_24%),radial-gradient(circle_at_bottom_left,_rgba(217,119,6,0.18),_transparent_30%),linear-gradient(180deg,_#f6f0e6_0%,_#e8ddce_100%)] px-4 py-10">
      <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[2rem] border border-white/70 bg-white/75 p-8 shadow-panel backdrop-blur">
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-ember">RAVEN</p>
          <h1 className="mt-6 max-w-xl text-5xl font-semibold leading-[1.05]">Human-approved remediation for web application incidents.</h1>
          <p className="mt-5 max-w-2xl text-lg text-slate-600">
            Detect failures, generate AI-assisted troubleshooting, and queue only approved remediations through a controlled runner.
          </p>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {[
              ["Observe", "Continuous checks track health by ping, HTTP, HTTPS, and API probes."],
              ["Decide", "The agent explains failure patterns and recommends only catalog-approved actions."],
              ["Execute", "Operators approve actions, and the secure runner logs every execution and validation step."],
            ].map(([title, text]) => (
              <div key={title} className="rounded-3xl bg-panel p-5">
                <h2 className="text-lg font-semibold">{title}</h2>
                <p className="mt-2 text-sm text-slate-600">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[2rem] border border-white/70 bg-ink p-8 text-white shadow-panel">
          <p className="text-xs uppercase tracking-[0.35em] text-white/60">Access</p>
          <h2 className="mt-4 text-3xl font-semibold">Sign in to the control plane</h2>
          <p className="mt-3 text-sm text-white/70">Seeded accounts are available for the MVP. Change them before any shared deployment.</p>
          <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
            <label className="block text-sm">
              <span className="mb-2 block text-white/70">Username</span>
              <input value={username} onChange={(event) => setUsername(event.target.value)} className="w-full rounded-2xl border border-white/15 bg-white/10 px-4 py-3 outline-none focus:border-white/40" />
            </label>
            <label className="block text-sm">
              <span className="mb-2 block text-white/70">Password</span>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-2xl border border-white/15 bg-white/10 px-4 py-3 outline-none focus:border-white/40" />
            </label>
            {error ? <p className="rounded-2xl bg-rose-500/15 px-4 py-3 text-sm text-rose-100">{error}</p> : null}
            <button disabled={loading} className="w-full rounded-full bg-white px-5 py-3 text-sm font-semibold text-ink">
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <div className="mt-8 rounded-3xl bg-white/5 p-5 text-sm text-white/70">
            <p className="font-semibold text-white">Seed credentials</p>
            <p className="mt-2">`admin / admin123!`</p>
            <p>`operator / operator123!`</p>
            <p>`viewer / viewer123!`</p>
          </div>
        </section>
      </div>
    </div>
  );
}
