"use client";

import { useEffect, useState } from "react";
import ConnectWalletButton from "@/components/ConnectWalletButton";
import { useAuth } from "@/hooks/useAuth";
import { apiRequest } from "@/lib/api";
import { shortenAddress } from "@/lib/constants";
import type { Claim, Reward, Wallet } from "@/types";

export default function WalletPage() {
  const { user } = useAuth();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [claims, setClaims] = useState<Omit<Claim, "chain_id">[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiRequest<Wallet[]>("/api/v1/me/wallets/", { auth: true })
      .then(setWallets)
      .catch(() => setWallets([]));
    apiRequest<Reward[]>("/api/v1/rewards/", { auth: true })
      .then(setRewards)
      .catch(() => setRewards([]));
    apiRequest<Omit<Claim, "chain_id">[]>("/api/v1/me/claims/", { auth: true })
      .then(setClaims)
      .catch(() => setClaims([]));
  }, [user]);

  const available = rewards.filter((r) => r.status === "AVAILABLE");

  async function handleClaim(reward: Reward) {
    const wallet = wallets.find((w) => w.verified);
    if (!wallet) {
      setMessage("Connect and verify a wallet before claiming.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const claim = await apiRequest<Claim>("/api/v1/claims/", {
        method: "POST",
        body: { reward_id: reward.id, wallet_id: wallet.id },
        auth: true,
      });
      setMessage(
        `Claim created (${claim.status}) for ${claim.amount} ${claim.token_symbol}. Submit the transaction from your wallet.`
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Claim failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container section" style={{ maxWidth: 820 }}>
      <h1>Wallet</h1>
      {!user ? (
        <div className="card">
          <p className="muted">Sign in to manage your wallet and rewards.</p>
        </div>
      ) : (
        <div className="grid">
          <div>
            <ConnectWalletButton />

            <div className="card" style={{ marginTop: 20 }}>
              <h3>Connected wallets</h3>
              {wallets.length === 0 ? (
                <p className="muted">No wallets connected yet.</p>
              ) : (
                <ul>
                  {wallets.map((w) => (
                    <li key={w.id}>
                      {shortenAddress(w.address)} (chain {w.chain_id}){" "}
                      {w.verified ? (
                        <span className="badge badge-ok">verified</span>
                      ) : (
                        <span className="badge badge-muted">unverified</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div>
            <div className="card">
              <h3>Available rewards</h3>
              {available.length === 0 ? (
                <p className="muted">No rewards available to claim.</p>
              ) : (
                available.map((r) => (
                  <div className="row" key={r.id}>
                    <span>
                      {r.amount} {r.token_symbol}
                    </span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleClaim(r)}
                      disabled={busy}
                    >
                      Claim
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="card" style={{ marginTop: 20 }}>
              <h3>Claim history</h3>
              {claims.length === 0 ? (
                <p className="muted">No claims yet.</p>
              ) : (
                <ul>
                  {claims.map((c) => (
                    <li key={c.id}>
                      {c.amount} {c.token_symbol} — {c.status}
                      {c.transaction_hash ? (
                        <>
                          {" "}
                          <code>{shortenAddress(c.transaction_hash, 8)}</code>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {message && <div className="banner banner-error">{message}</div>}
    </div>
  );
}