/**
 * Staff back-office services (Spec 05 Phase 7).
 *
 * Every call here goes to `/api/v1/admin/*`, which is restricted to staff by
 * `IsAdminUser`. The console is deliberately a thin client: the rules that
 * matter — who may be suspended, which rewards may be released, what a
 * rejection status may be — live in the backend services and surface here as
 * ordinary API errors rather than being re-implemented.
 */
import { apiRequest } from "@/lib/api";
import type {
  OpsAuditEntry,
  OpsCampaign,
  OpsClaim,
  OpsOverview,
  OpsPage,
  OpsPost,
  OpsReward,
  OpsRiskFlag,
  OpsSeller,
  OpsSettings,
} from "@/types/ops";

/** Query params for the list endpoints; empty values are dropped. */
export type OpsFilters = Record<string, string | number | undefined>;

function query(filters: OpsFilters = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "" || value === null) continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function opsList<T>(path: string, filters: OpsFilters = {}): Promise<OpsPage<T>> {
  return apiRequest<OpsPage<T>>(`${path}${query(filters)}`, { auth: true });
}

export async function getOverview(): Promise<OpsOverview> {
  return apiRequest<OpsOverview>("/api/v1/admin/overview/", { auth: true });
}

export async function getSettings(): Promise<OpsSettings> {
  return apiRequest<OpsSettings>("/api/v1/admin/settings/", { auth: true });
}

// ---------------------------------------------------------------- sellers
export async function listSellers(filters: OpsFilters = {}): Promise<OpsPage<OpsSeller>> {
  return opsList<OpsSeller>("/api/v1/admin/sellers/", filters);
}

/** Activate or suspend a seller. Financial history is untouched either way. */
export async function setSellerStatus(
  id: number,
  status: string,
  reason: string
): Promise<OpsSeller> {
  return apiRequest<OpsSeller>(`/api/v1/admin/sellers/${id}/status/`, {
    method: "POST",
    body: { status, reason },
    auth: true,
  });
}

// ---------------------------------------------------------------- campaigns
export async function listCampaigns(filters: OpsFilters = {}): Promise<OpsPage<OpsCampaign>> {
  return opsList<OpsCampaign>("/api/v1/admin/campaigns/", filters);
}

/**
 * Pause, resume, end or cancel a campaign.
 *
 * Pausing or cancelling also disables claiming for its rewards — enforced in
 * `create_claim`, not here, so the console cannot get it wrong.
 */
export async function setCampaignStatus(
  id: number,
  status: string,
  reason: string
): Promise<OpsCampaign> {
  return apiRequest<OpsCampaign>(`/api/v1/admin/campaigns/${id}/status/`, {
    method: "POST",
    body: { status, reason },
    auth: true,
  });
}

// ---------------------------------------------------------------- posts
export async function listPosts(filters: OpsFilters = {}): Promise<OpsPage<OpsPost>> {
  return opsList<OpsPost>("/api/v1/admin/posts/", filters);
}

/**
 * Approve or reject a tracked post.
 *
 * Approving marks it VERIFIED; rewards are still calculated separately by the
 * reward engine, so this never pays out on its own. Rejecting needs one of the
 * Spec 03 failure states as `rejectionStatus`.
 */
export async function reviewPost(
  id: number,
  decision: "approve" | "reject",
  reason: string,
  rejectionStatus = ""
): Promise<OpsPost> {
  return apiRequest<OpsPost>(`/api/v1/admin/posts/${id}/review/`, {
    method: "POST",
    body: { decision, reason, rejection_status: rejectionStatus },
    auth: true,
  });
}

/** The failure states a reviewer may apply when rejecting a post (Spec 03). */
export const REJECTION_STATUSES = [
  "NOT_ELIGIBLE",
  "DUPLICATE",
  "OUTSIDE_CAMPAIGN_WINDOW",
  "REQUIREMENT_MISSING",
  "PROVIDER_ERROR",
  "SUSPICIOUS_ACTIVITY",
] as const;

// ---------------------------------------------------------------- rewards
export async function listRewards(filters: OpsFilters = {}): Promise<OpsPage<OpsReward>> {
  return opsList<OpsReward>("/api/v1/admin/rewards/", filters);
}

/**
 * approve   -> PENDING becomes APPROVED
 * available -> APPROVED becomes AVAILABLE (claimable)
 * reverse   -> reversed, releasing the campaign slot; a reason is required
 */
export async function reviewReward(
  id: number,
  decision: "approve" | "available" | "reverse",
  reason = ""
): Promise<OpsReward> {
  return apiRequest<OpsReward>(`/api/v1/admin/rewards/${id}/review/`, {
    method: "POST",
    body: { decision, reason },
    auth: true,
  });
}

// ---------------------------------------------------------------- claims
export async function listClaims(filters: OpsFilters = {}): Promise<OpsPage<OpsClaim>> {
  return opsList<OpsClaim>("/api/v1/admin/claims/", filters);
}

/** Record a claim failure with a reason. The reward stays claimable. */
export async function failClaim(id: number, reason: string): Promise<OpsClaim> {
  return apiRequest<OpsClaim>(`/api/v1/admin/claims/${id}/fail/`, {
    method: "POST",
    body: { reason },
    auth: true,
  });
}

// ---------------------------------------------------------------- risk
export async function listRiskFlags(filters: OpsFilters = {}): Promise<OpsPage<OpsRiskFlag>> {
  return opsList<OpsRiskFlag>("/api/v1/admin/risk/", filters);
}

/** dismiss | confirm | review — a human decision, always audited. */
export async function resolveRiskFlag(
  id: number,
  decision: "dismiss" | "confirm" | "review",
  note = ""
): Promise<OpsRiskFlag> {
  return apiRequest<OpsRiskFlag>(`/api/v1/admin/risk/${id}/resolve/`, {
    method: "POST",
    body: { decision, note },
    auth: true,
  });
}

/** Re-run the risk scan on demand. It queues evidence; it never accuses. */
export async function runRiskScan(
  hours = 24,
  claimThreshold = 20
): Promise<{ posts: unknown; claims: unknown; summary: unknown }> {
  return apiRequest("/api/v1/admin/risk/scan/", {
    method: "POST",
    body: { hours, claim_threshold: claimThreshold },
    auth: true,
  });
}

// ---------------------------------------------------------------- audit
export async function listAuditLogs(filters: OpsFilters = {}): Promise<OpsPage<OpsAuditEntry>> {
  return opsList<OpsAuditEntry>("/api/v1/admin/audit-logs/", filters);
}
