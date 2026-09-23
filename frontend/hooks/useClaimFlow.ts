import { useCallback, useState } from "react";
import {
  createClaim,
  getClaimAuthorization,
  submitClaimTransaction,
} from "@/services/wallet";
import type { Claim, ClaimAuthorization, Reward, Wallet } from "@/types";

export type ClaimStep =
  | { phase: "idle" }
  | { phase: "creating" }
  | { phase: "authorizing" }
  | { phase: "awaiting-wallet" }
  | { phase: "recording"; hash: string }
  | { phase: "submitted"; claim: Claim; hash: string }
  | { phase: "error"; message: string };

/**
 * Claim flow (Spec 04): create the claim, fetch the server-signed EIP-712
 * authorization, have the wallet send the returned calldata, then record the
 * transaction hash. All chain/API logic lives here so the page stays presentational.
 */
export function useClaimFlow() {
  const [step, setStep] = useState<ClaimStep>({ phase: "idle" });

  const claimReward = useCallback(
    async (
      reward: Reward,
      wallet: Wallet,
      sendTransaction: (tx: { to: string; data: string; value?: string }) => Promise<string | null>
    ): Promise<Claim | null> => {
      try {
        setStep({ phase: "creating" });
        const created = await createClaim(reward.id, wallet.id);

        setStep({ phase: "authorizing" });
        const authorization: ClaimAuthorization =
          created.authorization ?? (await getClaimAuthorization(created.id));

        setStep({ phase: "awaiting-wallet" });
        const hash = await sendTransaction({
          to: authorization.transaction.to,
          data: authorization.transaction.data,
          value: authorization.transaction.value,
        });
        if (!hash) {
          setStep({ phase: "idle" });
          return null;
        }

        setStep({ phase: "recording", hash });
        const claim = await submitClaimTransaction(created.id, hash);
        setStep({ phase: "submitted", claim, hash });
        return claim;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "The claim could not be completed.";
        setStep({ phase: "error", message });
        return null;
      }
    },
    []
  );

  const reset = useCallback(() => setStep({ phase: "idle" }), []);

  return { step, claimReward, reset };
}