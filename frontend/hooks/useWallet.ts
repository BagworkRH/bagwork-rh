import { useCallback, useState } from "react";

import { SUPPORTED_NETWORKS } from "@/lib/constants";

/**
 * Minimal EIP-1193 provider hook (wallet connect/switch, signing requests).
 * Never asks for seed phrases, private keys, or wallet passwords (Spec 01/04).
 */

interface Eip1193Provider {
  request: <T = unknown>(args: { method: string; params?: unknown[] }) => Promise<T>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  isMetaMask?: boolean;
}

interface ExtendedWindow extends Window {
  ethereum?: Eip1193Provider;
}

export type WalletConnection =
  | { status: "disconnected" }
  | { status: "connected"; address: string; chainId: number };

/** EIP-1193 codes we react to instead of just printing. */
const USER_REJECTED = 4001;
const CHAIN_NOT_ADDED = 4902;

/**
 * One in-flight `connect()` promise, shared by every caller.
 *
 * MetaMask answers a second `wallet_requestPermissions` while one is already
 * pending with "Request of type 'wallet_requestPermissions' already pending for
 * origin …". A double click, a React remount, or two components connecting at
 * once all look like that to the user, and a `disabled` attribute on one button
 * cannot cover any of them. De-duplicating here is the actual fix.
 */
let inFlightConnect: Promise<WalletConnection | null> | null = null;

function provider(): Eip1193Provider | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as ExtendedWindow).ethereum;
}

/** Whether an injected wallet exists (desktop extension, or a wallet browser). */
export function hasInjectedProvider(): boolean {
  return Boolean(provider());
}

/** True on a phone or tablet, where a browser extension cannot exist at all. */
export function isMobileBrowser(): boolean {
  if (typeof navigator === "undefined") return false;
  return /android|iphone|ipad|ipod|opera mini|iemobile|mobile/i.test(navigator.userAgent);
}

/** Turn provider errors into something a creator can act on. */
function friendlyError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (/already pending/i.test(raw)) {
    return "Your wallet already has a connection request open. Open the wallet, approve or reject it, then try again.";
  }
  if (/user rejected|user denied|cancelled/i.test(raw)) {
    return "You cancelled the request in your wallet.";
  }
  return raw || "Wallet connection failed.";
}

export function useWallet() {
  const [connection, setConnection] = useState<WalletConnection>({
    status: "disconnected",
  });
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async (): Promise<WalletConnection | null> => {
    const injected = provider();
    if (!injected) {
      setError(
        isMobileBrowser()
          ? "No wallet found in this browser. On a phone, open this page inside your wallet app."
          : "No wallet provider detected. Install a wallet such as MetaMask and refresh."
      );
      return null;
    }
    if (inFlightConnect) return inFlightConnect;

    inFlightConnect = (async () => {
      try {
        // Ask silently first. If this origin is already authorised there is no
        // prompt at all — which is what makes the "already pending" error
        // mostly disappear rather than merely being explained.
        let accounts = await injected.request<string[]>({ method: "eth_accounts" });
        if (!accounts || accounts.length === 0) {
          accounts = await injected.request<string[]>({ method: "eth_requestAccounts" });
        }
        const address = accounts?.[0];
        if (!address) {
          setError("Your wallet did not share an account.");
          setConnection({ status: "disconnected" });
          return null;
        }
        const chainIdHex = await injected.request<string>({ method: "eth_chainId" });
        const next: WalletConnection = {
          status: "connected",
          address,
          chainId: parseInt(chainIdHex, 16),
        };
        setConnection(next);
        setError(null);
        return next;
      } catch (err) {
        const code = (err as { code?: number })?.code;
        setError(
          code === USER_REJECTED
            ? "You cancelled the connection request."
            : friendlyError(err)
        );
        setConnection({ status: "disconnected" });
        return null;
      } finally {
        inFlightConnect = null;
      }
    })();

    return inFlightConnect;
  }, []);


  /**
   * Put the wallet on `chainId`, adding the chain first when the wallet has
   * never seen it.
   *
   * MetaMask does not know Robinhood Chain, so a bare `wallet_switchEthereumChain`
   * fails with 4902 ("Unrecognized chain ID"). Without the add step a creator can
   * connect but never sign a claim, which reads as the platform being broken.
   */
  const ensureNetwork = useCallback(async (chainId: number): Promise<boolean> => {
    const injected = provider();
    if (!injected) return false;
    const hex = `0x${chainId.toString(16)}`;
    try {
      await injected.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: hex }],
      });
    } catch (err) {
      if ((err as { code?: number })?.code !== CHAIN_NOT_ADDED) {
        setError(friendlyError(err));
        return false;
      }
      const network = SUPPORTED_NETWORKS.find((n) => n.chainId === chainId);
      if (!network) {
        setError(`Chain ${chainId} is not configured for this app.`);
        return false;
      }
      try {
        await injected.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: hex,
              chainName: network.name,
              nativeCurrency: { name: network.token, symbol: network.token, decimals: 18 },
              rpcUrls: [network.rpcUrl],
              blockExplorerUrls: [network.explorerUrl],
            },
          ],
        });
      } catch (addErr) {
        setError(friendlyError(addErr));
        return false;
      }
    }
    setConnection((c) => (c.status === "connected" ? { ...c, chainId } : c));
    setError(null);
    return true;
  }, []);

  /** Ask the user's wallet to sign a nonce message (ownership verification). */
  const signMessage = useCallback(
    async (message: string): Promise<string | null> => {
      const injected = provider();
      if (connection.status !== "connected" || !injected) return null;
      try {
        const signature = await injected.request<string>({
          method: "personal_sign",
          params: [message, connection.address],
        });
        return signature;
      } catch (err) {
        setError(friendlyError(err));
        return null;
      }
    },
    [connection]
  );

  /**
   * Ask the wallet to send a transaction (the claim calldata is built by the
   * backend, so nothing is encoded client-side).
   */
  const sendTransaction = useCallback(
    async (transaction: { to: string; data: string; value?: string }): Promise<string | null> => {
      const injected = provider();
      if (connection.status !== "connected" || !injected) {
        setError("Connect a wallet before sending a transaction.");
        return null;
      }
      try {
        const hash = await injected.request<string>({
          method: "eth_sendTransaction",
          params: [
            {
              from: connection.address,
              to: transaction.to,
              value: transaction.value ?? "0x0",
              data: transaction.data,
            },
          ],
        });
        setError(null);
        return hash;
      } catch (err) {
        setError(friendlyError(err));
        return null;
      }
    },
    [connection]
  );

  return { connection, error, connect, ensureNetwork, signMessage, sendTransaction };
}