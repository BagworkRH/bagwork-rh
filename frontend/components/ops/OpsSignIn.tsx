"use client";

import { useState } from "react";

import type { User } from "@/types";

/**
 * Sign-in form for the staff console.
 *
 * The console signs staff in here rather than sending them to
 * `/dashboard/onboard`, which is the *creator* onboarding flow — a staff
 * member following that link lands in a seller registration form, which is
 * confusing and, for an admin account, wrong.
 *
 * `onSignIn` is the parent layout's own `login`, passed down as a prop on
 * purpose: `useAuth` is a plain hook rather than a shared context, so calling
 * a different instance's `login` would leave the layout still believing nobody
 * is signed in.
 */
export default function OpsSignIn({
  onSignIn,
}: {
  onSignIn: (email: string, password: string) => Promise<{ user: User }>;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = await onSignIn(email, password);
      if (data.user.is_staff) {
        // A full navigation rather than router.push: the site header holds its
        // own copy of the auth state, so a client-side transition would leave
        // it offering "Onboard" to someone who is already signed in. There is
        // no unsaved state here, so reloading costs nothing.
        window.location.replace("/ops");
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    }
    // Reached when the account is valid but not staff: the layout takes over
    // and explains that.
    setBusy(false);
  }

  return (
    <div className="container section" style={{ maxWidth: 560 }}>
      <h1>Staff console</h1>
      <p className="muted">
        Sign in with a staff account. This area reviews sellers, posts, rewards and risk; it is
        not the creator dashboard.
      </p>

      <div className="card">
        <form onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error ? <p className="modal-message">{error}</p> : null}

          <div className="actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </div>
        </form>

        <p className="muted" style={{ marginTop: 12 }}>
          Looking for your creator account? Use the{" "}
          <a href="/dashboard/onboard">seller sign-in</a> instead.
        </p>
      </div>
    </div>
  );
}
