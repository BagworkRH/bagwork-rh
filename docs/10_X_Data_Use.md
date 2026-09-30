## X Data Use & Compliance

What the platform actually does with X data, as implemented. Use this to answer
X's developer compliance questions; keep it accurate if the code changes.

### Use case

bagworkRH is a creator-rewards platform. A marketing team creates a campaign with
a fixed token amount per qualifying post. Creators connect their X account,
publish posts themselves, and earn a fixed reward for each post that passes
verification.

### Scopes

`tweet.read`, `users.read` — **read only**. No write scopes. We never post,
reply, like, repost, follow, or DM on a user's behalf. There is no code path
that writes to X.

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

Not yet implemented. Posts are retained for the life of a campaign so reward
calculations stay reproducible and auditable. **A concrete retention period
(e.g. campaign end + 12 months) and a user-initiated deletion endpoint are
pre-launch work.** X's compliance review will likely ask about both.

### Deletion

A creator can disconnect their account (`POST /api/v1/x/<platform>/disconnect/`),
which marks the connection `DISCONNECTED` and stops future polling. This does
**not** delete stored posts or tokens, because rewards already paid must remain
auditable. Hard erasure is unimplemented.