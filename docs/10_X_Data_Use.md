## X Data Use & Compliance

What the platform actually does with X data, as implemented. Use this to answer
X's developer compliance questions; keep it accurate if the code changes.

### Use case

bagworkRH is a creator-rewards platform. A marketing team creates a campaign with
a fixed token amount per qualifying post. Creators connect their X account,
publish posts themselves, and earn a fixed reward for each post that passes
verification.

### Scopes

`tweet.read`, `users.read`, `offline.access` — **read only**. No write scopes. We
never post, reply, like, repost, follow, or DM on a user's behalf. There is no
code path that writes to X. `offline.access` is not a write scope: it is what
lets us renew the read token when it expires, so a connected account keeps
working past the two-hour token lifetime without the creator reconnecting.

### What we read

- The authenticated user's own profile: user ID, username, display name, avatar URL
- Their own posts: ID, text, timestamp, engagement counts
- Whether a post is a repost or quote of someone else's content

### Why — the specific purpose

Verification answers one question: **is this the creator's own original work?**
We read `referenced_tweets` to distinguish an original post from a repost or
quote. That is the sole basis for payout, because the product pays a creator for
producing something rather than for amplifying another account.

### What we store

| Data | Notes |
|---|---|
| Post ID, platform, URL, text snapshot, publication date | For verification and audit |
| Engagement metrics + periodic snapshots | Reward reproducibility |
| Verification status and rejection reason | Audit trail; shown to the creator |
| X user ID, username, display name, avatar | To attribute the post to a connected account |
| OAuth access + refresh tokens | **Encrypted at rest (AES-GCM)** |

### What we do not do

- No selling, licensing, or sharing of X data with third parties
- No advertising or targeting
- No user profiling, no cross-platform identity resolution
- No model training or AI/ML use of X data
- No automated decision-making about people based on this data

### Access control

- **Staff only:** `GET /api/v1/posts/`, `GET /api/v1/posts/<id>/`,
  `GET /api/v1/admin/*`. These expose post URLs and engagement counts derived
  from X data and are restricted to `IsAdminUser`.
- **Creator, own data only:** `GET /api/v1/me/posts/` returns the signed-in
  seller's own posts, including rejection reasons so a creator can act on them.
  Scoped by `seller=request.user.seller_profile` — a creator can never read
  another seller's posts.
- **No endpoint returns post text publicly.** `text_snapshot` is not in any
  unauthenticated response.

Enforced by `tests/test_post_privacy.py`, which asserts the lock *and* the
creator-scoped replacement, so a regression re-exposing X data fails CI.

### Retention

**Implemented.** Platform-derived content is erased `SOCIAL_RETENTION_DAYS` after
the campaign it belongs to ends — 365 days by default, configurable per
environment. The window starts at the campaign's *end* rather than at discovery,
so it measures how long the data stays operationally useful rather than how long
ago it happened to be found.

`apps.social.erasure.purge_expired_social_data` runs daily via Celery beat
(`purge-expired-social-data`). Per post:

| Erased | Kept |
|---|---|
| `text_snapshot`, `post_url`, `external_post_id` (tombstoned) | the row itself, its `verification_status` and `originality_evidence` |
| engagement counters (zeroed) | the `Reward` and its amount |
| `PostMetricSnapshot` rows, including `raw_provider_payload` | the audit trail around them |

The row survives because `Reward.post` is PROTECT: deleting it would either
cascade into the ledger or fail outright, so erasure anonymises in place. A post
with no reward is handled identically, for consistency and so the audit trail
never has holes. Erasure is idempotent (`SocialPost.erased_at`), so a re-run —
or a manual one — is safe.

### Deletion

Two different operations, and the distinction is the point:

- **Disconnecting** (`POST /api/v1/x/<platform>/disconnect/`) marks the account
  `DISCONNECTED` and stops polling. It erases nothing, because the creator may
  simply reconnect.
- **Erasure** (`POST /api/v1/me/data-deletion/` with `{"confirm": "DELETE"}`)
  removes the person's identifiers and every piece of platform-derived data:
  post content anonymised as above, stored OAuth credentials destroyed and the
  token revoked at the platform, linked-account handles replaced and accounts
  disconnected, pending OAuth state and API tokens deleted, and the account's own
  email, username and names replaced with the password made unusable and the
  account deactivated.

**Rewards and claims are deliberately retained**, with their amounts and statuses.
They are the audit trail a payout dispute is settled against, and `Reward.seller`
is PROTECT — so they cannot be removed without destroying the ledger. This is a
documented limitation rather than an oversight: every erasure writes a
`SELLER_DATA_ERASED` audit entry recording `financial_records_retained: true`, so
the omission is visible in the record rather than silent. The user row itself is
kept, anonymised, because the ledger's foreign keys point at it.
