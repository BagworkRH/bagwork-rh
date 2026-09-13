/** Campaign services (Spec 02). */
import { apiRequest } from "@/lib/api";
import type { Campaign } from "@/types";

export async function listCampaigns(): Promise<Campaign[]> {
  return apiRequest<Campaign[]>("/api/v1/campaigns/");
}

export async function getCampaign(slug: string): Promise<Campaign> {
  return apiRequest<Campaign>(`/api/v1/campaigns/${slug}/`);
}

export async function joinCampaign(campaignId: number): Promise<unknown> {
  return apiRequest(`/api/v1/campaigns/${campaignId}/join/`, {
    method: "POST",
    auth: true,
  });
}