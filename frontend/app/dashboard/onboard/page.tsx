"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { apiRequest } from "@/lib/api";
import {
  connectPlatform,
  disconnectPlatform,
  getConnections,
  getPlatforms,
} from "@/services/social";
import type { SellerProfile, SocialAccount, SocialPlatform } from "@/types";

type Step = "account" | "x" | "wallet" | "code" | "done";

/**
 * Seller onboarding flow (Spec 01):
 * 1. Social accounts  2. Wallet  3. Seller profile/code  4. Confirmation
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
  const [available, setAvailable] = useState<SocialPlatform[]>([]);
  const [linked, setLinked] = useState<SocialAccount[]>([]);
  const [platformBusy, setPlatformBusy] = useState<SocialPlatform | null>(null);
  const [platformError, setPlatformError] = useState<string | null>(null);

  /**
   * Which platforms this build can connect, and which ones this seller has
   * already linked. Two calls because they answer different questions: what is
   * available is a property of the build, what is linked is a property of you.
   */
  const loadPlatforms = useCallback(async () => {
    try {
      const res = await getPlatforms();
      setAvailable(res.platforms.map((p) => p.id));
    } catch {
      setAvailable([]);
    }
    if (!user) return;
    try {
      const res = await getConnections();
      setLinked(res.connections);
    } catch {
      setLinked([]);
    }
  }, [user]);

  useEffect(() => {
    void loadPlatforms();
  }, [loadPlatforms]);

  /**
   * Begin OAuth for one platform.
   *
   * The provider hands us a URL to open; it then redirects back to the
   * callback endpoint on this origin. We navigate rather than fetch because
   * the exchange has to happen in the browser.
   */
  async function handleConnect(platform: SocialPlatform) {
    setPlatformBusy(platform);
    setPlatformError(null);
    try {
      const res = await connectPlatform(platform);
      window.location.href = res.authorize_url;
    } catch (err) {
      setPlatformError(
        err instanceof Error ? err.message : "Could not start the connection."
      );
      setPlatformBusy(null);
    }
  }

  async function handleDisconnect(platform: SocialPlatform) {
    setPlatformBusy(platform);
    setPlatformError(null);
    try {
      await disconnectPlatform(platform);
      setLinked((prev) => prev.filter((a) => a.platform !== platform));
    } catch (err) {
      setPlatformError(
        err instanceof Error ? err.message : "Could not disconnect."
      );
    } finally {
      setPlatformBusy(null);
    }
  }

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
          <h3>Step 1 — {step === "account" ? "Create account" : "Social accounts"}</h3>
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
                  <p className="muted">
                    Link the platforms you publish on. We use only the read
                    permissions we need, and we never post on your behalf.
                  </p>

                  {platformError && (
                    <div className="banner banner-error">{platformError}</div>
                  )}

                  {available.length === 0 && (
                    <p className="muted">
                      No platforms available in this build.
                    </p>
                  )}

                  {available.map((platform) => {
                    const account = linked.find((a) => a.platform === platform);
                    const busy = platformBusy === platform;
                    return (
                      <div className="row" key={platform}>
                        <div>
                          <strong>
                            {platform === "x" ? "X (Twitter)" : "TikTok"}
                          </strong>
                          {account ? (
                            <>
                              {" "}
                              <span className="badge badge-ok">Connected</span>
                              <div className="muted">@{account.username}</div>
                            </>
                          ) : (
                            <div className="muted">Not connected</div>
                          )}
                        </div>
                        {account ? (
                          <button
                            className="btn btn-outline btn-sm"
                            disabled={busy}
                            onClick={() => void handleDisconnect(platform)}
                          >
                            {busy ? "Disconnecting…" : "Disconnect"}
                          </button>
                        ) : (
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busy}
                            onClick={() => void handleConnect(platform)}
                          >
                            {busy ? "Redirecting…" : "Connect"}
                          </button>
                        )}
                      </div>
                    );
                  })}

                  <button
                    className="btn btn-primary"
                    style={{ marginTop: 12 }}
                    onClick={() => setStep("wallet")}
                  >
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
                <li>
                  Social accounts:{" "}
                  {linked.length > 0
                    ? linked.map((a) => `@${a.username}`).join(", ")
                    : "none linked"}
                </li>
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
