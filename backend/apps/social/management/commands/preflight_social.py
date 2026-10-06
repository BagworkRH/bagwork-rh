"""Check that real social API credentials work, before trusting the pipeline.

Stage 2 of docs/08_Production_Roadmap.md exists because every provider call so
far has been verified against a stub. This command makes the first live call
cheap and legible: it reports what is configured, makes one authenticated
request per platform, and prints exactly what came back.

    python manage.py preflight_social            # config only
    python manage.py preflight_social --call x   # + timeline + normalize
    python manage.py preflight_social --call all --verbose

It never prints a secret, and never mutates a SocialPost or Reward.
"""
import json
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.social.models import SocialPlatform
from apps.social.providers import provider_mode
from apps.social.providers.base import SocialProviderError
from apps.social.providers.official import OfficialXProvider, _rfc3339
from apps.social.providers.tiktok import OfficialTikTokProvider

# Never echoed, only reported as present/absent.
SECRET_VARS = {
    SocialPlatform.X: ("X_CLIENT_ID", "X_CLIENT_SECRET", "X_REDIRECT_URI"),
    SocialPlatform.TIKTOK: ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI"),
}


class Command(BaseCommand):
    help = "Verify real social API credentials and endpoint shape (Stage 2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--call",
            choices=["x", "tiktok", "all"],
            default=None,
            help="Also exercise the discovery endpoints with the configured token.",
        )
        parser.add_argument(
            "--token", default=None, help="A user access token to use instead of the stored one."
        )
        parser.add_argument("--verbose", action="store_true", help="Print raw payloads.")

    def handle(self, *args, **options):
        mode = provider_mode()
        self.stdout.write(f"provider mode : {mode}")
        if mode != "official":
            self.stdout.write(
                self.style.WARNING(
                    "SOCIAL_PROVIDER_MODE is not 'official'. Set it in .env before "
                    "trusting this check -- a mock adapter will appear to work."
                )
            )
            return

        if options["call"] == "all":
            targets = ["x", "tiktok"]
        elif options["call"]:
            targets = [options["call"]]
        else:
            targets = ["x", "tiktok"]
        for platform in targets:
            if self._check_config(platform):
                self._check_call(platform, options)

    def _check_config(self, platform) -> bool:
        self.stdout.write(f"\n--- {platform} ---")
        missing = []
        for var in SECRET_VARS[platform]:
            if getattr(settings, var, "") or "":
                self.stdout.write(f"  {var:<24} set")
            else:
                self.stdout.write(self.style.ERROR(f"  {var:<24} MISSING"))
                missing.append(var)
        if missing:
            self.stdout.write(
                self.style.ERROR(f"  cannot call {platform}: {len(missing)} var(s) missing")
            )
            return False
        return True

    def _check_call(self, platform, options):
        provider = OfficialXProvider() if platform == "x" else OfficialTikTokProvider()
        token = options["token"] or self._stored_token(platform)
        if not token:
            self.stdout.write(
                self.style.WARNING(
                    "  no access token. Run the OAuth connect flow first, or pass "
                    "--token. Skipping the live call."
                )
            )
            return
        self.stdout.write("  making an authenticated call...")
        try:
            if platform == "x":
                self._call_x(provider, token, options)
            else:
                self._call_tiktok(provider, token, options)
        except SocialProviderError as exc:
            self.stdout.write(self.style.ERROR(f"  provider error: {exc}"))
        except Exception as exc:  # noqa: BLE001 - a preflight tool reports anything
            self.stdout.write(self.style.ERROR(f"  {type(exc).__name__}: {exc}"))

    def _stored_token(self, platform):
        """Decrypt the most recently connected account's token, if any."""
        from apps.social.crypto_utils import decrypt_secret  # noqa: PLC0415
        from apps.social.models import SocialAccount  # noqa: PLC0415

        account = (
            SocialAccount.objects.filter(platform=platform, status="CONNECTED")
            .exclude(encrypted_credentials=b"")
            .order_by("-connected_at")
            .first()
        )
        if account is None:
            return None
        creds = json.loads(
            decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
        )
        return creds.get("access_token")

    def _call_x(self, provider, token, options):
        """The calls that matter: identity, timeline, and normalization."""
        identity = provider.get_account(token)
        self.stdout.write(
            f"  users/me   -> @{identity.get('username')} "
            f"({identity.get('provider_user_id')})"
        )
        self.stdout.write("  referenced_tweets is what Stage 1's originality gate needs.")
        body = provider._get_timeline(  # noqa: SLF001 - deliberate: probing internals
            token,
            identity["provider_user_id"],
            {
                "max_results": 5,
                # Must go through the adapter's formatter: X rejects the
                # microsecond precision a raw `.isoformat()` produces, which
                # made this probe report a failure that the real discovery
                # path (which uses `_rfc3339`) never had.
                "start_time": _rfc3339(timezone.now() - timedelta(days=7)),
                "exclude": "retweets,replies",
                "tweet.fields": "created_at,text,referenced_tweets",
            },
        )
        data = body.get("data") or []
        self.stdout.write(f"  timeline   -> {len(data)} post(s) in the last 7 days")
        if data and options["verbose"]:
            self.stdout.write(json.dumps(data[0], indent=2)[:1500])
        for tweet in data:
            p = provider.normalize_post(tweet)
            self.stdout.write(
                f"    {p['post_id']}  repost={p['is_repost']}  quote={p['is_quote']}  "
                f"text={p['text'][:40]!r}"
            )
        if not data:
            self.stdout.write(
                self.style.WARNING(
                    "  no posts found: post something publicly and re-run, or the "
                    "token lacks timeline access."
                )
            )

    def _call_tiktok(self, provider, token, options):
        identity = provider.get_account(token)
        self.stdout.write(
            f"  user/info  -> {identity.get('username')} "
            f"({identity.get('provider_user_id')})"
        )
        body = provider._list_videos(token, None)  # noqa: SLF001 - deliberate
        videos = (body.get("data") or {}).get("videos") or []
        self.stdout.write(f"  video/list -> {len(videos)} video(s)")
        if videos and options["verbose"]:
            self.stdout.write(json.dumps(videos[0], indent=2)[:1500])
        for video in videos[:5]:
            p = provider.normalize_video(video)
            self.stdout.write(
                f"    {p['post_id']}  {str(p['created_at'])[:19]}  text={p['text'][:40]!r}"
            )
        if not videos:
            self.stdout.write(
                self.style.WARNING(
                    "  no videos: make one public and re-run, or the app is not "
                    "approved for video.list."
                )
            )
