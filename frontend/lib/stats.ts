/**
 * Platform statistics shown on the landing page.
 *
 * Sourced from the public `GET /api/v1/campaigns/stats/` endpoint so the site
 * can never display a figure the database does not support. When the API is
 * unreachable the caller renders an honest empty state rather than a
 * placeholder.
 */
export type PlatformStats = {
  rewards_paid_total: string;
  rewards_outstanding_total: string;
  claims_completed: number;
  active_sellers: number;
  campaigns_live: number;
  campaigns_total: number;
  posts_tracked: number;
  posts_verified: number;
  verification_rate: number | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Fetch the headline figures. Returns null if the backend is unavailable. */
export async function getPlatformStats(): Promise<PlatformStats | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/campaigns/stats/`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as PlatformStats;
  } catch {
    return null;
  }
}
