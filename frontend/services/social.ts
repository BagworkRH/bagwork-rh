/**
 * Social platform + creator post API.
 *
 * Every route is platform-agnostic: `platform` is part of the path because the
 * backend can't complete a callback against the wrong provider, and neither
 * should the client be able to.
 */
import { apiRequest } from "@/lib/api";
import type { SocialPlatform, SocialPost, SocialAccount } from "@/types";

/** What this build can connect. Returns `mock: true` in mock mode. */
export function getPlatforms(): Promise<{
  platforms: Array<{ id: SocialPlatform; name: string }>;
  mock: boolean;
}> {
  return apiRequest("/api/v1/x/platforms/");
}

/**
 * Begin OAuth. The response's `authorize_url` is opened in the browser; the
 * provider then redirects back to the callback endpoint.
 */
export function connectPlatform(
  platform: SocialPlatform
): Promise<{ platform: SocialPlatform; authorize_url: string; mock: boolean }> {
  return apiRequest(`/api/v1/x/${platform}/connect/`, {
    method: "POST",
    auth: true,
  });
}

export function disconnectPlatform(
  platform: SocialPlatform
): Promise<{ platform: SocialPlatform; detail: string }> {
  return apiRequest(`/api/v1/x/${platform}/disconnect/`, {
    method: "POST",
    auth: true,
  });
}

/**
 * The seller's already-linked accounts.
 *
 * Distinct from `getPlatforms()`, which lists what this build can connect.
 * Without this, a client has no way to know what is linked before offering a
 * disconnect -- the only way to find out would be to call disconnect and read
 * the 404.
 */
export function getConnections(): Promise<{
  connections: SocialAccount[];
  mock: boolean;
}> {
  return apiRequest("/api/v1/x/connections/", { auth: true });
}

/**
 * The signed-in creator's own posts, newest first.
 *
 * Scoped server-side to the requesting seller, so a creator can see their own
 * post status and -- when a post was rejected -- why. That reason is the whole
 * point of this endpoint: without it a creator cannot fix the thing that failed.
 */
export function getMyPosts(): Promise<SocialPost[]> {
  // Authenticated: `/me/posts/` is scoped to the signed-in seller.
  return apiRequest("/api/v1/me/posts/", { auth: true });
}
