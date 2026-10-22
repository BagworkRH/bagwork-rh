"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { SUPPORTED_NETWORKS } from "@/lib/constants";

/**
 * Wallet connection state, shared by the whole app (Spec 01/04).
 *
 * A context rather than plain hook state, because wallet state is not local to a
 * page: the header shows the connected address, the wallet page signs claims,
 * and onboarding connects. While each `useWallet()` call kept its own
 * `useState`, connecting on one surface left every other one still offering
 * "Connect Wallet" — and clicking it re-ran the provider request just to
 * rediscover the account that was already connected.
 *
 * Never asks for seed phrases, private keys, or wallet passwords.
 */

interface Eip1193Provider {
  request: <T = unknown>(args: { method: string; params?: unknown[] }) => Promise<T>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void;
  isMetaMask?: boolean;
}

interface ExtendedWindow extends Window {
  ethereum?: Eip1193Provider;
}

export type WalletConnection =
  | { status: "disconnected" }
  | { status: "connected"; address: string; chainId: number };

export interface WalletApi {
  connection: WalletConnection;
  error: string | null;
  clearError: () => void;
  connect: () => Promise<WalletConnection | null>;
  ensureNetwork: (chainId: number) => Promise<boolean>;
  signMessage: (message: string) => Promise<string | null>;
  sendTransaction: (transaction: {
    to: string;
    data: string;
    value?: string;
  }) => Promise<string | null>;
  disconnect: () => void;
}

/** EIP-1193 codes we react to instead of just printing. */
const USER_REJECTED = 4001;
const CHAIN_NOT_ADDED = 4902;

/**
 * One in-flight `connect()` promise, shared by every caller.
 *
 * MetaMask answers a second `wallet_requestPermissions` while one is already
 * pending with "Request of type 'wallet_requestPermissions' already pending for
 * origin …". A double click, a remount, or two surfaces connecting at once all
 * look like that to the user, and a `disabled` attribute cannot cover any of
 * them. De-duplicating here is the actual fix.
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

const WalletContext = createContext<WalletApi | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<WalletConnection>({
    status: "disconnected",
  });
  const [error, setError] = useState<string | null>(null);

  const readChainId = useCallback(async (injected: Eip1193Provider): Promise<number> => {
    const hex = await injected.request<string>({ method: "eth_chainId" });
    return parseInt(hex, 16);
  }, []);

  /**
   * Restore an existing authorisation on load, and follow the wallet when the
   * user switches account or network inside it. Without the listeners the UI
   * keeps showing an address the wallet has already moved off.
   */
  useEffect(() => {
    const injected = provider();
    if (!injected) return;

    let cancelled = false;
    void (async () => {
      try {
        // `eth_accounts` never prompts: it reports what is already authorised.
        const accounts = await injected.request<string[]>({ method: "eth_accounts" });
        if (cancelled || !accounts?.length) return;
        const chainId = await readChainId(injected);
        setConnection({ status: "connected", address: accounts[0], chainId });
      } catch {
        // A provider that cannot answer this is simply not connected.
      }
    })();

    const onAccountsChanged = (...args: unknown[]) => {
      const accounts = (args[0] ?? []) as string[];
      if (!accounts.length) {
        setConnection({ status: "disconnected" });
        return;
      }
      setConnection((c) => (c.status === "connected" ? { ...c, address: accounts[0] } : c));
    };
    const onChainChanged = (...args: unknown[]) => {
      const chainId = parseInt(args[0] as string, 16);
      setConnection((c) => (c.status === "connected" ? { ...c, chainId } : c));
    };

    injected.on?.("accountsChanged", onAccountsChanged);
    injected.on?.("chainChanged", onChainChanged);
    return () => {
      cancelled = true;
      injected.removeListener?.("accountsChanged", onAccountsChanged);
      injected.removeListener?.("chainChanged", onChainChanged);
    };
  }, [readChainId]);

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
        const chainId = await readChainId(injected);
        const next: WalletConnection = { status: "connected", address, chainId };
        setConnection(next);
        setError(null);
        return next;
      } catch (err) {
        const code = (err as { code?: number })?.code;
        setError(
          code === USER_REJECTED ? "You cancelled the connection request." : friendlyError(err)
        );
        setConnection({ status: "disconnected" });
        return null;
      } finally {
        inFlightConnect = null;
      }
    })();

    return inFlightConnect;
  }, [readChainId]);

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

  /**
   * Forget the connection in this app only. It cannot revoke the wallet's
   * permission to this origin — that is the user's choice inside the wallet —
   * so a reload may restore it, which is honest rather than surprising.
   */
  const disconnect = useCallback(() => {
    setConnection({ status: "disconnected" });
    setError(null);
  }, []);

  /** Dismiss the last wallet error once the user has acknowledged it. */
  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<WalletApi>(
    () => ({
      connection,
      error,
      clearError,
      connect,
      ensureNetwork,
      signMessage,
      sendTransaction,
      disconnect,
    }),
    [
      connection,
      error,
      clearError,
      connect,
      ensureNetwork,
      signMessage,
      sendTransaction,
      disconnect,
    ]
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

/**
 * Read the shared wallet state. Every caller sees the same connection, so
 * connecting once is visible everywhere without a second provider request.
 */
export function useWallet(): WalletApi {
  const context = useContext(WalletContext);
  if (!context) {
    throw new Error("useWallet must be used inside <WalletProvider> (see app/layout.tsx).");
  }
  return context;
}

