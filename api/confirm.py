"""
Vercel serverless function — GET /api/confirm?token=<uuid>

Marks a subscriber as confirmed in Supabase.
Redirects to a success page on the landing site.

Env vars needed:
  SUPABASE_URL
  SUPABASE_KEY
  SITE_URL
"""

import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SITE_URL     = os.environ.get("SITE_URL", "https://synapse-daily.vercel.app")


def _confirm_subscriber(token: str) -> bool:
    """Set confirmed=True for the subscriber matching the token. Returns True on success."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=headers,
        params={"confirm_token": f"eq.{token}", "confirmed": "eq.false"},
        json={"confirmed": True, "confirm_token": None},
        timeout=10,
    )

    # 204 = success, 0 rows updated means token invalid/already confirmed
    return resp.status_code in (200, 204)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed  = urlparse(self.path)
        params  = parse_qs(parsed.query)
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
        except Exception:
            self._redirect(f"{SITE_URL}?confirmed=error")

    def _redirect(self, url: str):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def log_message(self, *args):
        pass
