import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import config
from .curator import CuratedDigest

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def _env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_email(digest: CuratedDigest) -> str:
    html = _env().get_template("email.html").render(
        digest=digest,
        newsletter_name=config.newsletter_name,
    )
    log.debug(f"rendered html email ({len(html):,} chars)")
    return html


def render_plain_text(digest: CuratedDigest) -> str:
    sep = "─" * 60
    lines = [
        f"⚡ {config.newsletter_name} — {digest.date_label()}",
        digest.headline,
        sep, "",
        digest.intro, "",
        "TOP STORIES", "=" * 60,
    ]

    for i, story in enumerate(digest.top_stories, 1):
        lines += [
            f"\n{i}. {story.title}",
            f"   {story.source} · {story.category}",
            f"   {story.url}", "",
            f"   {story.summary}", "",
            f"   KEY TAKEAWAY: {story.key_takeaway}",
            sep,
        ]

    if digest.brief_items:
        lines += ["", "ALSO WORTH READING", sep]
        for item in digest.brief_items:
            lines += [f"• {item.title} ({item.source})", f"  {item.blurb}", f"  {item.url}", ""]

    lines += [
        "=" * 60, "EDITOR'S NOTE", "=" * 60,
        digest.closing_note, "",
        sep,
        f"Generated: {digest.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Curated by ML · Written by Claude AI · {config.newsletter_name}",
    ]

    return "\n".join(lines)
