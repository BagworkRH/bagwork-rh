/**
 * Staff back-office types (Spec 01 §Admin UI), mirroring the serializers in
 * `backend/apps/audit/admin_api.py`.
 *
 * Kept in their own module rather than appended to the seller-facing types:
 * nothing here is served to a non-staff caller, and the shape of the payloads
 * is owned by the staff API.
 */

/** Every list endpoint returns this envelope (see `_page` in admin_api.py). */
export interface OpsPage<T> {
  count: number;
  limit: number;
  offset: number;
  results: T[];
  /** Present on the risk queue only. */
  summary?: OpsRiskSummary;
}

export interface OpsRiskSummary {
  open: number;
  high: number;
  medium: number;
  low: number;
  threshold: number;
}

export interface OpsOverview {
  generated_at: string;
  sellers: { total: number; active: number; suspended: number; new_last_24h: number };
  campaigns: {
    total: number;
    active: number;
    paused: number;
    ended: number;
    budget: string;
    remaining_budget: string;
  };
  posts: { total: number; verified: number; awaiting_metrics: number; flagged: number };
  rewards: {
    pending_review: number;
    approved: number;
    available: number;
    claimed: number;
    reversed: number;
    total_amount: string;
  };
  claims: { open: number; confirmed: number; failed: number; expired: number };
  risk: OpsRiskSummary;
  audit_events_last_24h: number;
}

export type OpsSellerStatus = "ACTIVE" | "SUSPENDED" | "PENDING";

export interface OpsSeller {
  id: number;
  seller_code: string;
  display_name: string;
  email: string;
  username: string;
  status: OpsSellerStatus;
  reputation_score: number;
  wallets: number;
  verified_wallets: number;
  social_accounts: number;
  posts: number;
  created_at: string;
}

export interface OpsCampaign {
  id: number;
  name: string;
  slug: string;
  project_name: string;
  status: "DRAFT" | "ACTIVE" | "PAUSED" | "ENDED" | "CANCELLED";
  reward_model: string;
  reward_rate: string;
  token_symbol: string;
  chain_id: number;
  budget: string;
  remaining_budget: string;
  participants: number;
  rewards: number;
  start_at: string;
  end_at: string;
  created_at: string;
}

export interface OpsPost {
  id: number;
  external_post_id: string;
  post_url: string;
  seller_code: string;
  campaign: string | null;
  verification_status: string;
  rejection_reason: string | null;
  impressions: number;
  likes: number;
  reposts: number;
  replies: number;
  total_engagement: number;
  published_at: string;
  last_metrics_sync: string | null;
  has_reward: boolean;
}

export interface OpsReward {
  id: number;
  seller_code: string;
  campaign: string;
  post: number;
  amount: string;
  gross_amount: string;
  deduction_amount: string;
  token_symbol: string;
  chain_id: number;
  status: string;
  explanation: string;
  reversal_reason: string | null;
  created_at: string;
  approved_at: string | null;
}

export interface OpsClaim {
  id: number;
  seller_code: string;
  wallet: string;
  reward: number;
  amount: string;
  amount_smallest_unit: string;
  token_symbol: string;
  chain_id: number;
  status: string;
  transaction_hash: string | null;
  failure_reason: string | null;
  created_at: string;
  expired_at: string | null;
  confirmed_at: string | null;
}

export interface OpsRiskFlag {
  id: number;
  subject_type: string;
  subject_id: string;
  seller_code: string | null;
  score: number;
  severity: string;
  signals: Record<string, unknown> | unknown[];
  status: string;
  note: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface OpsAuditEntry {
  id: number;
  action: string;
  actor: string | null;
  object_type: string;
  object_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface OpsSettings {
  claiming_paused: boolean;
  chain: {
    chain_id: number;
    rpc_configured: boolean;
    contract_address: string;
    reward_token_address: string;
    signer_configured: boolean;
  };
  risk: { review_threshold: number; signal_weights: Record<string, number> };
  tokens: {
    id: number;
    symbol: string;
    chain_id: number;
    address: string;
    decimals: number;
    enabled: boolean;
  }[];
}
