"""Standalone X OAuth2 + PKCE check. No Django login required.

The normal connect flow needs an authenticated Django session, because X
redirects the browser back to our callback and a token-authenticated API client
cannot carry an Authorization header through a redirect. That makes it awkward
to verify credentials for the first time.

This script does the PKCE handshake by hand, in your own browser:

  1. Opens X's authorize page.
  2. You approve access.
  3. X redirects to http://localhost:8000/... and shows an error. That is
     EXPECTED. Ignore it and continue.
  4. Copy the FULL URL out of the address bar and paste it here.
  5. This script exchanges the code for a token and calls the APIs the product
     depends on.

    python scripts/x_oauth_check.py

It prints field NAMES and counts, never a token or secret. The token stays in
memory and is never written to disk.
"""
import base64
import hashlib
import os
import secrets
import sys
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
API = "https://api.x.com/2"


def read_env(name):
    """Read a key from the environment, falling back to backend/.env."""
    value = os.environ.get(name)
    if value:
        return value
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def pkce_pair():
    verifier = secrets.token_urlsafe(48)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
def main():
    client_id = read_env("X_CLIENT_ID")
    client_secret = read_env("X_CLIENT_SECRET")
    redirect_uri = read_env("X_REDIRECT_URI") or "http://localhost:8000/api/v1/x/callback/"

    missing = [
        n
        for n, v in (("X_CLIENT_ID", client_id), ("X_CLIENT_SECRET", client_secret))
        if not v
    ]
    if missing:
        print(f"MISSING in backend/.env: {', '.join(missing)}")
        print("Add them, then run this again.")
        return 1

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    url = AUTHORIZE_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "tweet.read users.read",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    print("\nSTEP 1 - your browser will open X's authorize page.")
    print("        Approve access. You will then see an error page.")
    print("        THAT ERROR IS EXPECTED. Ignore it and continue.\n")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        print("Could not open a browser automatically. Open this URL yourself:\n")
        print(url)
        print()

    print("STEP 2 - copy the ENTIRE URL from the address bar and paste it here.")
    try:
        redirected = input("\npasted URL> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    params = parse_qs(urlparse(redirected).query)
    if "error" in params:
        print(f"\nX returned an error: {params['error'][0]}")
        print("Common causes: redirect_uri mismatch, or the app is not set to Read.")
        return 1
    if params.get("state", [""])[0] != state:
        print("\nState mismatch -- refusing. You may have pasted a stale URL.")
        return 1
    code = params.get("code", [""])[0]
    if not code:
        print("\nNo authorization code found in that URL.")
        return 1

    print("\nSTEP 3 - exchanging the code for a token...")
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if not response.ok:
        print(f"Token exchange FAILED (HTTP {response.status_code}):")
        print(response.text[:400])
        return 1

    token = response.json()["access_token"]
    print("        Token received.\n")
    headers = {"Authorization": f"Bearer {token}"}

    print("STEP 4 - who am I?")
    me = requests.get(
        f"{API}/users/me?user.fields=name,username,profile_image_url",
        headers=headers,
        timeout=30,
    )
    if not me.ok:
        print(f"        users/me FAILED (HTTP {me.status_code}): {me.text[:300]}")
        return 1
    user = me.json()["data"]
    print(f"        @{user['username']}  (id {user['id']})\n")

    print("STEP 5 - can I read the timeline? (discovery depends on this)")
    timeline = requests.get(
        f"{API}/users/{user['id']}/timelines/reverse_chronological",
        headers=headers,
        params={
            "max_results": 5,
            "exclude": "retweets,replies",
            "tweet.fields": "created_at,text,referenced_tweets,public_metrics",
        },
        timeout=30,
    )
    if not timeline.ok:
        print(f"        timeline FAILED (HTTP {timeline.status_code}): {timeline.text[:300]}")
        print("        A 403 here usually means the app lacks timeline access yet.")
        return 1

    posts = timeline.json().get("data") or []
    print(f"        {len(posts)} post(s) returned\n")

    if posts:
        print("STEP 6 - does referenced_tweets exist? (Stage 1's originality gate needs it)")
        print(f"        present in at least one post: {any('referenced_tweets' in p for p in posts)}")
        for post in posts[:5]:
            refs = post.get("referenced_tweets")
            kinds = ", ".join(r.get("type", "?") for r in refs) if refs else "-"
            text = (post.get("text") or "")[:45].replace("\n", " ")
            print(f"          id={post['id']:<20} refs={kinds:<10} {text!r}")
        print("\n        normalize_post() expects referenced_tweets[].type to be")
        print("        'reposted' or 'quoted'. If every row shows '-', including for")
        print("        posts you reposted, the originality gate needs revisiting.")

    print("\nDone. Paste the whole output here -- it contains no tokens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
