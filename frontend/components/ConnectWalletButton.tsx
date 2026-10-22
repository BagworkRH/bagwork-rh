"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { hasInjectedProvider, isMobileBrowser, useWallet } from "@/hooks/useWallet";
import { registerWallet, verifyWallet } from "@/services/wallet";
import { LAUNCH_CHAIN, shortenAddress, walletDeepLinks } from "@/lib/constants";

/**
 * Wallet connection + ownership verification (Spec 04).
 *
 * Ownership is proven by a signature over the server-issued nonce message: the
 * backend registers the wallet, returns the exact message to sign, and only
 * marks the wallet verified when the recovered signer matches the address.
 *
 * Two audiences, one flow. A desktop browser has an injected provider from an
 * extension; a phone browser has none, so it is offered deep links into wallet
 * apps whose built-in browser *does* inject one. Either way the same connect,
 * sign and verify steps run afterwards.
 */
export default function ConnectWalletButton({ onVerified }: { onVerified?: () => void }) {
  const { connection, error: walletError, connect, ensureNetwork, signMessage } = useWallet();
  const { user } = useAuth();
  const [status, setStatus] = useState<"idle" | "working">("idle");
  const [verified, setVerified] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [providerReady, setProviderReady] = useState(true);

  // Read after mount only: `window` does not exist during the server render, so
  // putting this in the initial state would cause a hydration mismatch.
  useEffect(() => {
    setProviderReady(hasInjectedProvider());
  }, []);

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

      // The reward contract lives on one chain, so a claim signed on any other
      // is worthless. Switching here is what stops a creator reaching "claim"
      // and only then discovering the network is wrong.
      if (conn.chainId !== LAUNCH_CHAIN.chainId) {
        const switched = await ensureNetwork(LAUNCH_CHAIN.chainId);
        if (!switched) {
          setMessage(`Switch your wallet to ${LAUNCH_CHAIN.name} to continue.`);
          return;
        }
      }

      // 1. Register the address and receive the nonce message to sign.
      const challenge = await registerWallet(conn.address, LAUNCH_CHAIN.chainId);

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

  const wrongNetwork =
    connection.status === "connected" && connection.chainId !== LAUNCH_CHAIN.chainId;

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

      {!providerReady && <NoProviderHint mobile={isMobileBrowser()} />}

      {wrongNetwork && (
        <p className="muted">
          This platform rewards on {LAUNCH_CHAIN.name} (chain {LAUNCH_CHAIN.chainId}). Your
          wallet does not ship with it, so it has to be added once before claiming.
        </p>
      )}

      <div className="row">
        {providerReady && (
          <button
            className="btn btn-primary"
            onClick={() => void handleConnect()}
            disabled={status === "working"}
          >
            {status === "working" ? "Waiting for wallet…" : "Connect & verify wallet"}
          </button>
        )}
        {providerReady && wrongNetwork && (
          <button
            className="btn btn-outline btn-sm"
            onClick={() => void ensureNetwork(LAUNCH_CHAIN.chainId)}
          >
            Add / switch to {LAUNCH_CHAIN.name}
          </button>
        )}
      </div>

      {message && <p className="muted">{message}</p>}
      {walletError && <p className="muted">{walletError}</p>}
    </div>
  );
}

/**
 * Shown when there is no injected provider — which on a phone is normal rather
 * than an error. The deep links open this exact page inside the wallet app,
 * where a provider does exist, so the same connect flow then works.
 */
function NoProviderHint({ mobile }: { mobile: boolean }) {
  const [href, setHref] = useState("");

  useEffect(() => {
    setHref(window.location.href);
  }, []);

  if (!mobile) {
    return (
      <p className="muted">
        No wallet detected in this browser. Install an extension such as{" "}
        <a href="https://metamask.io/download/" target="_blank" rel="noreferrer">
          MetaMask
        </a>
        , then reload this page.
      </p>
    );
  }

  return (
    <>
      <p className="muted">
        A phone browser cannot run a wallet extension, so open this page inside your wallet app
        and connect from there:
      </p>
      <div className="row">
        {href &&
          walletDeepLinks(href).map((link) => (
            <a
              key={link.name}
              className="btn btn-outline btn-sm"
              href={link.href}
              target="_blank"
              rel="noreferrer"
            >
              Open in {link.name}
            </a>
          ))}
      </div>
    </>
  );
}