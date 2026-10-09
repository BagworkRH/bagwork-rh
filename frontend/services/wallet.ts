/** Wallet, claim and authorization services (Spec 02 & 04).
 *
 * All blockchain business logic stays on the server: the backend signs the
 * EIP-712 claim authorization and returns fully ABI-encoded calldata, so this
 * module only moves data between the API and the wallet provider.
 */
import { apiRequest } from "@/lib/api";
import type {
  Claim,
  ClaimAuthorization,
  ClaimWithAuthorization,
  Reward,
  Wallet,
  WalletChallenge,
} from "@/types";

export async function listRewards(): Promise<Reward[]> {
  return apiRequest<Reward[]>("/api/v1/rewards/", { auth: true });
}

export async function listClaims(): Promise<Claim[]> {
  return apiRequest<Claim[]>("/api/v1/me/claims/", { auth: true });
}

export async function listWallets(): Promise<Wallet[]> {
  return apiRequest<Wallet[]>("/api/v1/me/wallets/", { auth: true });
}

/** Register a wallet and receive the nonce + exact message to sign. */
export async function registerWallet(
  address: string,
  chainId: number
): Promise<WalletChallenge> {
  return apiRequest<WalletChallenge>("/api/v1/me/wallets/", {
    method: "POST",
    body: { address, chain_id: chainId },
    auth: true,
  });
}

/** Submit the wallet's signature over the server-issued nonce message. */
export async function verifyWallet(walletId: number, signature: string): Promise<Wallet> {
  return apiRequest<Wallet>(`/api/v1/me/wallets/${walletId}/verify/`, {
    method: "POST",
    body: { signature },
    auth: true,
  });
}

/** Create a claim; the response carries the signed authorization when ready. */
export async function createClaim(
  rewardId: number,
  walletId: number
): Promise<ClaimWithAuthorization> {
  return apiRequest<ClaimWithAuthorization>("/api/v1/claims/", {
    method: "POST",
    body: { reward_id: rewardId, wallet_id: walletId },
    auth: true,
  });
}

/** Fetch (or refresh) the signed claim authorization and calldata. */
export async function getClaimAuthorization(claimId: number): Promise<ClaimAuthorization> {
  return apiRequest<ClaimAuthorization>(`/api/v1/claims/${claimId}/authorization/`, {
    auth: true,
  });
}

/** Record the transaction hash the wallet broadcast. */
export async function submitClaimTransaction(
  claimId: number,
  transactionHash: string
): Promise<Claim> {
  return apiRequest<Claim>(`/api/v1/claims/${claimId}/submit/`, {
    method: "POST",
    body: { transaction_hash: transactionHash },
    auth: true,
  });
}

export async function getClaim(claimId: number): Promise<Claim> {
  return apiRequest<Claim>(`/api/v1/claims/${claimId}/`, { auth: true });
}

// X connect/disconnect moved to `services/social.ts`, which is platform-agnostic
// (`connectPlatform` / `disconnectPlatform`). The X-only helpers that used to
// live here went dead once onboarding handled every platform.