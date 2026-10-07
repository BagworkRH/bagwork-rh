/** Campaign services (Spec 02). */
import { apiRequest } from "@/lib/api";
import type { Campaign, CampaignCreateInput } from "@/types";

export async function listCampaigns(): Promise<Campaign[]> {
  return apiRequest<Campaign[]>("/api/v1/campaigns/");
}

export async function getCampaign(slug: string): Promise<Campaign> {
  return apiRequest<Campaign>(`/api/v1/campaigns/${slug}/`);
}

/**
 * Create a campaign (staff, or a brand creating its own).
 *
 * The backend attributes a brand-created campaign to that brand automatically
 * and leaves it in DRAFT, so nothing here sends a brand id or a status. A draft
 * does not accept creators until it is launched, and a brand's campaign cannot
 * be launched until its confirmed stablecoin covers the budget plus the fee —
 * that gate lives on the backend and is surfaced as a normal API error.
 */
export async function createCampaign(input: CampaignCreateInput): Promise<Campaign> {
  return apiRequest<Campaign>("/api/v1/campaigns/", {
    method: "POST",
    body: input,
    auth: true,
  });
}

/**
 * Publish a draft so creators can join it.
 *
 * Staff may launch any campaign; a brand may launch only its own and only once
 * it is funded. An unfunded launch comes back as a 400 with the shortfall,
 * which is deliberately shown to the brand rather than swallowed.
 */
export async function launchCampaign(slug: string): Promise<Campaign> {
  return apiRequest<Campaign>(`/api/v1/campaigns/${slug}/launch/`, {
    method: "POST",
    auth: true,
  });
}

export async function joinCampaign(campaignId: number): Promise<unknown> {
  return apiRequest(`/api/v1/campaigns/${campaignId}/join/`, {
    method: "POST",
    auth: true,
  });
}