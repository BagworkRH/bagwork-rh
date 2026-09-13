/** Authentication and seller services (Spec 02). */
import { apiRequest } from "@/lib/api";
import type { SellerProfile, SellerDashboard, User, Wallet } from "@/types";

export async function getSellerProfile(): Promise<SellerProfile> {
  return apiRequest<SellerProfile>("/api/v1/me/seller/", { auth: true });
}

export async function updateSellerProfile(
  data: Partial<Pick<SellerProfile, "display_name">>
): Promise<SellerProfile> {
  return apiRequest<SellerProfile>("/api/v1/me/seller/", {
    method: "PATCH",
    body: data,
    auth: true,
  });
}

export async function getDashboard(): Promise<SellerDashboard> {
  return apiRequest<SellerDashboard>("/api/v1/me/dashboard/", { auth: true });
}

export async function getUser(): Promise<User> {
  return apiRequest<User>("/api/v1/me/", { auth: true });
}

export async function getMyWallets(): Promise<Wallet[]> {
  return apiRequest<Wallet[]>("/api/v1/me/wallets/", { auth: true });
}