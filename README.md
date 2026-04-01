# ⚡ Synapse Daily

> A production-ready AI & ML newsletter pipeline that fetches, ranks, summarises, and emails a curated daily digest — fully automated via GitHub Actions.

---

## How It Works

```
RSS Feeds (10 sources)
       ↓
  collector.py      — Fetches & normalises articles
       ↓
  ml_ranker.py      — ML relevance scoring + deduplication
       ↓             (sentence-transformers / all-MiniLM-L6-v2)
  curator.py        — Claude AI writes the newsletter
       ↓             (structured JSON output)
  renderer.py       — Renders HTML + plain-text email
       ↓             (Jinja2 + inline CSS)
  mailer.py         — Sends via Gmail SMTP
       ↓
📧 Your inbox
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/your-username/synapse-daily.git
cd synapse-daily
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your [Anthropic API key](https://console.anthropic.com/) |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-char [Gmail App Password](https://myaccount.google.com/apppasswords) — **not** your regular password |
| `RECIPIENT_EMAILS` | Comma-separated list of recipient emails |
| `DRY_RUN` | Set `true` to skip sending (just renders the email) |

### 3. Run locally

```bash
cd src
# Full pipeline
python -m synapse.main

# Dry run (no email sent)
DRY_RUN=true python -m synapse.main

# Save HTML preview to file
python -m synapse.main --preview
# → opens synapse_preview.html in your browser
```

### 4. Run tests

```bash
cd src
pytest ../tests/ -v
```

---

## Deployment — GitHub Actions

The newsletter runs automatically every day at **07:00 UTC** via GitHub Actions.

### Setup (one-time)

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `ANTHROPIC_API_KEY`
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `RECIPIENT_EMAILS`
3. That's it. The workflow in `.github/workflows/daily_newsletter.yml` handles the rest.

### Manual trigger

Go to **Actions → Synapse Daily Newsletter → Run workflow** and optionally set:
- **Dry run** — render but don't send
- **Preview** — download the rendered HTML as an artifact

---

## Project Structure

```
synapse-daily/
├── src/
│   └── synapse/
│       ├── __init__.py
│       ├── config.py        ← All settings & RSS feed list
│       ├── collector.py     ← RSS fetching & normalisation
│       ├── ml_ranker.py     ← ML relevance scoring & dedup
│       ├── curator.py       ← Claude AI curation
│       ├── renderer.py      ← HTML/plain-text rendering
│       └── main.py          ← Pipeline orchestration
├── templates/
│   └── email.html           ← Jinja2 HTML email template
├── tests/
│   └── test_pipeline.py     ← Unit tests (pytest)
├── .github/
│   └── workflows/
│       └── daily_newsletter.yml  ← GitHub Actions cron workflow
├── requirements.txt
├── .env.example
└── README.md
```

---

## Customisation

### Add or change RSS feeds

Edit the `rss_feeds` list in `src/synapse/config.py`.

### Change the send time

Edit the `cron` expression in `.github/workflows/daily_newsletter.yml`:
```yaml
- cron: "0 7 * * *"   # 07:00 UTC daily
```

### Adjust article count

Set `MAX_ARTICLES` (total fetched) and `TOP_STORIES` (featured) in your `.env` or as GitHub Secrets.

### Change the ML model

In `src/synapse/ml_ranker.py`, replace `"all-MiniLM-L6-v2"` with any [sentence-transformers compatible model](https://huggingface.co/sentence-transformers).

---

## Gmail App Password Setup

Regular Gmail passwords won't work. You need an **App Password**:

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select **Mail** and your device
3. Copy the 16-character password generated
4. Use this as `GMAIL_APP_PASSWORD`

> **Note:** 2-Step Verification must be enabled on your Google Account.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| RSS parsing | feedparser |
| HTML parsing | BeautifulSoup4 + lxml |
| ML ranking | sentence-transformers (all-MiniLM-L6-v2) |
| AI curation | Anthropic Claude API |
| Templating | Jinja2 |
| Email sending | Python smtplib (Gmail SMTP) |
| Scheduling | GitHub Actions (cron) |
| Testing | pytest |
