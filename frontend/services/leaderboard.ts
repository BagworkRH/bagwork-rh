/**
 * The public leaderboard.
 *
 * Deliberately unauthenticated: the board exists so a stranger can see that the
 * platform pays. It is fetched client-side rather than server-side so the rate
 * limit is per visitor, not per frontend container.
 */
import { apiRequest } from "@/lib/api";
import type { CreatorCard, Leaderboard } from "@/types";

export function getLeaderboard(
  params: { campaign?: string; limit?: number; offset?: number } = {}
): Promise<Leaderboard> {
  const query = new URLSearchParams();
  if (params.campaign) query.set("campaign", params.campaign);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Leaderboard>(`/api/v1/leaderboard/${suffix}`);
}

/**
 * One creator's public card, for sharing. Unauthenticated like the board.
 */
export function getCreatorCard(sellerCode: string): Promise<CreatorCard> {
  return apiRequest<CreatorCard>(`/api/v1/card/${sellerCode}/`);
}
