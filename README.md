# Synapse Daily

A production-ready AI/ML newsletter pipeline that fetches, ranks, summarises, and emails a curated daily digest — fully automated via GitHub Actions.

---

## How It Works

```
RSS Feeds (10 sources)
       |
  collector.py      — Fetches and normalises articles
       |
  ml_ranker.py      — ML relevance scoring + deduplication
       |               (sentence-transformers / all-MiniLM-L6-v2)
  curator.py        — LLM writes the newsletter
       |               (Groq / Llama 3.3 70B, structured JSON output)
  renderer.py       — Renders HTML + plain-text email
       |               (Jinja2 + inline CSS)
  mailer.py         — Sends via Gmail SMTP to confirmed subscribers
       |
  Your inbox
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/rounittxx/synapse-daily.git
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
| `GROQ_API_KEY` | Your Groq API key — free at console.groq.com |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-char Gmail App Password (see section below) |
| `RECIPIENT_EMAILS` | Comma-separated fallback recipients |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon/service key |
| `DRY_RUN` | Set `true` to render without sending |

### 3. Run locally

```bash
cd src

# Full pipeline
python -m synapse.main

# Dry run (no email sent)
DRY_RUN=true python -m synapse.main

# Save HTML preview to file
python -m synapse.main --preview
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
2. Go to **Settings -> Secrets and variables -> Actions -> New repository secret** and add:
   - `GROQ_API_KEY`
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `RECIPIENT_EMAILS`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
3. The workflow in `.github/workflows/daily_newsletter.yml` handles the rest.

### Manual trigger

Go to **Actions -> Synapse Daily Newsletter -> Run workflow** and optionally set:
- **Dry run** — render but do not send
- **Preview** — download the rendered HTML as an artifact

---

## Subscription Confirmation Flow

When a visitor subscribes via the landing page:

1. Their email is stored in Supabase with `confirmed = false` and a unique token.
2. A confirmation email is sent to their inbox with a verify link.
3. Clicking the link hits `/api/confirm?token=...` which sets `confirmed = true`.
4. Only confirmed subscribers receive the daily newsletter.

**Required Supabase table columns:**

| Column | Type | Notes |
|---|---|---|
| `email` | text | unique |
| `name` | text | nullable |
| `confirmed` | boolean | default false |
| `confirm_token` | text | nullable, cleared after confirmation |

---

## Project Structure

```
synapse-daily/
|-- src/
|   |-- synapse/
|       |-- __init__.py
|       |-- config.py        <- All settings and RSS feed list
|       |-- collector.py     <- RSS fetching and normalisation
|       |-- ml_ranker.py     <- ML relevance scoring and dedup
|       |-- curator.py       <- LLM curation (Groq / Llama 3.3 70B)
|       |-- renderer.py      <- HTML/plain-text rendering
|       |-- main.py          <- Pipeline orchestration
|-- templates/
|   |-- email.html           <- Jinja2 HTML email template (compact)
|-- api/
|   |-- subscribe.py         <- POST /api/subscribe (Vercel serverless)
|   |-- confirm.py           <- GET /api/confirm?token=... (Vercel serverless)
|-- web/
|   |-- index.html           <- Landing page
|-- tests/
|   |-- test_pipeline.py     <- Unit tests (pytest)
|-- .github/
|   |-- workflows/
|       |-- daily_newsletter.yml  <- GitHub Actions cron workflow
|-- requirements.txt
|-- vercel.json
|-- .env.example
|-- README.md
```

---

## Gmail App Password Setup

Regular Gmail passwords do not work for SMTP. You need an App Password:

1. Go to myaccount.google.com/apppasswords
2. Select Mail and your device
3. Copy the 16-character password generated
4. Use this as `GMAIL_APP_PASSWORD`

Note: 2-Step Verification must be enabled on your Google Account.

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

In `src/synapse/ml_ranker.py`, replace `"all-MiniLM-L6-v2"` with any sentence-transformers compatible model from huggingface.co/sentence-transformers.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| RSS parsing | feedparser |
| HTML parsing | BeautifulSoup4 + lxml |
| ML ranking | sentence-transformers (all-MiniLM-L6-v2) |
| LLM curation | Groq API / Llama 3.3 70B |
| Templating | Jinja2 |
| Email sending | smtplib (Gmail SMTP) |
| Subscriber storage | Supabase (PostgreSQL) |
| Scheduling | GitHub Actions (cron) |
| Hosting | Vercel (serverless functions + static) |
| Testing | pytest |
