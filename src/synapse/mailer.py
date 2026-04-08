import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from .config import config
from .curator import CuratedDigest
from .renderer import render_email, render_plain_text

log = logging.getLogger(__name__)


def _make_message(digest: CuratedDigest, to: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[{config.newsletter_name}] {digest.headline}"
    msg["From"] = f"{config.newsletter_name} <{config.gmail_address}>"
    msg["To"] = to

    msg.attach(MIMEText(render_plain_text(digest), "plain", "utf-8"))
    msg.attach(MIMEText(render_email(digest), "html", "utf-8"))
    return msg


def get_subscribers() -> List[str]:
    """Pull confirmed subscriber emails from Supabase if configured, else fall back to env var."""
    if config.supabase_url and config.supabase_key:
        try:
            import httpx
            resp = httpx.get(
                f"{config.supabase_url}/rest/v1/subscribers",
                headers={
                    "apikey": config.supabase_key,
                    "Authorization": f"Bearer {config.supabase_key}",
                },
                params={"select": "email", "confirmed": "eq.true"},
                timeout=10,
            )
            resp.raise_for_status()
            supabase_emails = [row["email"] for row in resp.json()]
            if supabase_emails:
                return supabase_emails
            log.warning(
                "supabase returned 0 confirmed subscribers — "
                "users may not have clicked the confirmation link; "
                "falling back to RECIPIENT_EMAILS env var"
            )
        except Exception as e:
            log.warning(f"supabase fetch failed, falling back to env: {e}")

    if not config.recipient_emails:
        log.error(
            "no recipients found — set RECIPIENT_EMAILS env var or add confirmed subscribers in Supabase"
        )
    return config.recipient_emails


def send_newsletter(digest: CuratedDigest) -> dict:
    result = {"sent": [], "failed": [], "dry_run": config.dry_run}

    recipients = get_subscribers()

    if not recipients:
        log.warning("no recipients — nothing to send")
        return result

    if config.dry_run:
        log.info(f"dry run — would send to {len(recipients)} recipients")
        for r in recipients:
            log.info(f"  → {r}")
        result["sent"] = list(recipients)
        return result

    log.info(f"connecting to gmail smtp as {config.gmail_address}...")

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config.gmail_address, config.gmail_app_password)

            for addr in recipients:
                try:
                    msg = _make_message(digest, addr)
                    server.sendmail(config.gmail_address, [addr], msg.as_string())
                    log.info(f"sent → {addr}")
                    result["sent"].append(addr)
                except smtplib.SMTPException as e:
                    log.error(f"failed → {addr}: {e}")
                    result["failed"].append((addr, str(e)))

    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "gmail auth failed — make sure GMAIL_APP_PASSWORD is an App Password, "
            "not your regular password (https://myaccount.google.com/apppasswords)"
        )

    log.info(f"done: {len(result['sent'])} sent, {len(result['failed'])} failed")
    return result
