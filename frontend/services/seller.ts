/**
 * The signed-in creator's own profile.
 *
 * Separate from `services/social.ts` because it is a different resource: this is
 * the account, not the accounts they publish from.
 */
import { apiRequest } from "@/lib/api";
import type { SellerProfile } from "@/types";

export function getSellerProfile(): Promise<SellerProfile> {
  return apiRequest<SellerProfile>("/api/v1/me/seller/", { auth: true });
}

/**
 * Update the fields a creator controls. Only the ones they actually own are
 * accepted: the server treats the rest as read-only, so a stray field cannot
 * change a status or a reputation score.
 */
export function updateSellerProfile(
  patch: Partial<Pick<SellerProfile, "display_name" | "show_earnings_publicly">>
): Promise<SellerProfile> {
  return apiRequest<SellerProfile>("/api/v1/me/seller/", {
    method: "PATCH",
    body: patch,
    auth: true,
  });
}
