# 09 — Testing Against Real Social APIs (Stage 2)

Every provider call in this repo has been verified against a **stub**. Stages 1
and 3 are correct against the *documented* contract, which is not the same
thing. This runbook is how to find out whether they are correct against reality.

Use `preflight_social` to check credentials and endpoint shape without going
through the app. It makes one authenticated call per platform, prints what came
back, mutates nothing, and never prints a secret.

## What you need

| | X | TikTok |
|---|---|---|
| Where | [console.x.com](https://console.x.com) | [developers.tiktok.com](https://developers.tiktok.com) |
| Cost | pay-per-use credits (no tiers) | free to apply |
| Approval | immediate, but *some endpoints need review* | **app review required** |
| Scopes we use | `tweet.read`, `users.read` | `user.info.basic`, `video.list` |
| Effort | ~30 min | days-to-weeks (review queue) |

**Start with X.** TikTok needs an approved app, and waiting on a review is not a
good use of your first pass.

## 1. X, end to end

**a. Create the app.** console.x.com → Projects → your project → Keys and
tokens. Enable **OAuth 2.0**. Set the app to **Read** permissions (you do not
want write access for a read-only discovery product).

**b. Register the callback URL exactly:**
```
http://127.0.0.1:8000/api/v1/x/x/callback/
```
Note the doubled `x`: social routes are mounted at `/api/v1/x/` and the
per-platform path adds the platform again (`x/<platform>/callback/`). Registering
`/api/v1/x/callback/` (one `x`) fails with X's generic "Something went wrong"
page and no callback ever arrives. X matches the string exactly, so the host
matters too: `localhost` and `127.0.0.1` are different values to X even though
they are the same machine.

**c. Write `.env` in the repo root** (never commit this file):
```
SOCIAL_PROVIDER_MODE=official
X_CLIENT_ID=your-consumer-key
X_CLIENT_SECRET=your-consumer-secret
X_REDIRECT_URI=http://127.0.0.1:8000/api/v1/x/x/callback/
```

**d. Check configuration, no network:**
```bash
cd backend
python manage.py preflight_social
```

**e. Get a user access token.** OAuth 2.0 with PKCE needs a browser, so use the
app itself:
```bash
python manage.py runserver
# as a seller: POST /api/v1/x/x/connect/  -> follow authorize_url
```

`connect` records a pending `SocialOAuthState` (the `state`, the PKCE verifier
and the user), and the callback resolves the user from `state` alone before
redirecting the browser back to the app. The callback is deliberately public:
the provider's redirect is a top-level browser navigation, so it carries neither
the SPA's bearer token (which lives in `localStorage`) nor a session cookie — a
token-based SPA has no session to lean on. Trust comes from `state`, which is
unguessable, single-use, and expires after `SOCIAL_OAUTH_STATE_TTL_SECONDS`
(default 600 seconds).

**f. Verify against the real API:**
```bash
python manage.py preflight_social --call x --verbose
```

You want to see your handle, then real posts with `is_repost=False`.

### What the first live run actually found

Verified on 2026-10-06 against `GET /2/users/:id/timelines/reverse_chronological`.
Every one of these was invisible to a suite built on guessed fixtures:

| Finding | Consequence |
| --- | --- |
| `referenced_tweets[].type` is **`retweeted`**, not `reposted` | The originality gate tested for `"reposted"`, so it never matched. Every real retweet was recorded `PROVIDER_CONFIRMED` and was payable. `quoted` was correct, which is why quotes were caught and the gap stayed hidden. |
| The real enum is `retweeted \| quoted \| replied_to` | Any other value now fails closed rather than being assumed original. |
| An original post **omits** `referenced_tweets` entirely | Absence is normal and means original; do not read a missing key as an error. |
| `start_time` rejects microsecond precision | X's pattern is `yyyy-MM-dd'T'HH:mm:ss[.SSS]X`. Django's `timezone.now()` carries microseconds, so the first real discovery call failed with HTTP 400 until `_rfc3339` truncated to milliseconds. |
| `exclude=retweets,replies` hides retweets from discovery | The bug survived in production-shaped runs because the filter removed the very posts that would have exposed it. Manual submission was the exposed path. |

Fixing the fixtures mattered as much as fixing the code: `test_refreshed_repost_fails_verification`
— the end-to-end "a repost cannot earn" guarantee — had been asserting against
`"reposted"`, so it passed while the gate was open.

## 2. TikTok, end to end

TikTok requires an approved app before `video.list` returns anything.

1. developers.tiktok.com → Create App → choose **Content Posting API**.
2. Request `user.info.basic` and `video.list`.
3. Set the redirect URL to `http://127.0.0.1:8000/api/v1/x/tiktok/callback/`
   (note `/x/tiktok/` — social routes are mounted under `/x/` for every platform).
4. **Submit for review.** This is the wait. Meanwhile test X.
5. Make one **public** video. `video/list` only returns public posts.
6. `python manage.py preflight_social --call tiktok --verbose`

## 3. The full pipeline

Once preflight is green, prove the product end to end:

```bash
python manage.py runserver            # terminal 1
celery -A config worker -l info       # terminal 2
celery -A config beat -l info         # terminal 3
```

1. Create a campaign. **There is no campaign-create API yet (Stage 4)** — use
   `python manage.py shell` or Django admin.
2. Set `required_hashtags: ["#yourtag"]` in `requirements_json`.
3. Post something publicly containing that hashtag, with the connected account.
4. Within 5 minutes, check it arrived:
```bash
python manage.py shell -c "
from apps.social.models import SocialPost
for p in SocialPost.objects.order_by('-discovered_at')[:3]:
    print(p.platform, p.external_post_id, p.verification_status,
          p.originality_evidence, p.is_original)"
```
   Expect `DISCOVERED PROVIDER_CONFIRMED True`, then `VERIFIED`.
5. **Then test the rejection path** — repost someone else's post with the
   hashtag. It must land in `NOT_ORIGINAL` and earn nothing. This is the test
   that matters most; a working happy path proves nothing on its own.
6. `calculate_pending_rewards`, then check the Reward exists at the fixed rate.

## 4. Local callback without a public URL

X only redirects to a registered URL. For local dev either tunnel
(`cloudflared tunnel --url http://localhost:8000`, then register the tunnel URL)
or register the localhost URL — X generally allows it while the app is in
development.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: .official` | `SOCIAL_PROVIDER_MODE` is `mock`. |
| `Timeline fetch failed: HTTP 403` | Token lacks `tweet.read`, or the app is in Read-only mode and hit a restricted endpoint. |
| `HTTP 401` | Expired or revoked token; re-run the connect flow. |
| `timeline -> 0 post(s)` | No posts in the window, or account is protected. Post something public. |
| `referenced_tweets` missing from raw JSON | The field is not requested, or the endpoint ignores it. Stage 1 needs this — check the `tweet.fields` param. |
| TikTok `403` on `video/list` | App not yet approved for the scope. |

## What "verified" means

Stage 2 is done when: a real post on each platform pays out at the fixed rate,
a real repost on each platform is rejected, and the raw payloads match what
`normalize_post` / `normalize_video` expect. Until then, Stages 1 and 3 rest on
documentation, not observation.
