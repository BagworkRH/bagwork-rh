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

## Verified accounts only
A post is only tracked when its author carries a verification badge. Discovery
reads the connected account's **own** timeline, so the author of every discovered
post is that account — which is why this is one gate on the account rather than a
check on each post.

The badge is read from X's `verified_type` (`blue` · `business` · `government`),
**not** the legacy `verified` boolean. That boolean reported `false` for Premium
subscribers holding a visible blue badge (xurl issue #41, fixed in v1.2.0) while
`verified_type` said `"blue"` in the same response, so a gate built on it would
refuse to pay real creators. Anything unrecognised — an absent field, a value X
adds later — counts as no badge: this decides whether someone is paid, so an
unknown string cannot pass as a credential.

Because X Premium is a **subscription**, a badge held at connect time can lapse
with nothing on this side changing. A connect-time check alone is farmable:
subscribe for one month, connect, cancel, keep earning. So the badge is re-read
from the provider once a day (`VERIFICATION_TTL`), before the timeline call, and
discovery acts on the stored value in between.

Rules the implementation holds to:

- **Fail closed, but never on an outage.** If the badge cannot be read, the poll
  is skipped and the stored badge is left untouched. An unreachable X must not
  strip a verified creator of their badge and stop their earnings — the same rule
  that stops a post being marked VERIFIED while the provider is down.
- **No request for an untrackable account.** The gate runs before the timeline
  call, so an unverified account costs nothing and the campaign watermark is left
  alone, because nothing was read.
- **A change is audited.** `SOCIAL_VERIFICATION_CHANGED` records a badge
  appearing or disappearing, because it changes whether someone can be paid.
- **The creator is told.** An unverified account still connects and still shows
  in the dashboard, marked, with the consequence spelled out. An account that
  looks connected and silently earns nothing is the most confusing state this
  product can present.

`REQUIRE_VERIFIED_ACCOUNTS` (default `true`) switches the rule off and tracks
every connected account.

**What this rule is not.** The blue badge is a paid X Premium subscription, so
requiring it excludes every creator who will not buy one — it is a supply filter,
not a quality signal. It is also not a fraud control: spammers buy badges too.
The anti-abuse signals below remain what actually catches farming.

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