/**
 * Brand-side types. A brand is the paying customer: it funds campaigns in the
 * platform stablecoin (USDG) and creators are paid from that balance.
 */

export type BrandStatus = "PENDING" | "ACTIVE" | "SUSPENDED";

export type FundingStatus = "PENDING" | "CONFIRMED" | "REJECTED";

export interface BrandProfile {
  id: number;
  company_name: string;
  contact_email: string;
  funding_wallet: string;
  status: BrandStatus;
  created_at: string;
  /** Served by the profile endpoint only; derived from confirmed deposits. */
  funded_balance?: string;
}

export interface BrandFunding {
  id: number;
  amount: string;
  chain_id: number;
  token_symbol: string;
  tx_hash: string;
  status: FundingStatus;
  campaign: number | null;
  funded_at: string;
  confirmed_at: string | null;
}

export interface BrandFundingList {
  fundings: BrandFunding[];
  confirmed_balance: string;
}

export interface BrandQuote {
  payout_total: string;
  platform_fee: string;
  platform_fee_bps: number;
  total_required: string;
  already_funded: string;
  shortfall: string;
  sufficient: boolean;
  /** Token the quote is denominated in, from the backend's funding token. */
  token_symbol?: string;
  /** Precision of that token, so the UI can confirm the fee matches the chain. */
  token_decimals?: number;
}

export interface BrandCampaignFunding {
  slug: string;
  name: string;
  status: CampaignStatus;
  budget: string;
  remaining_budget: string;
  funded: string;
}

export interface BrandCampaignList {
  campaigns: BrandCampaignFunding[];
  confirmed_balance: string;
}

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
// The backend engine can still compute impression/engagement/hybrid rewards,
// but they are not selectable at launch: rewards are paid per verified original
// post. See docs/02_Backend_API.md.
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

/**
 * A campaign the seller has joined, from `/api/v1/me/campaigns/`.
 *
 * Pairs the campaign with the seller's own participation: which campaign it is,
 * and what they have earned from it so far — the two halves of the question the
 * public campaign list cannot answer, because it does not know who is asking.
 */
export interface JoinedCampaign {
  campaign_id: number;
  slug: string;
  name: string;
  campaign_status: CampaignStatus;
  token_symbol: string;
  reward_model: RewardModel;
  reward_rate: string;
  remaining_budget: string;
  end_at: string;
  participation_status: "ACTIVE" | "LEFT" | "EXCLUDED";
  joined_at: string;
  cumulative_reward: string;
}

/**
 * Create/update payload for a campaign, mirroring the backend's
 * `CampaignWriteSerializer`. Only staff and brand accounts may send it; a brand
 * that sends it is recorded as the campaign's funder by the backend, so the
 * payload deliberately carries no brand id — it cannot be attributed to
 * someone else's money.
 *
 * `reward_model` is fixed to FIXED at launch: only a fixed reward per verified
 * original post is offered, so the field is present for clarity but not a free
 * choice. The budget must cover at least one payout, and `end_at` must be
 * after `start_at` — both enforced server-side and mirrored in the form.
 */
export interface CampaignCreateInput {
  name: string;
  slug: string;
  description?: string;
  project_name: string;
  token_symbol: string;
  chain_id: number;
  budget: string;
  reward_model: RewardModel;
  reward_rate: string;
  maximum_reward_per_seller?: string;
  maximum_rewards_per_seller?: number;
  start_at: string;
  end_at: string;
  requirements_json?: Record<string, unknown>;
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
  | "NOT_ORIGINAL"
  | "NOT_DISCLOSED"
  | "ACCOUNT_NOT_CONNECTED"
  | "PROVIDER_ERROR"
  | "SUSPICIOUS_ACTIVITY";

export type SocialPlatform = "x" | "tiktok";

export type SocialAccountStatus = "CONNECTED" | "PENDING" | "ERROR" | "REVOKED";

/**
 * A seller's linked account as returned by `GET /api/v1/x/connections/`.
 *
 * Credential material is deliberately absent: tokens are encrypted at rest and
 * never serialised to the client, so the only fields exposed are the ones a
 * creator needs to see their own link status.
 */
export interface SocialAccount {
  platform: SocialPlatform;
  username: string;
  display_name: string;
  status: SocialAccountStatus;
  connected_at: string;
  last_synced_at: string | null;
}

/**
 * A creator's own post as returned by `GET /api/v1/me/posts/`.
 *
 * `rejection_reason` explains a failed verification in prose so the creator can
 * correct it. `originality_evidence` records how the originality claim was
 * established -- a post that was never provider-confirmed cannot earn, which is
 * why the field is surfaced rather than kept server-side.
 */
export interface SocialPost {
  id: number;
  platform: SocialPlatform;
  external_post_id: string;
  post_url: string;
  campaign: string | null;
  published_at: string | null;
  verification_status: PostVerificationStatus;
  rejection_reason: string;
  is_original: boolean;
  originality_evidence: string;
  impressions: number;
  likes: number;
  reposts: number;
  replies: number;
  total_engagement: number;
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