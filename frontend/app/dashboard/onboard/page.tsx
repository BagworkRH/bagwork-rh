"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { apiRequest } from "@/lib/api";
import type { SellerProfile } from "@/types";

type Step = "account" | "x" | "wallet" | "code" | "done";

/**
 * Seller onboarding flow (Spec 01):
 * 1. X account  2. Wallet  3. Seller profile/code  4. Confirmation
 */
export default function OnboardPage() {
  const { user, register, login, loadDashboard } = useAuth();
  const { connection, connect, error: walletError } = useWallet();
  const [step, setStep] = useState<Step>(user ? "x" : "account");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sellerCode, setSellerCode] = useState<string>("");

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, username, password);
      const p = await apiRequest<SellerProfile>("/api/v1/me/seller/", {
        method: "POST",
        body: { display_name: username },
        auth: true,
      });
      setSellerCode(p.seller_code);
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConnectWallet() {
    setBusy(true);
    setError(null);
    try {
      const conn = await connect();
      if (!conn) {
        setError(walletError ?? "Wallet connection failed.");
        setBusy(false);
        return;
      }
      await loadDashboard();
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wallet step failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container section" style={{ maxWidth: 680 }}>
      <h1>Onboard a seller</h1>
<div className="stepper">
        <div className="step">
          <h3>Step 1 — {step === "account" ? "Create account" : "X account"}</h3>
          {step === "account" && !user && (
            <div>
              <form className="card" onSubmit={handleSignup}>
                <label className="field">
                  Email
                  <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
                <label className="field">
                  Username
                  <input type="text" required value={username} onChange={(e) => setUsername(e.target.value)} />
                </label>
                <label className="field">
                  Password
                  <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
                </label>
                <button className="btn btn-primary" disabled={busy}>Create account</button>
              </form>
              <p className="muted">
                Already have an account?{" "}
                <button className="btn btn-ghost btn-sm" onClick={handleLogin}>Sign in</button>
              </p>
            </div>
          )}

          {step !== "account" && (
            <div className="card">
              {user ? (
                <>
                  <p>X account: <strong>@{user.username}</strong> <span className="badge badge-ok">Connected (mock)</span></p>
                  <p className="muted">
                    Production uses the official X OAuth flow with only the required permissions.
                  </p>
                  <button className="btn btn-primary" onClick={() => setStep("wallet")}>
                    Continue to wallet
                  </button>
                </>
              ) : (
                <p className="muted">Create an account first.</p>
              )}
            </div>
          )}
        </div>

        <div className="step">
          <h3>Step 2 — Connect wallet</h3>
          <div className="card">
            {connection.status === "connected" ? (
              <p>
                Wallet connected: <strong>{connection.address}</strong> on chain {connection.chainId}.{" "}
                <span className="badge badge-ok">OK</span>
              </p>
            ) : (
              <p className="muted">Connect an EVM wallet. We never ask for your private key.</p>
            )}
            {connection.status !== "connected" && (
              <button className="btn btn-primary" onClick={() => void handleConnectWallet()}>
                Connect wallet
              </button>
            )}
            {connection.status === "connected" && step !== "done" && (
              <button className="btn btn-primary" onClick={() => setStep("code")}>Continue</button>
            )}
          </div>
        </div>
<div className="step">
          <h3>Step 3 — Seller profile &amp; code</h3>
          {sellerCode ? (
            <div className="card">
              <p>
                Your unique seller code: <code className="wallet-chip">{sellerCode}</code>
              </p>
              <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard?.writeText(sellerCode)}>
                Copy code
              </button>
              <p className="muted">
                Include the code in qualifying posts where the campaign requires it. It is an
                additional matching signal, not proof of authorship.
              </p>
              <button className="btn btn-primary" onClick={() => setStep("done")}>Finish</button>
            </div>
          ) : (
            <p className="muted">Your code is generated automatically after signup.</p>
          )}
        </div>

        <div className="step">
          <h3>Step 4 — Confirmation</h3>
          {step === "done" ? (
            <div className="card">
              <h3>You&apos;re all set 🎉</h3>
              <ul>
                <li>X account linked</li>
                <li>Wallet connected</li>
                <li>Seller code ready: {sellerCode}</li>
              </ul>
              <Link className="btn btn-primary" href="/dashboard">Go to dashboard</Link>
            </div>
          ) : (
            <p className="muted">Complete the earlier steps to confirm.</p>
          )}
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
    </div>
  );
}
