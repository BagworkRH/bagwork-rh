import { useCallback, useState } from "react";

/**
 * Minimal EIP-1193 provider hook (wallet connect/switch, signing requests).
 * Never asks for seed phrases, private keys, or wallet passwords (Spec 01/04).
 */

interface ExtendedWindow extends Window {
  ethereum?: {
    request: <T = unknown>(args: { method: string; params?: unknown[] }) => Promise<T>;
    on?: (event: string, handler: (...args: unknown[]) => void) => void;
  };
}

export type WalletConnection =
  | { status: "disconnected" }
  | { status: "connected"; address: string; chainId: number };

export function useWallet() {
  const [connection, setConnection] = useState<WalletConnection>({
    status: "disconnected",
  });
  const [error, setError] = useState<string | null>(null);

  const ethereum = (typeof window !== "undefined" ? window : null) as
    | ExtendedWindow
    | null;

  const connect = useCallback(async (): Promise<WalletConnection | null> => {
    if (!ethereum?.ethereum) {
      setError(
        "No wallet provider detected. Install a wallet such as MetaMask and refresh."
      );
      return null;
    }
    try {
      const accounts = await ethereum.ethereum.request<string[]>({
        method: "eth_requestAccounts",
      });
      const address = accounts[0];
      const chainIdHex = await ethereum.ethereum.request<string>({
        method: "eth_chainId",
      });
      const chainId = parseInt(chainIdHex, 16);
      const next: WalletConnection = { status: "connected", address, chainId };
      setConnection(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Wallet connection failed.");
      setConnection({ status: "disconnected" });
      return null;
    }
  }, [ethereum]);

  /** Ask the user's wallet to sign a nonce message (ownership verification). */
  const signMessage = useCallback(
    async (message: string): Promise<string | null> => {
      if (connection.status !== "connected" || !ethereum?.ethereum) return null;
      try {
        const signature = await ethereum.ethereum.request<string>({
          method: "personal_sign",
          params: [message, connection.address],
        });
        return signature;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Message signing failed.");
        return null;
      }
    },
    [connection, ethereum]
  );

  /**
   * Ask the wallet to send a transaction (the claim calldata is built by the
   * backend, so nothing is encoded client-side).
   */
  const sendTransaction = useCallback(
    async (transaction: { to: string; data: string; value?: string }): Promise<string | null> => {
      if (connection.status !== "connected" || !ethereum?.ethereum) {
        setError("Connect a wallet before sending a transaction.");
        return null;
      }
      try {
        const hash = await ethereum.ethereum.request<string>({
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
        setError(
          err instanceof Error ? err.message : "The wallet rejected the transaction."
        );
        return null;
      }
    },
    [connection, ethereum]
  );

  const switchNetwork = useCallback(
    async (chainId: number): Promise<boolean> => {
      if (connection.status !== "connected" || !ethereum?.ethereum) return false;
      try {
        await ethereum.ethereum.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: `0x${chainId.toString(16)}` }],
        });
        setConnection((c) =>
          c.status === "connected" ? { ...c, chainId } : c
        );
        setError(null);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Network switch failed. Please switch networks in your wallet."
        );
        return false;
      }
    },
    [connection, ethereum]
  );

  return { connection, error, connect, signMessage, sendTransaction, switchNetwork };
}