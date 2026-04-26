"""
Vercel serverless function — POST /api/subscribe

Accepts JSON: { "email": "...", "name": "..." }
Writes subscriber to Supabase with confirmed=False,
then sends a confirmation email via Gmail SMTP.

Env vars needed (set in Vercel project settings):
  SUPABASE_URL
  SUPABASE_KEY
  GMAIL_ADDRESS
  GMAIL_APP_PASSWORD
  SITE_URL          — e.g. https://synapse-daily.vercel.app
"""

import json
import os
import re
import smtplib
import sys
import traceback
import urllib.error
import urllib.request
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY      = os.environ.get("SUPABASE_KEY", "")
GMAIL_ADDRESS     = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD= os.environ.get("GMAIL_APP_PASSWORD", "")
SITE_URL          = os.environ.get("SITE_URL", "https://synapse-daily.vercel.app")


def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


class _SupabaseError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"supabase HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def _supabase_post(path: str, payload: dict) -> int:
    """POST JSON to Supabase via stdlib urllib. Returns HTTP status code."""
    url = f"{SUPABASE_URL.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        # 409 (duplicate) is expected — surface it without raising
        return e.code


def _add_subscriber(email: str, name: str) -> dict:
    """Insert subscriber with confirmed=False and a unique token. Returns token."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("supabase env vars not configured")

    token = str(uuid.uuid4())

    status = _supabase_post(
        "/rest/v1/subscribers",
        {
            "email": email,
            "name": name or None,
            "confirmed": False,
            "confirm_token": token,
        },
    )

    if status == 409:
        return {"already_subscribed": True}

    if status not in (200, 201, 204):
        raise _SupabaseError(status, "")

    return {"ok": True, "token": token}


def _send_confirmation_email(to_email: str, name: str, token: str):
    """Send a confirmation email with a clickable verify link."""
    confirm_url = f"{SITE_URL}/api/confirm?token={token}"
    display_name = name or to_email.split("@")[0]

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,sans-serif;">
  <table width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f4f7;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="560" cellspacing="0" cellpadding="0" border="0"
        style="background:#ffffff;border-radius:12px;overflow:hidden;max-width:560px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:#6c63ff;padding:28px 36px;text-align:center;">
            <p style="margin:0;font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.3px;">
              ⚡ Synapse Daily
            </p>
            <p style="margin:6px 0 0;font-size:13px;color:rgba(255,255,255,0.75);">
              Your daily AI/ML intelligence brief
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 36px 28px;">
            <p style="margin:0 0 12px;font-size:16px;color:#1f2937;font-weight:600;">
              Hi {display_name},
            </p>
            <p style="margin:0 0 20px;font-size:15px;color:#4b5563;line-height:1.7;">
              Thanks for subscribing to <strong>Synapse Daily</strong>! You're one step away from
              receiving your daily ML-curated AI/ML newsletter.
            </p>
            <p style="margin:0 0 28px;font-size:15px;color:#4b5563;line-height:1.7;">
              Please confirm your email address by clicking the button below:
            </p>

            <!-- Button -->
            <table cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td style="border-radius:8px;background:#6c63ff;">
                  <a href="{confirm_url}"
                    style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;
                           color:#ffffff;text-decoration:none;letter-spacing:0.3px;">
                    ✓ Confirm My Subscription
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:24px 0 0;font-size:13px;color:#9ca3af;line-height:1.6;">
              If the button doesn't work, copy and paste this link into your browser:<br/>
              <a href="{confirm_url}" style="color:#6c63ff;word-break:break-all;">{confirm_url}</a>
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 36px 28px;border-top:1px solid #f3f4f6;text-align:center;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
              If you didn't subscribe to Synapse Daily, you can safely ignore this email.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    plain_body = (
        f"Hi {display_name},\n\n"
        f"Thanks for subscribing to Synapse Daily!\n\n"
        f"Please confirm your email by visiting:\n{confirm_url}\n\n"
        f"If you didn't subscribe, ignore this email.\n\n"
        f"— Synapse Daily"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Confirm your Synapse Daily subscription ✓"
    msg["From"]    = f"Synapse Daily <{GMAIL_ADDRESS}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_email], msg.as_string())


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or "{}")
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "invalid JSON"})
            return

        email = (body.get("email") or "").strip().lower()
        name  = (body.get("name")  or "").strip()[:100]

        if not email or not _valid_email(email):
            self._respond(400, {"error": "Please provide a valid email address."})
            return

        try:
            result = _add_subscriber(email, name)

            if result.get("already_subscribed"):
                self._respond(200, {"message": "You're already subscribed!"})
                return

            # Send confirmation email
            email_sent = False
            if GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
                try:
                    _send_confirmation_email(email, name, result["token"])
                    email_sent = True
                except Exception as mail_err:
                    print(
                        f"[error] confirmation email failed for {email}: {type(mail_err).__name__}: {mail_err}",
                        file=sys.stderr,
                    )
                    traceback.print_exc(file=sys.stderr)
            else:
                print(
                    "[error] GMAIL_ADDRESS or GMAIL_APP_PASSWORD env var not set — cannot send confirmation email",
                    file=sys.stderr,
                )

            if email_sent:
                self._respond(201, {
                    "message": "Almost there! Check your inbox to confirm your subscription."
                })
            else:
                self._respond(201, {
                    "message": "You're subscribed! However, we couldn't send a confirmation email right now. Please contact support."
                })

        except RuntimeError as e:
            print(f"[error] RuntimeError in /api/subscribe: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self._respond(503, {"error": "Service temporarily unavailable."})
        except _SupabaseError as e:
            print(
                f"[error] SupabaseError in /api/subscribe: status={e.status} body={e.body!r}",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
            self._respond(502, {"error": "Could not save subscription. Try again."})
        except urllib.error.URLError as e:
            print(f"[error] URLError in /api/subscribe: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self._respond(502, {"error": "Could not save subscription. Try again."})
        except Exception as e:
            print(
                f"[error] Unhandled {type(e).__name__} in /api/subscribe: {e}",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
            self._respond(500, {"error": "Something went wrong. Please try again."})

    def do_OPTIONS(self):
        self.send_response(204)
        self._add_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _add_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, status: int, data: dict):
        body_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, *args):
        pass
