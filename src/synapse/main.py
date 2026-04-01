"""
Synapse Daily — main pipeline runner

Usage:
    python -m synapse.main              # full run
    DRY_RUN=true python -m synapse.main # skip sending
    python -m synapse.main --preview    # save HTML to file for browser preview
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

from .collector import collect_articles
from .config import config
from .curator import curate
from .mailer import send_newsletter
from .ml_ranker import rank_articles
from .renderer import render_email


def run(preview=False):
    t0 = time.perf_counter()

    log.info("=" * 50)
    log.info(f"Synapse Daily — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 50)

    # 1. collect
    log.info("[1/5] collecting from RSS feeds...")
    articles = collect_articles()
    if not articles:
        log.error("no articles collected, bailing")
        sys.exit(1)

    # 2. rank with ML model
    log.info("[2/5] running ML ranker...")
    ranked = rank_articles(articles, top_n=config.max_articles)
    if not ranked:
        log.error("ML ranker filtered everything out, bailing")
        sys.exit(1)

    # 3. curate with claude
    log.info("[3/5] curating with claude...")
    digest = curate(ranked)

    # 4. render
    log.info("[4/5] rendering email...")
    html = render_email(digest)

    if preview:
        out = Path("synapse_preview.html")
        out.write_text(html, encoding="utf-8")
        log.info(f"preview saved → {out.resolve()}")

    # 5. send
    log.info("[5/5] sending newsletter...")
    result = send_newsletter(digest)

    elapsed = time.perf_counter() - t0
    log.info("=" * 50)
    log.info(f"done in {elapsed:.1f}s — sent: {len(result['sent'])}, failed: {len(result['failed'])}")

    if result["failed"]:
        for addr, reason in result["failed"]:
            log.error(f"  failed → {addr}: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="save HTML preview to file")
    args = parser.parse_args()
    run(preview=args.preview)
