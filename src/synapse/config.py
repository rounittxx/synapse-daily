import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    groq_api_key: str = field(default_factory=lambda: os.environ["GROQ_API_KEY"])

    gmail_address: str = field(default_factory=lambda: os.environ["GMAIL_ADDRESS"])
    gmail_app_password: str = field(default_factory=lambda: os.environ["GMAIL_APP_PASSWORD"])

    # comma-sep list in the env var, split it out here
    recipient_emails: List[str] = field(
        default_factory=lambda: [
            e.strip() for e in os.getenv("RECIPIENT_EMAILS", "").split(",") if e.strip()
        ]
    )

    newsletter_name: str = field(default_factory=lambda: os.getenv("NEWSLETTER_NAME", "Synapse Daily"))

    max_articles: int = field(default_factory=lambda: int(os.getenv("MAX_ARTICLES", "15")))
    top_stories: int = field(default_factory=lambda: int(os.getenv("TOP_STORIES", "5")))
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true"
    )

    # groq free tier: 14,400 req/day, 30 RPM, ultra-fast inference
    groq_model: str = "llama-3.3-70b-versatile"

    # supabase for subscriber storage (used by the web app)
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))

    # feeds ordered roughly by signal quality
    rss_feeds: List[dict] = field(default_factory=lambda: [
        {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "Research & Open Source"},
        {"name": "Papers With Code", "url": "https://paperswithcode.com/latest.rss", "category": "Research"},
        {"name": "The Batch", "url": "https://www.deeplearning.ai/the-batch/feed/", "category": "Industry Insights"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "Industry News"},
        {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "category": "Analysis"},
        {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "category": "Research"},
        {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "Industry News"},
        {"name": "arXiv cs.LG", "url": "http://export.arxiv.org/rss/cs.LG", "category": "Academic Papers"},
        {"name": "The Gradient", "url": "https://thegradient.pub/rss/", "category": "Analysis"},
        {"name": "Towards Data Science", "url": "https://towardsdatascience.com/feed", "category": "Tutorials"},
    ])


config = Config()
