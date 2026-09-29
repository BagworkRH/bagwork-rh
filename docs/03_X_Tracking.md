# 03 — X Tracking & Reward Engine

Compliant system linking an authenticated X account to a seller profile,
discovering qualifying posts via **supported X API capabilities**, verifying
campaign requirements, recording metrics, and calculating rewards.

**Rule:** use official X API and granted permissions. Do not scrape X, bypass
rate limits, evade access controls, or fabricate engagement data. Provider
limitations must be handled gracefully.

## X account linking
OAuth authorization → callback → verify state/PKCE → exchange code → retrieve
identity → match to one seller → encrypt credentials → store provider user id,
username → mark connected. One X account should not link to multiple active
sellers.

## Seller code
Cryptographically secure, non-sequential, e.g. `SELLER-7K4M2P`.
Unique, case-normalized, difficult to guess, never reused, indexed.

## Post verification pipeline
```
DISCOVERED → BASIC_VALIDATION → CAMPAIGN_MATCH → DUPLICATE_CHECK
  → METRICS_PENDING → VERIFIED → REWARD_CALCULATED → APPROVED
```
Failure states: `NOT_ELIGIBLE · DUPLICATE · OUTSIDE_CAMPAIGN_WINDOW ·
REQUIREMENT_MISSING · ACCOUNT_NOT_CONNECTED · PROVIDER_ERROR ·
SUSPICIOUS_ACTIVITY`

## Metrics
Track only provider-available metrics; **store snapshots** (not overwritten):
`10:00=1000 likes, 12:00=1400 likes…` for auditability.

## Synchronization (Celery)
discover qualifying posts · refresh post metrics · retry failed provider
requests · reconcile provider data · calculate pending rewards · flag
suspicious activity. Exponential backoff for transient errors.

## Provider adapter
`XProvider` interface: `authorize() · callback() · get_account() ·
discover_posts() · get_post() · get_metrics() · revoke()`.
The rest of the app never depends on raw X API calls.

## Reward engine
Inputs: campaign, post, metric snapshot, seller, current budget, seller reward
history. Output: gross reward, deductions/exclusions, final reward,
calculation version, explanation. Every reward reproducible.

**Launch model: fixed per verified original post** (e.g. $5/post). Rewards are
paid for a creator producing original, disclosed content — not for reach.
Impression-based ($2 per 1k), engagement-based ($0.50 per 100) and hybrid
calculations still exist in the engine but are **not selectable via the API**:
those pay for metrics we cannot independently verify, which would undercut the
platform's auditability. Re-enabling them is a deliberate later decision.

Originality gate: reposts and quotes never earn. X reports this through
`referenced_tweets`, mapped to `is_repost` / `is_quote`; a post is original
when both are false. A reply is the creator's own words and still counts.

Always enforce caps.

## Anti-fraud
Signals: abnormal engagement spikes, repeated/duplicate posts, excessive
posting frequency, suspicious account patterns, engagement inconsistent with
history, bot-like activity. **Never auto-accuse on a weak signal** — use a risk
score and review queue.

## Campaign budget
Before approving: lock budget row → check remaining → calculate → cap to
remaining → reserve/deduct → commit. Budget reaching zero stops approvals.

## Reward lifecycle
`PENDING → VERIFIED → APPROVED → AVAILABLE → CLAIMED`
Reversal: mark `REVERSED`, record reason, audit event — never silently modify
history.

## Provider outages
Keep existing verified data, pause new verification, show status to admins,
retry automatically. Never mark posts verified because the provider is down.

## Compliance
Paid partnership/disclosure guidance, ToS, privacy policy, campaign rules,
content restrictions, reporting/contact mechanism. Not designed around spam,
fake engagement, or evasion of platform enforcement.