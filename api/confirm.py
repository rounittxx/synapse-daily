"""
Vercel serverless function — GET /api/confirm?token=<uuid>

Marks a subscriber as confirmed in Supabase.
Redirects to a success page on the landing site.

Env vars needed:
  SUPABASE_URL
  SUPABASE_KEY
  SITE_URL
"""

import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SITE_URL     = os.environ.get("SITE_URL", "https://synapse-daily.vercel.app")


def _confirm_subscriber(token: str) -> bool:
    """Set confirmed=True for the subscriber matching the token. Returns True on success."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    qs = urllib.parse.urlencode({
        "confirm_token": f"eq.{token}",
        "confirmed": "eq.false",
    })
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/subscribers?{qs}"
    payload = json.dumps({"confirmed": True, "confirm_token": None}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode() in (200, 204)
    except urllib.error.HTTPError as e:
        print(
            f"[error] supabase HTTP {e.code} when confirming token: {e.read()[:200]!r}",
            file=sys.stderr,
        )
        return False


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed  = urllib.parse.urlparse(self.path)
        params  = urllib.parse.parse_qs(parsed.query)
        token   = (params.get("token") or [""])[0].strip()

        if not token:
            self._redirect(f"{SITE_URL}?confirmed=error")
            return

        try:
            success = _confirm_subscriber(token)
            if success:
                self._redirect(f"{SITE_URL}?confirmed=true")
            else:
                self._redirect(f"{SITE_URL}?confirmed=already")
        except Exception as e:
            print(f"[error] Unhandled {type(e).__name__} in /api/confirm: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self._redirect(f"{SITE_URL}?confirmed=error")

    def _redirect(self, url: str):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def log_message(self, *args):
        pass
