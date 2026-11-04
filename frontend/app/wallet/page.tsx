"use client";

import { useCallback, useEffect, useState } from "react";

import ConnectWalletButton from "@/components/ConnectWalletButton";
import { CoinsIcon, ExternalLinkIcon, WalletIcon } from "@/components/icons";
import { EmptyState, Skeleton, StatGridSkeleton, StatTile } from "@/components/ui";
import { useAuth } from "@/hooks/useAuth";
import { useClaimFlow } from "@/hooks/useClaimFlow";
import { useWallet } from "@/hooks/useWallet";
import { LAUNCH_CHAIN, shortenAddress } from "@/lib/constants";
import { formatAmount } from "@/lib/money";
import { listClaims, listRewards, listWallets } from "@/services/wallet";
import type { Claim, Reward, Wallet } from "@/types";

function claimBadge(status: string): string {
  if (status === "CONFIRMED") return "badge badge-ok";
  if (status === "FAILED" || status === "EXPIRED") return "badge badge-danger";
  if (status === "SUBMITTED" || status === "PENDING") return "badge badge-warn";
  return "badge badge-muted";
}

export default function WalletPage() {
  const { user } = useAuth();
  const { sendTransaction } = useWallet();
  const { step, claimReward, reset } = useClaimFlow();
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [rewards, setRewards] = useState<Reward[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    if (!user) {
      setLoaded(true);
      return;
    }
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
    } finally {
      setLoaded(true);
    }
  }, [user]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const available = rewards.filter((reward) => reward.status === "AVAILABLE");
  const claimed = rewards.filter((reward) => reward.status === "CLAIMED");
  const verifiedWallet = wallets.find((wallet) => wallet.verified);
  const symbol = rewards[0]?.token_symbol ?? LAUNCH_CHAIN.token;

  const totalAvailable = available.reduce((sum, reward) => sum + Number(reward.amount || 0), 0);
  const totalClaimed = claimed.reduce((sum, reward) => sum + Number(reward.amount || 0), 0);

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

  if (!user) {
    return (
      <div style={{ maxWidth: 640 }}>
        <EmptyState
          icon={WalletIcon}
          title="Sign in to manage your wallet"
          action={
            <a href="/dashboard/onboard" className="btn btn-primary">
              Sign in
            </a>
          }
        >
          Your rewards, wallet and claim history live here once you are signed in.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="page-head">
        <div>
          <span className="eyebrow">Earnings</span>
          <h1>Wallet</h1>
          <p className="lede">Claim verified rewards to your own wallet on {LAUNCH_CHAIN.name}.</p>
        </div>
      </div>

      {!loaded ? (
        <StatGridSkeleton count={3} />
      ) : (
        <div className="stat-grid">
          <StatTile
            label="Available to claim"
            value={formatAmount(totalAvailable)}
            unit={symbol}
            icon={CoinsIcon}
            tone="green"
            sub={`${available.length} reward${available.length === 1 ? "" : "s"} ready`}
          />
          <StatTile
            label="Claimed on-chain"
            value={formatAmount(totalClaimed)}
            unit={symbol}
            icon={WalletIcon}
            tone="brand"
            sub={`${claimed.length} settled`}
          />
          <StatTile
            label="Connected wallet"
            value={verifiedWallet ? shortenAddress(verifiedWallet.address) : "None"}
            icon={WalletIcon}
            tone={verifiedWallet ? "green" : "warn"}
            sub={verifiedWallet ? "Verified by signature" : "Verify a wallet to claim"}
          />
        </div>
      )}

      <div className="split">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <div>
                <h3>Available rewards</h3>
                <p className="card-sub">Claimable now to your verified wallet.</p>
              </div>
              {available.length > 0 ? <span className="badge badge-ok">{available.length} ready</span> : null}
            </div>

            {!loaded ? (
              <Skeleton lines={3} />
            ) : available.length === 0 ? (
              <p className="muted">No rewards available to claim yet.</p>
            ) : (
              <ul className="joined-campaigns">
                {available.map((reward) => (
                  <li key={reward.id}>
                    <span style={{ flex: "1 1 auto", minWidth: 0 }}>
                      <span className="money" style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                        {formatAmount(reward.amount)} {reward.token_symbol}
                      </span>
                      <div className="muted" style={{ fontSize: "0.78rem" }}>
                        {reward.campaign ?? "Reward"}
                      </div>
                    </span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleClaim(reward)}
                      disabled={busy || !verifiedWallet}
                      title={
                        verifiedWallet
                          ? `Claim to ${shortenAddress(verifiedWallet.address)}`
                          : "Verify a wallet before claiming"
                      }
                    >
                      {busy ? "Claiming…" : "Claim"}
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {available.length > 0 && !verifiedWallet ? (
              <p className="muted" style={{ marginTop: 12 }}>
                Verify wallet ownership before claiming.
              </p>
            ) : null}
            <ClaimStatusBanner step={step} />
          </div>

          <div className="card card-flush">
            <div className="card-head card-pad" style={{ marginBottom: 0 }}>
              <h3>Claim history</h3>
            </div>
            {!loaded ? (
              <div className="card-pad">
                <Skeleton lines={3} />
              </div>
            ) : claims.length === 0 ? (
              <div className="card-pad">
                <p className="muted">No claims yet.</p>
              </div>
            ) : (
              <div className="table-cards">
                <table>
                  <thead>
                    <tr>
                      <th>Amount</th>
                      <th>Status</th>
                      <th>Transaction</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {claims.map((claim) => (
                      <tr key={claim.id}>
                        <td data-label="Amount" className="money">
                          {formatAmount(claim.amount)} {claim.token_symbol}
                        </td>
                        <td data-label="Status">
                          <span className={claimBadge(claim.status)}>{claim.status}</span>
                        </td>
                        <td data-label="Transaction">
                          {claim.transaction_hash ? (
                            <a
                              href={`${LAUNCH_CHAIN.explorerUrl}/tx/${claim.transaction_hash}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="row"
                              style={{ gap: 4 }}
                            >
                              {shortenAddress(claim.transaction_hash, 6)} <ExternalLinkIcon size={13} />
                            </a>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td data-label="Date" className="muted">
                          {new Date(claim.created_at).toLocaleDateString("en-GB", {
                            day: "numeric",
                            month: "short",
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <ConnectWalletButton onVerified={() => void refresh()} />

          <div className="card">
            <h3>Connected wallets</h3>
            {wallets.length === 0 ? (
              <p className="muted">No wallets connected yet.</p>
            ) : (
              <ul className="joined-campaigns">
                {wallets.map((wallet) => (
                  <li key={wallet.id}>
                    <span className="row" style={{ gap: 8, flex: "1 1 auto" }}>
                      <WalletIcon size={16} />
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.83rem" }}>
                        {shortenAddress(wallet.address)}
                      </span>
                    </span>
                    {wallet.verified ? (
                      <span className="badge badge-ok">Verified</span>
                    ) : (
                      <span className="badge badge-muted">Unverified</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h3>How claiming works</h3>
            <p className="muted" style={{ fontSize: "0.875rem" }}>
              The server signs an EIP-712 authorization and hands your wallet fully
              encoded calldata. Your wallet sends the transaction; the reward is marked
              claimed once it is confirmed on-chain.
            </p>
          </div>
        </div>
      </div>
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
      <div className="banner banner-ok">
        Claim submitted ({step.claim.status}). Transaction <code>{shortenAddress(step.hash, 8)}</code> —
        the reward is marked claimed once the transaction is confirmed on-chain.
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

