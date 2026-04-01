"""
Vercel serverless function — POST /api/subscribe

Accepts JSON: { "email": "...", "name": "..." }
Writes subscriber to Supabase.

Env vars needed (set in Vercel project settings):
  SUPABASE_URL
  SUPABASE_KEY
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _add_subscriber(email: str, name: str) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("supabase env vars not configured")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/subscribers",
        headers=headers,
        json={"email": email, "name": name or None, "confirmed": True},
        timeout=10,
    )

    # 409 = already subscribed (unique constraint on email)
    if resp.status_code == 409:
        return {"already_subscribed": True}

    resp.raise_for_status()
    return {"ok": True}


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or "{}")
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "invalid JSON"})
            return

        email = (body.get("email") or "").strip().lower()
        name = (body.get("name") or "").strip()[:100]

        if not email or not _valid_email(email):
            self._respond(400, {"error": "Please provide a valid email address."})
            return

        try:
            result = _add_subscriber(email, name)

            if result.get("already_subscribed"):
                self._respond(200, {"message": "You're already subscribed!"})
            else:
                self._respond(201, {"message": "Subscribed!"})

        except RuntimeError as e:
            # config issue — don't leak details to client
            self._respond(503, {"error": "Service temporarily unavailable."})

        except httpx.HTTPStatusError as e:
            self._respond(502, {"error": "Could not save subscription. Try again."})

        except Exception:
            self._respond(500, {"error": "Something went wrong. Please try again."})

    def do_OPTIONS(self):
        # allow CORS preflight
        self._respond(204, {})

    def _respond(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # suppress default request logging
