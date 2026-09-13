/** Wallet and reward services (Spec 02 & 04). */
import { apiRequest } from "@/lib/api";
import type { Claim, Reward } from "@/types";

export async function listRewards(): Promise<Reward[]> {
  return apiRequest<Reward[]>("/api/v1/rewards/", { auth: true });
}

export async function listClaims(): Promise<Omit<Claim, "chain_id">[]> {
  return apiRequest<Omit<Claim, "chain_id">[]>("/api/v1/me/claims/", {
    auth: true,
  });
}

export async function createClaim(rewardId: number, walletId: number): Promise<Claim> {
  return apiRequest<Claim>("/api/v1/claims/", {
    method: "POST",
    body: { reward_id: rewardId, wallet_id: walletId },
    auth: true,
  });
}

export interface XConnectResult {
  authorize_url: string;
  mock: boolean;
}

/** Start the X (Twitter) OAuth authorization flow. */
export async function startXConnect(): Promise<XConnectResult> {
  return apiRequest<XConnectResult>("/api/v1/x/connect/", {
    method: "POST",
    auth: true,
  });
}

export async function disconnectX(): Promise<void> {
  return apiRequest<void>("/api/v1/x/disconnect/", { method: "POST", auth: true });
}