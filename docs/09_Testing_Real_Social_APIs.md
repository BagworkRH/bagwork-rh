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
http://localhost:8000/api/v1/x/callback/
```
X rejects a trailing-slash mismatch, so copy it precisely. It must also be a URL
you can actually receive — see step 4 for the local tunnel.

**c. Write `.env` in the repo root** (never commit this file):
```
SOCIAL_PROVIDER_MODE=official
X_CLIENT_ID=your-consumer-key
X_CLIENT_SECRET=your-consumer-secret
X_REDIRECT_URI=http://localhost:8000/api/v1/x/callback/
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
# then:         GET  /api/v1/x/x/callback/?state=...&code=...
```

**f. Verify against the real API:**
```bash
python manage.py preflight_social --call x --verbose
```

You want to see your handle, then real posts with `reposted=False`. If
`referenced_tweets` is absent from the raw payload, Stage 1's originality gate
is reading a field that does not exist — that is the single most important thing
this step can tell you.

## 2. TikTok, end to end

TikTok requires an approved app before `video.list` returns anything.

1. developers.tiktok.com → Create App → choose **Content Posting API**.
2. Request `user.info.basic` and `video.list`.
3. Set the redirect URL to `http://localhost:8000/api/v1/tiktok/callback/`.
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
