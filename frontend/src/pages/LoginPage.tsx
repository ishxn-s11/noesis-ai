import { useState } from "react";
import { api, setSession } from "../api";

interface AuthResponse {
  access_token: string;
  user: { id: string; email: string; tenant_id: string; role: string };
}

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("register");
  const [tenant, setTenant] = useState("My Research Lab");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = mode === "register" ? "/api/auth/register" : "/api/auth/login";
      const body =
        mode === "register"
          ? { tenant_name: tenant, email, password, full_name: name }
          : { email, password };
      const resp = await api<AuthResponse>(path, { method: "POST", body: JSON.stringify(body) });
      setSession(resp.access_token, resp.user);
      window.location.hash = "#/";
      window.location.reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="display-sm">NOESIS</div>
          <div className="eyebrow mt-2">Autonomous Astrophysics Research</div>
        </div>
        <form onSubmit={submit} className="card space-y-4">
          <div className="flex gap-2 text-sm">
            {(["register", "login"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={mode === m ? "btn-primary flex-1" : "btn-ghost flex-1"}
              >
                {m === "register" ? "Create lab" : "Sign in"}
              </button>
            ))}
          </div>
          {mode === "register" && (
            <>
              <label className="block text-xs text-slate-400">
                Lab / tenant name
                <input className="input mt-1" value={tenant} onChange={(e) => setTenant(e.target.value)} />
              </label>
              <label className="block text-xs text-slate-400">
                Full name
                <input className="input mt-1" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
            </>
          )}
          <label className="block text-xs text-slate-400">
            Email
            <input
              className="input mt-1"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="block text-xs text-slate-400">
            Password (min 8 chars)
            <input
              className="input mt-1"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <div className="text-sm text-rose-400">{error}</div>}
          <button className="btn-primary w-full justify-center" disabled={busy}>
            {busy ? "Working…" : mode === "register" ? "Create lab & sign in" : "Sign in"}
          </button>
          <p className="text-xs leading-relaxed text-slate-500">
            Tenants are fully isolated (DB-level row scoping). First user of a lab becomes
            its admin.
          </p>
        </form>
      </div>
    </div>
  );
}