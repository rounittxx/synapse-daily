import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import feedparser
from bs4 import BeautifulSoup

from .config import config

log = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: datetime
    source: str
    category: str

    def to_dict(self):
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published": self.published.isoformat(),
            "source": self.source,
            "category": self.category,
        }


def _parse_date(entry):
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        tup = getattr(entry, attr, None)
        if tup:
            return datetime(*tup[:6], tzinfo=timezone.utc)
    # fallback to raw string
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _strip_html(html):
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


def _truncate(text, limit=500):
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _fetch(feed_cfg):
    articles = []
    name, url, category = feed_cfg["name"], feed_cfg["url"], feed_cfg["category"]

    try:
        log.info(f"fetching: {name}")
        parsed = feedparser.parse(url, agent="SynapseDaily/1.0")

        if parsed.bozo and not parsed.entries:
            log.warning(f"{name}: bozo exception, skipping")
            return articles

        for entry in parsed.entries[:5]:
            title = _strip_html(getattr(entry, "title", "")).strip()
            link = getattr(entry, "link", "") or getattr(entry, "id", "")

            if not title or not link:
                continue

            raw_summary = (
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
                or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
            )
            summary = _truncate(_strip_html(raw_summary))
            published = _parse_date(entry)

            articles.append(Article(
                title=title,
                url=link,
                summary=summary,
                published=published,
                source=name,
                category=category,
            ))

    except Exception as e:
        log.error(f"error fetching {name}: {e}")

    return articles


def collect_articles(feeds=None):
    feeds = feeds or config.rss_feeds
    seen = set()
    results = []

    for feed in feeds:
        for article in _fetch(feed):
            if article.url not in seen:
                seen.add(article.url)
                results.append(article)
        time.sleep(0.3)

    results.sort(key=lambda a: a.published, reverse=True)
    log.info(f"collected {len(results)} articles from {len(feeds)} feeds")
    return results[:config.max_articles]
