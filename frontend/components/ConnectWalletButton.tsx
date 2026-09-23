"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@/hooks/useWallet";
import { registerWallet, verifyWallet } from "@/services/wallet";
import { shortenAddress } from "@/lib/constants";

/**
 * Wallet connection + ownership verification (Spec 04).
 *
 * Ownership is proven by a signature over the server-issued nonce message: the
 * backend registers the wallet, returns the exact message to sign, and only
 * marks the wallet verified when the recovered signer matches the address.
 */
export default function ConnectWalletButton({ onVerified }: { onVerified?: () => void }) {
  const { connection, connect, signMessage, switchNetwork } = useWallet();
  const { user } = useAuth();
  const [status, setStatus] = useState<"idle" | "working">("idle");
  const [verified, setVerified] = useState(false);
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
    setStatus("working");
    setMessage("");
    setVerified(false);
    try {
      const conn = await connect();
      if (!conn || conn.status !== "connected") {
        setMessage("Wallet connection was not completed.");
        return;
      }

      // 1. Register the address and receive the nonce message to sign.
      const challenge = await registerWallet(conn.address, conn.chainId);

      // 2. Ask the wallet to sign exactly the message the server will verify.
      const signature = await signMessage(challenge.message);
      if (!signature) {
        setMessage("Signature was not provided; ownership is unverified.");
        return;
      }

      // 3. The server verifies the signature and marks ownership verified.
      const wallet = await verifyWallet(challenge.id, signature);
      setVerified(wallet.verified);
      setMessage(
        wallet.verified
          ? "Wallet verified: ownership proven by signature."
          : "Wallet could not be verified."
      );
      if (wallet.verified) onVerified?.();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Wallet verification failed.");
    } finally {
      setStatus("idle");
    }
  }

  const wrongNetwork = connection.status === "connected" && connection.chainId !== 11155111;

  return (
    <div className="card">
      <h3>Connect your wallet</h3>
      {connection.status === "connected" ? (
        <p>
          Connected: <strong>{shortenAddress(connection.address)}</strong> on chain{" "}
          {connection.chainId}.{" "}
          {verified ? (
            <span className="badge badge-ok">verified</span>
          ) : (
            <span className="badge">ownership pending</span>
          )}
        </p>
      ) : (
        <p className="muted">
          Connect an EVM-compatible wallet. We never ask for your private key or seed phrase.
        </p>
      )}

      {wrongNetwork && (
        <p className="muted">
          This platform rewards on Sepolia (chain 11155111). Switch networks in your wallet to
          continue.
        </p>
      )}

      <div className="row">
        <button
          className="btn btn-primary"
          onClick={() => void handleConnect()}
          disabled={status === "working"}
        >
          {status === "working" ? "Waiting for wallet…" : "Connect & verify wallet"}
        </button>
        {wrongNetwork && (
          <button
            className="btn btn-outline btn-sm"
            onClick={() => void switchNetwork(11155111)}
          >
            Switch to Sepolia
          </button>
        )}
      </div>

      {message && <p className="muted">{message}</p>}
    </div>
  );
}