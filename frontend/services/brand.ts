import { ApiError, apiRequest } from "@/lib/api";
import type {
  BrandCampaignList,
  BrandFunding,
  BrandFundingList,
  BrandProfile,
  BrandQuote,
} from "@/types";

/**
 * Brand API client.
 *
 * All calls are authenticated and scoped to the signed-in user's own brand;
 * the backend enforces that, so nothing here needs to filter by brand id.
 *
 * Note the two-step funding flow: `recordFunding` only *records* a deposit and
 * returns PENDING, which does not count toward the balance until
 * `confirmFunding` runs. The UI must not present a recorded deposit as funded
 * money, or a brand will believe they have budget they do not.
 */

export async function getBrandProfile(): Promise<BrandProfile | null> {
  try {
    return await apiRequest<BrandProfile>("/api/v1/brand/profile/", { auth: true });
  } catch (err) {
    // 404 is the documented "no brand yet" answer, not a failure: the caller
    // renders the create form. Any other error is a real problem.
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function createBrandProfile(payload: {
  company_name: string;
  contact_email?: string;
  funding_wallet?: string;
}): Promise<BrandProfile> {
  return apiRequest<BrandProfile>("/api/v1/brand/profile/", {
    method: "POST",
    body: payload,
    auth: true,
  });
}

export async function listFunding(): Promise<BrandFundingList> {
  return apiRequest<BrandFundingList>("/api/v1/brand/funding/", { auth: true });
}

export async function recordFunding(payload: {
  amount: string;
  chain_id: number;
  tx_hash: string;
  token_symbol?: string;
}): Promise<BrandFunding> {
  return apiRequest<BrandFunding>("/api/v1/brand/funding/", {
    method: "POST",
    body: payload,
    auth: true,
  });
}

export async function confirmFunding(id: number): Promise<BrandFunding> {
  return apiRequest<BrandFunding>(`/api/v1/brand/funding/${id}/confirm/`, {
    method: "POST",
    body: {},
    auth: true,
  });
}

export async function getQuote(payoutTotal: string): Promise<BrandQuote> {
  return apiRequest<BrandQuote>("/api/v1/brand/quote/", {
    method: "POST",
    body: { payout_total: payoutTotal },
    auth: true,
  });
}

export async function listBrandCampaigns(): Promise<BrandCampaignList> {
  return apiRequest<BrandCampaignList>("/api/v1/brand/campaigns/", { auth: true });
}
