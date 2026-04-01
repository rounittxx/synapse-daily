"""
test_pipeline.py — Unit tests for the Synapse Daily pipeline.

Run with:  pytest tests/ -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from synapse.collector import Article, _clean_html, _truncate
from synapse.curator import BriefItem, CuratedDigest, StorySummary
from synapse.renderer import render_email, render_plain_text


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

def make_article(
    title="Test Article",
    url="https://example.com/test",
    summary="A test summary about AI.",
    source="Test Source",
    category="Research",
    days_old=0,
) -> Article:
    published = datetime(2026, 4, 1, 7, 0, 0, tzinfo=timezone.utc)
    return Article(
        title=title,
        url=url,
        summary=summary,
        published=published,
        source=source,
        category=category,
    )


def make_digest() -> CuratedDigest:
    return CuratedDigest(
        headline="GPT-5 Drops, DeepMind Breaks Protein Folding Record",
        intro="Today's digest covers a landmark week in AI.",
        top_stories=[
            StorySummary(
                title="GPT-5 Released with 10x Context",
                url="https://openai.com/gpt5",
                source="OpenAI Blog",
                category="Industry News",
                summary="OpenAI released GPT-5 today with 1M token context.",
                key_takeaway="Context length is no longer a bottleneck.",
            ),
        ],
        brief_items=[
            BriefItem(
                title="Google Launches Gemini Ultra 2",
                url="https://google.com/gemini",
                source="Google Blog",
                blurb="Gemini Ultra 2 scores SOTA on MMLU.",
            ),
        ],
        closing_note="The pace of model releases is accelerating.",
        generated_at=datetime(2026, 4, 1, 7, 0, 0, tzinfo=timezone.utc),
    )


# -------------------------------------------------------------------
# collector tests
# -------------------------------------------------------------------

class TestCollectorHelpers:
    def test_clean_html_strips_tags(self):
        result = _clean_html("<p>Hello <b>world</b></p>")
        assert result == "Hello world"

    def test_clean_html_handles_empty(self):
        assert _clean_html("") == ""
        assert _clean_html(None) == ""

    def test_truncate_short_string_unchanged(self):
        text = "Short text"
        assert _truncate(text, max_chars=100) == "Short text"

    def test_truncate_long_string_truncated(self):
        text = " ".join(["word"] * 200)
        result = _truncate(text, max_chars=50)
        assert len(result) <= 54  # max_chars + ellipsis
        assert result.endswith("…")

    def test_article_to_dict(self):
        a = make_article()
        d = a.to_dict()
        assert d["title"] == "Test Article"
        assert d["url"] == "https://example.com/test"
        assert "published" in d


# -------------------------------------------------------------------
# ml_ranker tests
# -------------------------------------------------------------------

class TestMLRanker:
    def test_rank_articles_returns_subset(self):
        """rank_articles should return at most top_n articles."""
        from synapse.ml_ranker import rank_articles

        articles = [
            make_article(
                title=f"Deep learning breakthrough #{i} in neural networks AI model",
                url=f"https://example.com/{i}",
                summary=f"Researchers discovered new AI technique {i}.",
            )
            for i in range(10)
        ]
        ranked = rank_articles(articles, top_n=5)
        assert len(ranked) <= 5

    def test_rank_articles_empty_input(self):
        from synapse.ml_ranker import rank_articles
        result = rank_articles([], top_n=5)
        assert result == []

    def test_recency_score_recent_is_higher(self):
        from synapse.ml_ranker import _recency_score
        recent = datetime.now(timezone.utc)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert _recency_score(recent) > _recency_score(old)

    def test_recency_score_range(self):
        from synapse.ml_ranker import _recency_score
        score = _recency_score(datetime.now(timezone.utc))
        assert 0.0 <= score <= 1.0


# -------------------------------------------------------------------
# curator tests (mocked)
# -------------------------------------------------------------------

class TestCurator:
    def test_curate_raises_on_empty_articles(self):
        from synapse.curator import curate
        with pytest.raises(ValueError, match="empty"):
            curate([])

    def test_curate_parses_valid_response(self):
        from synapse.curator import curate

        mock_response_data = {
            "headline": "AI Changes Everything",
            "intro": "A pivotal day in AI.",
            "top_stories": [
                {
                    "title": "Test Article",
                    "url": "https://example.com",
                    "source": "Test",
                    "category": "Research",
                    "summary": "A great summary.",
                    "key_takeaway": "Key insight here.",
                }
            ],
            "brief_items": [],
            "closing_note": "The future is bright.",
        }

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(mock_response_data))]

        with patch("anthropic.Anthropic") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_message

            articles = [make_article() for _ in range(3)]
            digest = curate(articles)

        assert digest.headline == "AI Changes Everything"
        assert len(digest.top_stories) == 1
        assert digest.top_stories[0].title == "Test Article"


# -------------------------------------------------------------------
# renderer tests
# -------------------------------------------------------------------

class TestRenderer:
    def test_render_email_returns_html(self):
        digest = make_digest()
        html = render_email(digest)
        assert "<!DOCTYPE html>" in html
        assert "GPT-5 Released" in html
        assert "Synapse Daily" in html

    def test_render_email_contains_links(self):
        digest = make_digest()
        html = render_email(digest)
        assert "https://openai.com/gpt5" in html

    def test_render_plain_text(self):
        digest = make_digest()
        text = render_plain_text(digest)
        assert "GPT-5 Released" in text
        assert "TOP STORIES" in text
        assert "EDITOR'S NOTE" in text
        assert "https://openai.com/gpt5" in text

    def test_render_email_escapes_html(self):
        """Make sure Jinja2 autoescape is active."""
        digest = make_digest()
        digest.headline = "Test <script>alert('xss')</script>"
        html = render_email(digest)
        assert "<script>" not in html


# -------------------------------------------------------------------
# mailer tests (mocked SMTP)
# -------------------------------------------------------------------

class TestMailer:
    def test_dry_run_skips_smtp(self):
        from synapse.mailer import send_newsletter

        digest = make_digest()
        with patch("synapse.mailer.config") as mock_cfg:
            mock_cfg.dry_run = True
            mock_cfg.recipient_emails = ["test@example.com"]
            mock_cfg.gmail_address = "sender@gmail.com"
            mock_cfg.gmail_app_password = "test_password"
            mock_cfg.newsletter_name = "Synapse Daily"

            with patch("smtplib.SMTP") as mock_smtp:
                result = send_newsletter(digest)
                mock_smtp.assert_not_called()

        assert result["dry_run"] is True

    def test_no_recipients_returns_empty(self):
        from synapse.mailer import send_newsletter

        digest = make_digest()
        with patch("synapse.mailer.config") as mock_cfg:
            mock_cfg.dry_run = False
            mock_cfg.recipient_emails = []
            mock_cfg.newsletter_name = "Synapse Daily"

            result = send_newsletter(digest)

        assert result["sent"] == []
        assert result["failed"] == []
