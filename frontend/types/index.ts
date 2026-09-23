/** Shared API types (mirror Spec 02 endpoints). */

export interface User {
  id: number;
  email: string;
  username: string;
  is_staff: boolean;
  is_active: boolean;
  created_at: string;
}

export interface SellerProfile {
  id: number;
  user: User;
  seller_code: string;
  display_name: string;
  status: "PENDING" | "ACTIVE" | "SUSPENDED";
  reputation_score: number;
  created_at: string;
}

export interface Wallet {
  id: number;
  address: string;
  chain_id: number;
  network?: string;
  wallet_type: string;
  verified: boolean;
  connected_at: string;
}

export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "ENDED" | "CANCELLED";
export type RewardModel = "FIXED" | "IMPRESSION_BASED" | "ENGAGEMENT_BASED" | "HYBRID";

export interface Campaign {
  id: number;
  name: string;
  slug: string;
  description: string;
  project_name: string;
  token_symbol: string;
  chain_id: number;
  budget: string;
  remaining_budget: string;
  reward_model: RewardModel;
  reward_rate: string;
  maximum_reward_per_seller: string;
  maximum_rewards_per_seller: number;
  start_at: string;
  end_at: string;
  status: CampaignStatus;
  requirements_json: Record<string, unknown>;
  joined: boolean;
  created_at: string;
}

export type PostVerificationStatus =
  | "DISCOVERED"
  | "BASIC_VALIDATION"
  | "CAMPAIGN_MATCH"
  | "DUPLICATE_CHECK"
  | "METRICS_PENDING"
  | "VERIFIED"
  | "REWARD_CALCULATED"
  | "APPROVED"
  | "NOT_ELIGIBLE"
  | "DUPLICATE"
  | "OUTSIDE_CAMPAIGN_WINDOW"
  | "REQUIREMENT_MISSING"
  | "ACCOUNT_NOT_CONNECTED"
  | "PROVIDER_ERROR"
  | "SUSPICIOUS_ACTIVITY";

export interface SocialPost {
  id: number;
  external_post_id: string;
  post_url: string;
  campaign: string | null;
  seller_code: string;
  published_at: string | null;
  verification_status: PostVerificationStatus;
  rejection_reason: string;
  impressions: number;
  likes: number;
  reposts: number;
  replies: number;
  last_metrics_sync: string | null;
}

export type RewardStatus =
  | "PENDING"
  | "VERIFIED"
  | "APPROVED"
  | "AVAILABLE"
  | "CLAIMED"
  | "FAILED"
  | "REVERSED";

export interface Reward {
  id: number;
  seller_code: string;
  campaign: string | null;
  post: string | null;
  amount: string;
  gross: string;
  deductions: string;
  token_symbol: string;
  status: RewardStatus;
  calculation_version: string;
  explanation: string;
  created_at: string;
}

export type ClaimStatus =
  | "CREATED"
  | "SIGNING"
  | "SUBMITTED"
  | "PENDING"
  | "CONFIRMED"
  | "FAILED"
  | "REPLACED"
  | "EXPIRED";

export interface Claim {
  id: number;
  seller_code: string;
  wallet: string;
  wallet_id: number;
  reward: number | null;
  amount: string;
  amount_smallest_unit: number;
  token_symbol: string;
  chain_id: number;
  status: ClaimStatus;
  transaction_hash?: string;
  failure_reason?: string;
  expired_at?: string | null;
  created_at: string;
  submitted_at?: string | null;
  confirmed_at?: string | null;
}

/** A claim as returned by POST /api/v1/claims/ (claim + signed authorization). */
export interface ClaimWithAuthorization extends Claim {
  authorization: ClaimAuthorization | null;
  authorization_ready: boolean;
  authorization_unavailable?: string;
}

/**
 * Server-signed EIP-712 claim authorization (Spec 04).
 *
 * `transaction` is fully ABI-encoded by the backend, so the frontend only asks
 * the wallet provider to send it — no client-side ABI encoding is needed.
 */
export interface ClaimAuthorization {
  claim_id: number;
  status: ClaimStatus;
  signature: string;
  wallet: string;
  reward_id: number;
  token: string;
  token_symbol: string;
  token_decimals: number;
  amount_smallest_unit: number;
  amount: string;
  nonce: number;
  nonce_hex: string;
  deadline: number;
  chain_id: number;
  contract_address: string;
  signer_address: string;
  domain: { name: string; version: string; chainId: number };
  function: string;
  transaction: {
    to: string;
    from: string;
    value: string;
    data: string;
    chain_id: number;
  };
}

/** Wallet registration response: the nonce and the exact message to sign. */
export interface WalletChallenge {
  id: number;
  address: string;
  chain_id: number;
  wallet_type: string;
  verified: boolean;
  nonce: string;
  message: string;
  connected_at: string;
}

export interface SellerDashboard {
  seller: SellerProfile;
  total_earnings: string;
  available_to_claim: string;
  pending_rewards: number;
  posts_tracked: number;
  verified_posts: number;
  total_engagement: number;
}