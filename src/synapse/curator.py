import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

import anthropic

from .collector import Article
from .config import config

log = logging.getLogger(__name__)


@dataclass
class StorySummary:
    title: str
    url: str
    source: str
    category: str
    summary: str
    key_takeaway: str


@dataclass
class BriefItem:
    title: str
    url: str
    source: str
    blurb: str


@dataclass
class CuratedDigest:
    headline: str
    intro: str
    top_stories: List[StorySummary]
    brief_items: List[BriefItem]
    closing_note: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def date_label(self):
        return self.generated_at.strftime("%A, %B %-d, %Y")


def _build_prompt(articles: List[Article], top_n: int) -> str:
    articles_json = json.dumps([a.to_dict() for a in articles], indent=2, default=str)

    return f"""You are the editor of Synapse Daily, a daily AI & ML newsletter for engineers and researchers.

You've been given {len(articles)} pre-ranked articles (rank 1 = most relevant + recent). Turn them into a clean daily digest.

Articles:
```json
{articles_json}
```

Return ONLY valid JSON with this structure (no markdown, no explanation):

{{
  "headline": "<specific subject line — name real models/companies/breakthroughs>",
  "intro": "<2-3 sentence editorial intro, written like a smart analyst not a PR person>",
  "top_stories": [
    {{
      "title": "<title>",
      "url": "<url>",
      "source": "<source>",
      "category": "<category>",
      "summary": "<3-4 sentences, specific and technical, explain why it matters>",
      "key_takeaway": "<one sentence, the thing a busy reader must remember>"
    }}
    // {top_n} items
  ],
  "brief_items": [
    {{
      "title": "<title>",
      "url": "<url>",
      "source": "<source>",
      "blurb": "<1-2 sentences, quick signal>"
    }}
    // remaining articles
  ],
  "closing_note": "<2-3 sentences, a forward-looking observation from today's stories>"
}}

Guidelines: be specific, cite numbers/benchmarks, don't hype. Today: {datetime.now(timezone.utc).strftime('%B %-d, %Y')}"""


def curate(articles: List[Article]) -> CuratedDigest:
    if not articles:
        raise ValueError("no articles to curate")

    top_n = min(config.top_stories, len(articles))
    prompt = _build_prompt(articles, top_n)

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    log.info(f"calling claude with {len(articles)} articles...")

    msg = client.messages.create(
        model=config.claude_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()

    # claude sometimes wraps in ```json ``` even when told not to
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"claude returned bad JSON: {e}")
        raise

    top_stories = [
        StorySummary(
            title=s["title"], url=s["url"], source=s["source"],
            category=s.get("category", ""), summary=s["summary"],
            key_takeaway=s["key_takeaway"],
        )
        for s in data.get("top_stories", [])
    ]

    brief_items = [
        BriefItem(title=b["title"], url=b["url"], source=b["source"], blurb=b["blurb"])
        for b in data.get("brief_items", [])
    ]

    digest = CuratedDigest(
        headline=data["headline"],
        intro=data["intro"],
        top_stories=top_stories,
        brief_items=brief_items,
        closing_note=data["closing_note"],
    )

    log.info(f"digest ready: {digest.headline}")
    return digest
