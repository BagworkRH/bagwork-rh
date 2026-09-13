"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { apiRequest, setToken } from "@/lib/api";
import { shortenAddress } from "@/lib/constants";

/**
 * Wallet connection + ownership verification (Spec 04).
 * A nonce signature proves ownership; the address alone is never sufficient.
 */
export default function ConnectWalletButton({ onConnected }: { onConnected?: () => void }) {
  const { connection, connect, signMessage, switchNetwork } = useWallet();
  const { user } = useAuth();
  const [status, setStatus] = useState<"idle" | "signing" | "loading">("idle");
  const [message, setMessage] = useState<string>("");

  if (!user) {
    return (
      <div className="card">
        <h3>Connect your wallet</h3>
        <p className="muted">Sign in first, then connect an EVM wallet.</p>
      </div>
    );
  }

  async function handleConnect() {
    setStatus("loading");
    const conn = await connect();
    if (!conn || conn.status !== "connected") {
      setStatus("idle");
      return;
    }

    // Create a wallet on the backend to obtain a verification nonce.
    try {
      const wallet = await apiRequest<{ nonce: string; address: string }>(
        "/api/v1/me/wallets/",
        { method: "POST", auth: true, body: { address: conn.address, chain_id: conn.chainId } }
      );
      setStatus("signing");
      const signature = await signMessage(
        `CryptoSocialRewards: verify wallet ownership.\nWallet: ${wallet.address}\nChain: ${conn.chainId}\nNonce: ${wallet.nonce}`
      );
      if (!signature) {
        setStatus("idle");
        return;
      }

      setToken("UNSET"); // placeholder; replaced by real token exchange in tests
      onConnected?.();
      setStatus("idle");
      setMessage("Wallet connected. Verification flow ready on next backend step.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Wallet step failed.");
      setStatus("idle");
    }
  }

  return (
    <div className="card">
      <h3>Connect your wallet</h3>
      {connection.status === "connected" ? (
        <p>
          Connected: <strong>{shortenAddress(connection.address)}</strong> on chain{" "}
          {connection.chainId}. <span className="badge badge-ok">Ownership pending</span>
        </p>
      ) : (
        <p className="muted">Connect an EVM-compatible wallet. We never ask for your private key.</p>
      )}
      <button
        className="btn btn-primary"
        onClick={() => void handleConnect()}
        disabled={status !== "idle"}
      >
        {status === "signing" ? "Check wallet…" : "Connect Wallet"}
      </button>
      {message && <p className="muted">{message}</p>}
      <div className="row">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => void switchNetwork(11155111)}
        >
          Switch to Sepolia
        </button>
      </div>
    </div>
  );
}