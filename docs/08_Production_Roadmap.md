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

## Stage 2 — Real API credentials  (blocked on us, not engineering)

Neither adapter has ever been called against a live API. Everything in Stage 1
is a hypothesis until this happens.

- [ ] X developer app, PKCE credentials into env
- [ ] TikTok app, Content Posting API credentials into env
- [ ] Confirm the real shape of `referenced_tweets` matches `normalize_post`
- [ ] One end-to-end connect -> discover -> verify -> reward, per platform
- [ ] Record actual response shapes as contract fixtures

**Done when:** a real post on each platform pays out correctly, and a real
repost on each platform is rejected.

**Risk if skipped:** Stage 1 may be hardening a field name we guessed.



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

## Stage 4 — Campaign creation API

Campaigns come from the seed or Django admin. The `FIXED`-only validation exists
but guards a door nobody can walk through.

- [ ] `POST /campaigns/`, staff-only
- [ ] Requirement editor (hashtags, disclosure, window, caps)
- [ ] Budget validation: budget >= rate, caps sane
- [ ] Publish / pause / end transitions exposed

**Done when:** an operator can create and launch a campaign without a shell.

## Stage 5 — Anti-abuse  (under-built relative to its risk)

The fixed-reward model makes post-farming the central threat. Today it is a
stub, and there is no rate limiting on submit.

- [ ] Rate limit post submission per account
- [ ] One payout identity per account; block obvious duplicate payouts
- [ ] Real `flag_suspicious_activity` signals (burst posting, identical text
      across accounts, new account + large reward)
- [ ] Risk queue the review UI can act on; never auto-accuse on a weak signal
- [ ] Reversal path exercised end-to-end

**Done when:** a scripted farm of N accounts earns materially less than N
rewards.

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
