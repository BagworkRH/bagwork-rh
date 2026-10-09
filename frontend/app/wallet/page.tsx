"use client";

import { useCallback, useEffect, useState } from "react";
import ConnectWalletButton from "@/components/ConnectWalletButton";
import { useAuth } from "@/hooks/useAuth";
import { useClaimFlow } from "@/hooks/useClaimFlow";
import { useWallet } from "@/hooks/useWallet";
import { shortenAddress } from "@/lib/constants";
import { formatAmount } from "@/lib/money";
import { listClaims, listRewards, listWallets } from "@/services/wallet";
import type { Claim, Reward, Wallet } from "@/types";

export default function WalletPage() {
  const { user } = useAuth();
  const { sendTransaction } = useWallet();
  const { step, claimReward, reset } = useClaimFlow();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const [nextWallets, nextRewards, nextClaims] = await Promise.all([
        listWallets(),
        listRewards(),
        listClaims(),
      ]);
      setWallets(nextWallets);
      setRewards(nextRewards);
      setClaims(nextClaims);
    } catch {
      // A failed refresh must not break the page; state stays as it was.
    }
  }, [user]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const available = rewards.filter((r) => r.status === "AVAILABLE");
  const verifiedWallet = wallets.find((w) => w.verified);

  async function handleClaim(reward: Reward) {
    if (!verifiedWallet) return; // guarded by the disabled button below
    reset();
    const claim = await claimReward(reward, verifiedWallet, sendTransaction);
    if (claim) await refresh();
  }

  const busy =
    step.phase === "creating" ||
    step.phase === "authorizing" ||
    step.phase === "awaiting-wallet" ||
    step.phase === "recording";

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
            <ConnectWalletButton onVerified={() => void refresh()} />

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
                      {formatAmount(r.amount)} {r.token_symbol}
                    </span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleClaim(r)}
                      disabled={busy || !verifiedWallet}
                      title={
                        verifiedWallet
                          ? `Claim to ${shortenAddress(verifiedWallet.address)}`
                          : "Verify a wallet before claiming"
                      }
                    >
                      {busy ? "Claiming…" : "Claim"}
                    </button>
                  </div>
                ))
              )}
              {available.length > 0 && !verifiedWallet && (
                <p className="muted">Verify wallet ownership before claiming.</p>
              )}
              <ClaimStatusBanner step={step} />
            </div>

            <div className="card" style={{ marginTop: 20 }}>
              <h3>Claim history</h3>
              {claims.length === 0 ? (
                <p className="muted">No claims yet.</p>
              ) : (
                <ul>
                  {claims.map((c) => (
                    <li key={c.id}>
                      {formatAmount(c.amount)} {c.token_symbol} — {c.status}
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
    </div>
  );
}

function ClaimStatusBanner({ step }: { step: ReturnType<typeof useClaimFlow>["step"] }) {
  if (step.phase === "idle") return null;
  if (step.phase === "error") {
    return <div className="banner banner-error">{step.message}</div>;
  }
  if (step.phase === "submitted") {
    return (
      <div className="banner">
        Claim submitted ({step.claim.status}). Transaction{" "}
        <code>{shortenAddress(step.hash, 8)}</code> — the reward is marked claimed once the
        transaction is confirmed on-chain.
      </div>
    );
  }
  const labels: Record<string, string> = {
    creating: "Creating claim…",
    authorizing: "Requesting claim authorization…",
    "awaiting-wallet": "Confirm the transaction in your wallet…",
    recording: "Recording the transaction…",
  };
  return <div className="banner">{labels[step.phase] ?? ""}</div>;
}