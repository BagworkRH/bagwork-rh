# 08 — Production Readiness Roadmap

Ordered by risk, not by convenience. Each stage states what "done" means.
Nothing here is speculative scope; it is the shortest path from the current
state to real creators being paid real money.

## Where we actually are

Solid: the multi-platform provider layer, the fixed-reward policy, the
originality/disclosure gates, and the trust boundary that stops a seller from
self-reporting their way to a payout.

Thin: neither provider has touched a real API, the discovery path that *is* the
product does not exist, and anti-abuse is a stub.

## Stage 0 — Unblock ourselves  (blocking everything)  — DONE

The last three fixes (platform-scoped submit, `importlib` registry fix,
`refresh_post_facts`) are committed nowhere and the full suite has not run
green since they landed. No further work should start on an unverified tree.

- [x] Kill stray `python.exe` processes wedging the test runner
- [x] `manage.py test` serial, green (220)
- [x] Commit + push, CI green (`135da1c`)

**Done when:** CI is green on a commit containing all three fixes.

## Stage 1 — Make failures fail closed  (highest risk per line of work)  — DONE

The originality gate defaulted to "original" and was corrected by a provider
call. If that call was wrong, timed out, or the field was absent, a repost
verified and earned. It failed **open**, the dangerous direction for a system
that pays out.

- [x] `originality_evidence` records provenance: `SELF_REPORTED` /
      `PROVIDER_CONFIRMED` / `PROVIDER_REJECTED` / `PROVIDER_UNAVAILABLE`
- [x] Unconfirmed originality cannot reach `VERIFIED` (`PROVIDER_ERROR` instead)
- [x] `refresh_post_facts` records `PROVIDER_UNAVAILABLE` on a provider error
- [x] Money path re-asserts it: `calculate_reward` refuses unconfirmed posts
- [x] 6 fail-closed tests; verified a broken provider yields no payout

**Done when:** no code path exists where an unavailable provider yields a paid
reward. Prove it by breaking the provider and asserting nothing is paid.

**Not done (Stage 8):** alerting on provider unavailability. Right now it is
logged, not paged.

## Stage 2 — Real API credentials  (X DONE, TikTok blocked on review)

Neither adapter had ever been called against a live API. Everything in Stage 1
was a hypothesis until this happened — and the first live call proved the
suspicion right.

**X — verified 2026-10-06.** Credentials are configured, an OAuth 2.0 + PKCE
connect completed in a browser, and a real account (`@IsaacMadu9`) was linked
and read back through the real timeline endpoint.

- [x] X developer app, PKCE credentials into env
- [x] Real OAuth connect → callback → token exchange → account linked
- [x] `users/me` and the timeline endpoint return real data
- [x] Confirm the real shape of `referenced_tweets` matches `normalize_post`
      — **it did not.** X returns `type: "retweeted"`; the code tested for
      `"reposted"`. See below.
- [x] Record actual response shapes as contract fixtures
      (live payloads pinned in `ProviderOriginalityMappingTests`)
- [ ] One end-to-end connect -> discover -> verify -> reward, on a funded campaign
- [ ] TikTok app, Content Posting API credentials into env (blocked on app review)

**The bug the live run caught.** `normalize_post` decided originality with
`"reposted" in ref_types`. X never sends that string. So every real retweet was
recorded `PROVIDER_CONFIRMED` and was therefore **payable** — a creator could
retweet someone else's campaign post and be paid the fixed reward for it.

Two things had kept it invisible:

1. **Fixtures encoded the same guess.** `test_refreshed_repost_fails_verification`
   — the end-to-end "a repost cannot earn" test — passed because it asserted
   against `"reposted"` too. A suite built on a wrong assumption cannot refute it.
2. **`exclude=retweets,replies`** removes retweets from discovery, so the
   production-shaped path never carried the posts that would expose it. The
   exposed path was manual submission, where `refresh_post_facts` re-fetches the
   post and re-derives originality.

The fix matches the real enum and fails closed on anything unrecognised. Live
verification: **0 of 62 reference-bearing posts were flagged before; 49 are now.**
Observed type histogram is exactly `retweeted: 50, quoted: 10, replied_to: 2` —
no unrecognised values, so the fail-closed branch has no untested tail.

Also found and fixed on the same run: `start_time` rejects microsecond precision
(X's pattern is `yyyy-MM-dd'T'HH:mm:ss[.SSS]X`), which made the first real
discovery call fail with HTTP 400. `preflight_social` had its own copy of that
bug, so the verification tool would have misreported the adapter.

**Done when:** a real post on each platform pays out correctly, and a real
repost on each platform is rejected. X's repost rejection is now proven against
real payloads; the TikTok half still waits on app review.

**Still open:** TikTok credentials, and a full connect → discover → verify →
reward against a funded campaign (which needs the funding loop from Stage 6).



## Stage 3 — Discovery, the actual product  — DONE (unverified against a live API)

Creators previously pasted a URL into a test endpoint. `discover_posts` raised on
both adapters. Discovery is now implemented for both platforms and scheduled.

- [x] `discover_posts` for X via `GET /2/users/:id/timelines/reverse_chronological`
      (X renamed this endpoint; the old `/2/users/:id/tweets` path is gone)
- [x] `discover_posts` for TikTok via `POST /v2/video/list/`. It does exist —
      the earlier "no equivalent" assumption was wrong
- [x] Celery beat schedule every 5 minutes, per campaign x connected account
- [x] Idempotency: per-campaign per-platform watermark + `(platform, id)` uniqueness
- [x] A provider error does NOT advance the watermark, so a transient outage
      cannot silently discard posts published during the gap
- [x] 16 discovery tests

**Done when:** a creator who links an account and posts gets the reward with no
manual step.

**Verified only against stubs.** Both adapters match the documented contract, not
a live response. See Stage 2 — this is the code Stage 2 will exercise.

**Known limits:**
- One timeline page per poll (X `max_results=100`). A creator posting more than
  100 posts between polls would need pagination; unlikely but unbounded.
- TikTok pagination is capped at 5 pages x 20 videos per poll.
- X rate limits are per-user (900/15min); sharding, not a longer interval, is
  the answer at scale.

## Stage 4 — Campaign creation API  — DONE

Campaigns came from the seed or Django admin. The `FIXED`-only validation existed
but guarded a door nobody could walk through.

- [x] `POST /api/v1/campaigns/`, staff-only (`IsAuthenticatedOrReadOnly` plus an
      explicit staff check, so an authenticated non-staff user gets 403)
- [x] `PATCH /api/v1/campaigns/<slug>/`, staff-only
- [x] `POST /api/v1/campaigns/<slug>/launch/` to publish a draft
- [x] Validation lives in the service, so the shell and admin are held to the
      same rules: fixed-only, budget must cover at least one payout, window
      order, seller cap, and no budget beyond `max_posts x rate`
- [x] `budget`, `reward_rate`, `chain_id` and `remaining_budget` are immutable
      once set -- changing them mid-flight would make calculated rewards
      irreproducible. Start a new campaign instead
- [x] An ACTIVE campaign cannot be edited; pause it first
- [x] Money fields are coerced to Decimal in the service, so a string from the
      shell or a test cannot be stored and fail later inside the reward engine
- [x] 22 tests

**Done when:** an operator can create and launch a campaign without a shell.

## Stage 5 — Anti-abuse  — DONE

The fixed-reward model makes post-farming the central threat: with no bound on
*how many* rewards a creator earns, N accounts posting N times earn N x N.

The original note called this "a stub" and "no rate limiting". That was out of
date when re-read — the signal engine, score, review queue and human-decision
flow all existed — but three real gaps did remain, and all three are closed.

- [x] **Rate limit post submission** — `SubmissionThrottle` at `THROTTLE_SUBMIT`
       (20/hour). The global user rate was 1000/hour, which is a scraping guard,
       not an anti-abuse control: it says nothing about one host looping. The
       Celery discovery path does not use this endpoint, so the real flow is
       unaffected.
- [x] **`maximum_rewards_per_seller` enforced at payout.** This was the
       significant one. The field was validated at campaign creation, stored,
       and exposed in serializers, then ignored by the reward engine — so a
       brand setting "3 rewards per creator" paid an unlimited number. Enforced
       in `apply_caps`, which every payout passes.
- [x] **Count rewards from PENDING.** The count used `_COUNTED_STATUSES`, which
       excludes PENDING. A farm's rewards are all PENDING, so the cap counted
       zero and never fired — verified by a test that first asserted 50 rewards
       were earned where 15 should have been. `calculate_reward` debits the
       budget when the row is created, so PENDING is money already promised.
- [x] **Cross-account signals** — `collect_farm_signals`: identical long-form
       text across distinct sellers, and one wallet behind several sellers. All
       pre-existing signals were scoped to a single seller, which is exactly
       why they missed a farm: from inside one account a farm looks like an
       ordinary prolific creator.
- [x] **Signals wired into the scheduled scan.** `evaluate_post` merges both
       signal sets. Called once, because `queue_flag` *replaces* a subject's
       signals — two separate calls would have overwritten rather than
       accumulated evidence.

**Done when:** a scripted farm of N accounts earns materially less than N
rewards. Tested directly: 5 accounts x 10 posts earns 15, not 50 — payout is
bounded per account, so extra accounts buy nothing.

**Not done:**
- **Blocking rather than flagging.** A shared wallet queues a flag but does not
  stop the payout. Stopping is an enforcement decision, and the design rule is
  never auto-accuse on a signal. The caps bound the loss meanwhile, so the
  urgency is lower than it would otherwise be — but a reviewer still has to be
  in the loop.
- **Reversal path exercised end-to-end.** `REVERSED` correctly releases a slot,
  but no reversal has ever run against a live reward.
- **Review UI.** Flags are actionable via the staff API and Django admin; there
  is no purpose-built review screen.

## Stage 6 — Money actually moves  (blocked on funding)

The contract compiles and its tests pass, but no reward has ever been claimed
on-chain. This is the step that makes the product real and the step nobody can
do for us.

- [ ] Funded deployer key on Robinhood Chain
- [ ] Deploy `RewardToken`, record address
- [ ] One real claim, verified against a block explorer
- [ ] Failover: what happens if the RPC or contract is unavailable at claim time

**Done when:** a claim settles on a public explorer.

## Stage 7 — Frontend parity

No campaign-create UI. The onboarding page still hardcodes "X account:
Connected (mock)" — now wrong twice over, since the platform is configurable
and connect is a real OAuth flow.

- [ ] Platform picker using `/x/platforms/`
- [ ] Real connect/disconnect UI, both platforms
- [ ] Campaign create screen (Stage 4)
- [ ] Post status and rejection reasons surfaced to creators
- [ ] Remove remaining X-only copy in `how-it-works` / `onboard`

**Done when:** a creator can do everything without a developer present.

## Stage 8 — Operations

- [ ] Structured logging with request/post ids
- [ ] Error tracking and uptime alerting
- [ ] Provider-specific dashboards (failure rate, latency)
- [ ] Secret rotation for stored OAuth tokens
- [ ] Backup/restore drill for a live database
- [ ] Terms of service covering disclosure obligations and reversals

**Done when:** a provider outage pages someone and the runbook is unambiguous.

## Sequencing

Stages 0 and 1 are ours and are small. Stage 2 is blocked on credentials and
should be started in parallel today, because it gates whether Stage 1 was even
pointed at the right field. Stages 3-5 are the real build. Stage 6 is blocked
on funding. Stages 7-8 are what make it operable.

**Do not start Stage 3 or later until Stage 0 is green.**
