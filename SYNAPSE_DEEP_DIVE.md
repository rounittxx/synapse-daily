# Synapse Daily — Complete Project Deep-Dive for AI/ML Interview Prep

---

## TABLE OF CONTENTS

1. [Project Overview & What It Does](#1-project-overview)
2. [System Architecture & Data Flow](#2-system-architecture)
3. [Folder Structure Explained](#3-folder-structure)
4. [Module-by-Module Code Walkthrough](#4-code-walkthrough)
5. [The ML Model — all-MiniLM-L6-v2 (Deep Dive)](#5-ml-model)
6. [The LLM Layer — Groq + Llama 3.3 70B](#6-llm-layer)
7. [All Technologies & Why Each Was Chosen](#7-technologies)
8. [Issues Faced & How They Were Solved](#8-issues)
9. [Interview-Critical ML/AI Concepts Used](#9-interview-concepts)
10. [System Design & Scalability Discussion](#10-system-design)
11. [Potential Interview Questions & Answers](#11-interview-qa)

---

## 1. PROJECT OVERVIEW

Synapse Daily is a **production-ready, fully-automated AI/ML newsletter pipeline** that runs end-to-end without human intervention. Every day at 07:00 UTC, it fetches articles from 10 AI/ML RSS feeds, ranks them using a sentence-transformer ML model, sends the top-ranked articles to an LLM (Llama 3.3 70B via Groq) for editorial curation, renders a professional HTML email, and delivers it via Gmail SMTP.

**In one sentence:** It's an ML-powered content curation pipeline that combines semantic search (embeddings + cosine similarity), LLM-based summarisation, and automated delivery — all orchestrated via CI/CD.

**Why this matters for an AI/ML interview:** This project demonstrates that you can build end-to-end ML systems, not just train models. It shows you understand embeddings, similarity search, LLM prompt engineering, API integration, CI/CD, and production deployment — the full stack that companies actually need.

---

## 2. SYSTEM ARCHITECTURE & DATA FLOW

The pipeline has exactly 5 sequential stages, orchestrated by `main.py`:

```
[Stage 1] collector.py
    │  Fetches 10 RSS feeds using feedparser
    │  Parses dates, strips HTML, deduplicates by URL
    │  Output: List[Article] (up to ~50 raw articles)
    ▼
[Stage 2] ml_ranker.py
    │  Loads all-MiniLM-L6-v2 sentence-transformer model
    │  Embeds all articles into 384-dimensional vectors
    │  Computes cosine similarity against 10 "anchor" AI/ML phrases
    │  Filters by relevance threshold (0.25)
    │  Removes near-duplicates (cosine similarity > 0.92)
    │  Scores = 0.6 * relevance + 0.4 * recency (exponential decay)
    │  Output: List[Article] (top 15, ranked)
    ▼
[Stage 3] curator.py
    │  Builds a structured prompt with all 15 articles as JSON
    │  Sends to Groq API (Llama 3.3 70B)
    │  Parses the structured JSON response
    │  Output: CuratedDigest (headline, intro, 5 top stories with
    │          summaries + key takeaways, brief items, closing note)
    ▼
[Stage 4] renderer.py
    │  Loads Jinja2 HTML template (email.html)
    │  Renders HTML and plain-text versions
    │  Output: HTML string + plain-text string
    ▼
[Stage 5] mailer.py
    │  Fetches subscriber list from Supabase (or env var fallback)
    │  Connects to Gmail SMTP with TLS
    │  Sends MIME multipart email (HTML + plain-text)
    │  Output: {"sent": [...], "failed": [...]}
```

**Key architectural decisions:**

- **Sequential, not parallel:** Each stage depends on the previous one's output. This is intentional — the pipeline is simple, debuggable, and runs in ~15 seconds total.
- **Stateless:** No database, no persistent state between runs. Each run is independent. This makes debugging trivial and eliminates state corruption bugs.
- **Fail-fast:** If any stage produces zero results (no articles, nothing passes relevance filter), the pipeline exits with a non-zero code so GitHub Actions marks it as failed.

---

## 3. FOLDER STRUCTURE

```
synapse-daily/
├── src/
│   └── synapse/                  ← Main Python package
│       ├── __init__.py           ← Makes it a package (empty)
│       ├── main.py               ← Pipeline orchestrator (entry point)
│       ├── config.py             ← Centralised settings via @dataclass
│       ├── collector.py          ← RSS fetching & article normalisation
│       ├── ml_ranker.py          ← ML relevance scoring & deduplication
│       ├── curator.py            ← LLM curation (Groq/Llama API)
│       ├── renderer.py           ← Jinja2 HTML/text email rendering
│       ├── mailer.py             ← Gmail SMTP sending + Supabase subscribers
│       ├── components/           ← (placeholder for future UI components)
│       ├── prompts/              ← (placeholder for prompt templates)
│       └── utils/                ← (placeholder for shared utilities)
│
├── templates/
│   └── email.html                ← Jinja2 HTML email template (360 lines)
│                                   Dark theme, inline CSS, table-based layout
│                                   for maximum email client compatibility
│
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py          ← Unit tests: collector, ranker, curator,
│                                   renderer, mailer (all with mocks)
│
├── .github/
│   └── workflows/
│       └── daily_newsletter.yml  ← GitHub Actions cron workflow
│                                   Runs daily at 07:00 UTC
│                                   Caches ML model between runs (~90MB)
│
├── web/                          ← Landing page (static, served by Vercel)
│   ├── index.html                ← Marketing landing page
│   └── static/
│       ├── css/style.css         ← Landing page styles
│       └── js/subscribe.js       ← Subscribe form handler (fetch API)
│
├── api/
│   └── subscribe.py              ← Vercel serverless function
│                                   POST /api/subscribe → Supabase insert
│
├── requirements.txt              ← Production dependencies (16 packages)
├── pyproject.toml                ← Modern Python project config
├── vercel.json                   ← Vercel deployment routing
├── .env.example                  ← Template for environment variables
├── .gitignore
└── README.md
```

**Why `src/` layout?** The `src/` layout prevents accidental imports of the local package during testing. It's a Python packaging best practice recommended by the PyPA. The `pyproject.toml` sets `where = ["src"]` so `setuptools` knows where to find the package.

**Why templates/ is outside src/?** The Jinja2 template is a deployment artifact, not Python code. Keeping it at the project root makes it accessible regardless of how the package is installed. The renderer calculates the path relative to itself: `Path(__file__).parent.parent.parent / "templates"`.

---

## 4. MODULE-BY-MODULE CODE WALKTHROUGH

### 4.1 main.py — Pipeline Orchestrator

This is the entry point, run as `python -m synapse.main`.

**How it works:**
1. Configures logging (timestamps, level names, stdout)
2. Imports all 5 pipeline stages
3. Runs them sequentially with timing
4. Supports `--preview` flag to save HTML to disk
5. Exits with code 1 if any stage fails or if emails fail to send

**Key design patterns:**
- **`time.perf_counter()`** for high-resolution timing (not `time.time()` which is affected by system clock changes)
- **`sys.exit(1)`** propagates failures to GitHub Actions, which marks the run as failed
- **`argparse`** for CLI arguments — clean, standard, no external deps

**Interview talking point:** "The orchestrator follows the Unix philosophy — each stage does one thing well, and main.py just chains them together. This makes testing trivial because you can test each stage in isolation."

---

### 4.2 config.py — Centralised Configuration

Uses Python's `@dataclass` to define all configuration in one place, with all values pulled from environment variables.

**How it works:**
- `load_dotenv()` loads `.env` file for local development
- Each field uses `field(default_factory=lambda: ...)` so env vars are read at instantiation time, not import time
- A single `config = Config()` singleton is created at module level

**Key fields:**
- `groq_api_key` — required, raises KeyError if missing
- `groq_model` — `"llama-3.3-70b-versatile"` (hardcoded, not from env)
- `rss_feeds` — list of 10 dicts with `name`, `url`, `category`
- `max_articles` — default 15 (how many articles to keep after ML ranking)
- `top_stories` — default 5 (how many get full summaries vs. brief items)
- `dry_run` — boolean, skip email sending when true
- `supabase_url/key` — optional, for subscriber storage

**Why `default_factory` with lambdas?**
If you wrote `groq_api_key: str = os.environ["GROQ_API_KEY"]`, the env var would be read at *class definition time* (when the module is imported), not when the config object is created. Lambdas defer evaluation to instantiation time. This is critical because in testing, you might patch env vars after import.

**Interview talking point:** "I used dataclasses instead of a dict or a JSON config file because dataclasses give you type annotations, default values, and IDE autocomplete — and they're immutable by convention, which prevents accidental mutation of global config."

---

### 4.3 collector.py — RSS Fetching & Normalisation

This module fetches articles from 10 RSS feeds and normalises them into a uniform `Article` dataclass.

**The `Article` dataclass:**
```python
@dataclass
class Article:
    title: str       # cleaned, HTML-stripped
    url: str         # canonical link
    summary: str     # first 500 chars of content, HTML-stripped
    published: datetime  # timezone-aware UTC
    source: str      # feed name (e.g., "Hugging Face Blog")
    category: str    # from feed config (e.g., "Research")
```

**Key functions:**

`_parse_date(entry)` — RSS feeds are notoriously inconsistent with dates. This function tries 5 different date attributes (`published_parsed`, `updated_parsed`, `created_parsed`, then raw `published` and `updated` strings). Falls back to `datetime.now(UTC)` if nothing works. This defensive approach is essential because arXiv, for example, doesn't always include `published_parsed`.

`_strip_html(html)` — Uses BeautifulSoup with the `lxml` parser to convert HTML to plain text. The `lxml` parser is chosen over `html.parser` because it's faster and handles malformed HTML better (which is common in RSS feeds).

`_truncate(text, limit=500)` — Truncates text at a word boundary, not mid-word. The `rsplit(" ", 1)[0]` trick finds the last space before the limit and cuts there, adding an ellipsis.

`_fetch(feed_cfg)` — Fetches a single feed, takes top 5 entries per feed. Uses a custom User-Agent (`SynapseDaily/1.0`) because some feeds block generic requests. Handles the feedparser "bozo" flag (set when the feed has XML errors) — only skips the feed if there are no parseable entries despite the error.

`collect_articles()` — The main function:
1. Iterates over all feeds from config
2. Deduplicates by URL (using a `seen` set — O(1) lookup)
3. Adds a 0.3s delay between feeds to be polite to servers
4. Sorts by published date (newest first)
5. Returns top `max_articles` (default 15)

**Interview talking point:** "The collector handles real-world messiness — inconsistent date formats, malformed HTML in summaries, duplicate articles across feeds, and feeds that sometimes return XML errors. Production code has to be defensive."

---

### 4.4 ml_ranker.py — The ML Ranking Engine (CRITICAL FOR INTERVIEW)

This is the most interview-relevant module. It uses a pre-trained sentence-transformer to semantically rank articles by AI/ML relevance and remove duplicates.

#### The Model: all-MiniLM-L6-v2

```python
_model = SentenceTransformer("all-MiniLM-L6-v2")
```

**What it is:** A 22M-parameter sentence embedding model based on Microsoft's MiniLM architecture. It maps any text input to a 384-dimensional dense vector (embedding) that captures semantic meaning.

**Architecture (know this for interviews):**
- Based on the Transformer encoder architecture (like BERT, but distilled)
- 6 layers (the "L6"), 384 hidden dimensions, 12 attention heads
- Trained via knowledge distillation from a larger model
- Uses mean pooling over token embeddings to produce a fixed-size sentence vector
- Fine-tuned on 1B+ sentence pairs for semantic similarity tasks
- Size: ~90 MB — small enough to run on CPU in CI/CD

**Why this model specifically?**
- It's the gold standard for lightweight semantic similarity
- Fast inference on CPU (~100 sentences/second)
- 384-dim vectors are compact but expressive
- Normalised embeddings mean cosine similarity = dot product (faster)

#### The Anchor-Based Relevance Scoring System

```python
_ANCHORS = [
    "artificial intelligence machine learning deep learning",
    "large language model neural network transformer",
    "natural language processing computer vision reinforcement learning",
    ...
]
```

**How it works (step by step):**

1. **Embed all articles:** Each article's `title + summary` is encoded into a 384-dim vector
2. **Embed the anchors:** 10 predefined AI/ML topic phrases are encoded into vectors
3. **Compute cosine similarity:** Each article vector is compared against all 10 anchor vectors
4. **Take the max:** Each article's relevance score = highest cosine similarity across all anchors

**Why anchors instead of a classifier?**
- No labeled training data needed — anchors are manually defined topic descriptions
- Easy to modify (just change the text strings)
- This is essentially a zero-shot classification approach using semantic similarity
- It's more flexible than keyword matching — "GPT-5 context window" has high cosine similarity to "large language model" even though they share no words

**The relevance threshold:**
```python
RELEVANCE_THRESHOLD = 0.25
```
Articles below 0.25 cosine similarity to ANY anchor are filtered out. This removes clearly non-AI articles (e.g., a VentureBeat article about fintech that was in their AI RSS feed by mistake).

#### Duplicate Detection

```python
DUPLICATE_CUTOFF = 0.92
```

**How it works:**
1. Compute pairwise cosine similarity matrix for all remaining articles
2. For each pair where similarity > 0.92, remove the later one
3. This is an O(n²) algorithm but with n ≤ 50 articles, it's instant

**Why 0.92?** Through experimentation: 0.95 was too strict (missed paraphrased duplicates), 0.85 was too loose (removed related but distinct articles). 0.92 catches "same story, different source" while keeping "similar topic, different angle".

#### The Final Scoring Formula

```python
scores = 0.6 * relevance + 0.4 * recency
```

**Relevance (60% weight):** Cosine similarity to anchor phrases (0.0-1.0)
**Recency (40% weight):** Exponential decay with 24-hour half-life:

```python
def _recency(published):
    age_hours = (now - published).total_seconds() / 3600
    return exp(-ln(2) * age_hours / 24)
```

This means:
- Published now → recency = 1.0
- Published 24h ago → recency = 0.5
- Published 48h ago → recency = 0.25
- Published 72h ago → recency = 0.125

**Why exponential decay?** It's the standard approach in information retrieval because it provides smooth, continuous decay without any hard cutoff. The half-life of 24 hours means yesterday's articles are worth half as much — reasonable for a daily newsletter.

**Why 60/40 split?** Relevance matters more than recency because we'd rather send a highly relevant 2-day-old article than a barely relevant 1-hour-old article. But recency still matters to keep the newsletter fresh.

**Interview talking point:** "The ranker combines semantic similarity for relevance scoring with temporal decay for recency, using a weighted linear combination. It's essentially a simple but effective learning-to-rank approach where the 'features' are embedding similarity and time, and the 'weights' are manually set rather than learned — which is appropriate given we have no click-through data to train on."

---

### 4.5 curator.py — LLM Curation Layer

This module sends the top-ranked articles to an LLM and gets back a structured newsletter digest.

#### The Prompt Engineering

The prompt is a carefully structured instruction that:
1. Sets the persona: "You are the editor of Synapse Daily"
2. Provides all articles as JSON (with title, URL, summary, source, category, published date)
3. Specifies the exact output JSON schema with field-level descriptions
4. Sets tone guidelines: "be specific, cite numbers/benchmarks, don't hype"
5. Tells the model the current date for temporal context

**Why JSON-in, JSON-out?**
- Structured output is more reliable than free-form text
- JSON schema acts as a contract — the code knows exactly what fields to expect
- Makes parsing deterministic (just `json.loads()`)
- LLMs are very good at following JSON schemas when instructed clearly

#### The Groq API Integration

```python
url = "https://api.groq.com/openai/v1/chat/completions"
payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.4,
    "max_tokens": 4096,
}
```

**Why temperature 0.4?** Not 0.0 (too deterministic, repetitive outputs) and not 0.7+ (too creative, might hallucinate). 0.4 gives slight variation while keeping the output factual and grounded.

**Why max_tokens 4096?** The response needs to contain 5 full story summaries + brief items + editorial content. 4096 tokens is enough for ~3000 words, which is sufficient.

#### Retry Logic with Exponential Backoff

```python
for attempt in range(3):
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    if resp.status_code == 429 and attempt < 2:
        wait = 30 * (attempt + 1)  # 30s, 60s
        time.sleep(wait)
        continue
    resp.raise_for_status()
    break
```

**Pattern:** 3 attempts with 30s and 60s backoff for rate limits (429). This is a simplified exponential backoff — production systems typically use jitter (random delay) to prevent thundering herd, but for a single daily request, linear backoff suffices.

#### Response Parsing & Cleanup

```python
if raw.startswith("```"):
    raw = raw.split("```", 2)[1]
    if raw.startswith("json"):
        raw = raw[4:]
    raw = raw.rsplit("```", 1)[0].strip()
```

**Why this cleanup?** LLMs frequently wrap JSON in markdown code blocks even when told not to. This strips the ``` markers to get clean JSON. This is a common real-world LLM integration pattern — never trust the output format, always sanitise.

**Interview talking point:** "Integrating LLMs in production means handling their unreliability — you need retry logic for API errors, output sanitisation for format issues, and structured schemas to constrain the output space."

---

### 4.6 renderer.py — Email Rendering

Uses Jinja2 templating engine to render the `CuratedDigest` dataclass into HTML and plain-text email formats.

**Key design decisions:**
- `autoescape=True` prevents XSS — if an article title contains `<script>`, it's escaped
- `trim_blocks` and `lstrip_blocks` keep the template readable without extra whitespace in output
- Template path calculated relative to the file, not current directory, so it works regardless of where the script is run

**The HTML template (email.html):**
- Uses table-based layout (not divs/flexbox) because email clients like Outlook strip CSS
- All styles are inline (not in `<style>` block) for maximum compatibility
- Dark theme with a purple accent (#6c63ff)
- Responsive width (max-width 620px, width 100%)

**Interview talking point:** "Email HTML is 15 years behind web HTML. You can't use CSS Grid, Flexbox, or even reliable `<div>` layouts. Table-based layout with inline styles is the only cross-client approach."

---

### 4.7 mailer.py — Email Delivery

Handles SMTP connection to Gmail and subscriber management.

**Key features:**
- **Dual-source subscribers:** Tries Supabase first (for web-app subscribers), falls back to `RECIPIENT_EMAILS` env var
- **MIME multipart:** Sends both HTML and plain-text versions. Email clients pick the richest version they support
- **TLS encryption:** Uses STARTTLS (port 587), not raw TLS (port 465)
- **App Password auth:** Gmail requires App Passwords when 2FA is enabled. Regular passwords are rejected
- **Per-recipient sending:** Each recipient gets their own SMTP sendmail call, so one failure doesn't block others

**Interview talking point:** "I implemented graceful degradation — if Supabase is down, it falls back to env-var recipients. If one email fails, others still send. The result dict tracks successes and failures separately."

---

## 5. THE ML MODEL — all-MiniLM-L6-v2 (DEEP DIVE)

This section is critical for AI/ML interview questions.

### Architecture

**Base model:** MiniLM (Microsoft, 2020) — a knowledge-distilled Transformer encoder

**What is knowledge distillation?** A large "teacher" model (like BERT-large, 340M params) is used to train a smaller "student" model (22M params) by having the student learn to reproduce the teacher's output distributions, not just the labels. The student learns the teacher's "dark knowledge" — the probability distributions over incorrect classes, which contain useful similarity information.

**The Transformer encoder (know this cold):**

1. **Input:** Tokenised text → token IDs
2. **Embedding layer:** Token IDs → 384-dim vectors + positional encodings
3. **6 Transformer layers, each containing:**
   - Multi-head self-attention (12 heads, 32 dims each)
   - Layer normalisation
   - Feed-forward network (384 → 1536 → 384)
   - Residual connections
4. **Mean pooling:** Average all token vectors → single 384-dim sentence vector
5. **L2 normalisation:** Normalise to unit length (so cosine similarity = dot product)

### Self-Attention Mechanism (Interview Must-Know)

For each token, self-attention computes:

```
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) * V
```

Where:
- Q (query), K (key), V (value) are linear projections of the input
- d_k = 32 (dimension per head)
- The softmax creates an attention distribution over all tokens
- The result is a weighted sum of value vectors

**Multi-head attention:** 12 independent attention heads, each looking at different "aspects" of the relationships between tokens. Outputs are concatenated and linearly projected back to 384 dims.

**Why self-attention for text embeddings?** It captures long-range dependencies — the word "not" at the beginning of a sentence can affect the meaning of "good" at the end. This is something that bag-of-words or even RNNs struggle with.

### Cosine Similarity (Interview Must-Know)

```
cos(A, B) = (A · B) / (||A|| * ||B||)
```

For L2-normalised vectors (||A|| = ||B|| = 1):
```
cos(A, B) = A · B  (just a dot product!)
```

**Range:** -1 (opposite meaning) to +1 (identical meaning), typically 0 to 1 for real text

**Why cosine over Euclidean distance?**
- Cosine is magnitude-invariant (a longer document isn't "further" from a shorter one)
- It measures the *angle* between vectors, which captures semantic similarity better
- With normalised vectors, it's equivalent to dot product (very fast)

### Why This Model Is Perfect for This Use Case

| Requirement | all-MiniLM-L6-v2 | Alternative |
|---|---|---|
| CPU inference | ~100 sent/sec | GPU models: 10x faster but need GPU ($$$) |
| Size | 90 MB | all-mpnet-base-v2: 420 MB |
| Quality | 68.1% on STS benchmark | mpnet: 69.6% (marginal gain) |
| Embedding dim | 384 | Some models: 768+ (more memory) |
| GitHub Actions | Perfect (2GB RAM limit) | Large models: OOM errors |

---

## 6. THE LLM LAYER — Groq + Llama 3.3 70B

### Why Groq (Not OpenAI, Not Gemini)?

**The story:** We originally used Google Gemini (free tier) but hit persistent 429 rate-limit errors from GitHub Actions. Google's free tier aggressively throttles requests from known datacenter IP ranges (Azure/GCP, which GitHub Actions runs on). After 7 failed runs trying different API keys, retry strategies, and backoff times, we switched to Groq.

**Groq advantages:**
- Free tier: 14,400 requests/day, 30 RPM — very generous
- No datacenter IP throttling (works perfectly from GitHub Actions)
- OpenAI-compatible API — minimal code changes
- Extremely fast inference (custom LPU hardware): ~500 tokens/second
- Supports Llama 3.3 70B — a top-tier open model

### Llama 3.3 70B — The Model

- **Developer:** Meta AI
- **Parameters:** 70 billion
- **Architecture:** Decoder-only Transformer (GPT-style, not BERT-style)
- **Context window:** 128K tokens
- **Training data:** 15T+ tokens of public data
- **Why "versatile"?** Groq's nickname for the general-purpose variant (vs. instruct-specific)

**For interviews, know the difference:**
- **Encoder models** (like MiniLM/BERT): Bidirectional attention, good for understanding/classification/embeddings
- **Decoder models** (like Llama/GPT): Autoregressive (left-to-right) attention, good for generation
- We use BOTH: MiniLM encoder for ranking, Llama decoder for text generation

### The Prompt Structure (Prompt Engineering)

```
System context: "You are the editor of Synapse Daily..."
Input: Articles as structured JSON
Output spec: Exact JSON schema with field descriptions
Guidelines: Tone, style, date
```

**Prompt engineering principles used:**
1. **Persona:** "editor of a newsletter for engineers" — grounds the tone
2. **Structured I/O:** JSON in, JSON out — reduces format errors
3. **Few-shot via schema:** The output schema with field descriptions acts like a few-shot example
4. **Negative constraints:** "no markdown, no explanation" — prevents common LLM behaviors
5. **Grounding:** "cite numbers/benchmarks, don't hype" — reduces hallucination

---

## 7. ALL TECHNOLOGIES & WHY EACH WAS CHOSEN

### Core Python Stack

| Package | Version | Purpose | Why This One? |
|---|---|---|---|
| `feedparser` | 6.0.11 | RSS/Atom parsing | The de-facto standard; handles quirky feeds gracefully |
| `beautifulsoup4` | 4.12.3 | HTML→text | Robust HTML parser; handles malformed HTML from RSS |
| `lxml` | 5.3.0 | BS4 backend | 10x faster than html.parser; handles edge cases |
| `requests` | 2.32.3 | HTTP client | Simple, well-tested; sufficient for single API calls |
| `jinja2` | 3.1.4 | HTML templating | Industry standard; auto-escaping prevents XSS |
| `python-dotenv` | 1.0.1 | .env loading | Loads .env for local dev; no-op in CI where env vars are set |

### ML Stack

| Package | Version | Purpose | Why This One? |
|---|---|---|---|
| `sentence-transformers` | 3.4.1 | Embedding model framework | Wraps HuggingFace models with simple encode() API |
| `torch` | 2.6.0 | PyTorch (ML backend) | Required by sentence-transformers; CPU-only usage |
| `numpy` | 2.2.4 | Numerical computing | Embedding vectors, cosine similarity computation |
| `scikit-learn` | 1.6.1 | ML utilities | `cosine_similarity()` — optimised C implementation |

### Infrastructure

| Technology | Purpose | Why This One? |
|---|---|---|
| **GitHub Actions** | CI/CD orchestration | Free for public repos; cron scheduling; secret management |
| **Gmail SMTP** | Email delivery | Free; reliable; supports App Passwords for automation |
| **Groq API** | LLM inference | Free tier; no datacenter IP throttling; fast; OpenAI-compatible |
| **Supabase** | Subscriber database | Free tier PostgreSQL; REST API; handles auth |
| **Vercel** | Landing page hosting | Free tier; serverless Python functions; edge CDN |

### Why Not X?

| Alternative | Why Not? |
|---|---|
| **OpenAI GPT-4** | Costs money; this is a free/open-source project |
| **Google Gemini** | Throttles GitHub Actions IPs (429 errors) |
| **Anthropic Claude API** | Costs money per token |
| **Celery/Redis** | Overkill for a single daily job; GitHub Actions is simpler |
| **SendGrid/Mailgun** | Gmail is free and sufficient for low volume |
| **FAISS for dedup** | Overkill for ~50 articles; sklearn's cosine_similarity is fine |

---

## 8. ISSUES FACED & HOW THEY WERE SOLVED

### Issue 1: Gemini 429 Rate Limiting (THE BIG ONE)

**Symptom:** Every GitHub Actions run got HTTP 429 "Too Many Requests" from Google Gemini, even on the very first API call of a fresh run.

**Investigation steps:**
1. Verified we were well under rate limits (6 requests total across all runs; free tier allows 15 RPM)
2. Added exponential backoff (60s, 120s waits) — still 429 on all 3 retries
3. Created a brand-new Gemini API key — still 429 on the FIRST request
4. This ruled out per-key quota and per-minute rate limiting

**Root cause:** Google's free Gemini tier aggressively throttles requests from known datacenter IP ranges. GitHub Actions runs on Microsoft Azure infrastructure, and Google pre-emptively blocks these IPs to prevent abuse.

**Solution:** Switched to Groq entirely. Code changes were minimal because Groq uses an OpenAI-compatible API format:
- Changed endpoint URL
- Changed response parsing (`choices[0].message.content` vs `candidates[0].content.parts[0].text`)
- Changed env var name (`GROQ_API_KEY` vs `GEMINI_API_KEY`)

**Interview talking point:** "This is a classic production issue — the API worked perfectly locally but failed in CI because of IP-based throttling. The fix was provider migration, not code changes. In production, you always need a fallback LLM provider."

### Issue 2: GitHub Secrets Not Saving via Browser Automation

**Symptom:** GitHub secret appeared saved but was actually empty, causing `KeyError` in the pipeline.

**Root cause:** React's state management requires synthetic events (onChange) to register input values. Programmatically setting a form field's value via DOM manipulation doesn't trigger React's state update.

**Solution:** Used keyboard typing simulation instead of direct DOM manipulation, which triggers React's synthetic events correctly.

### Issue 3: Email Client Compatibility

**Symptom:** HTML email looked broken in Outlook, Yahoo Mail, etc.

**Root cause:** Email clients strip `<style>` blocks, don't support CSS Grid/Flexbox, and have inconsistent CSS support.

**Solution:** All styles inline, table-based layout, no external CSS, no `<div>` layout.

---

## 9. INTERVIEW-CRITICAL ML/AI CONCEPTS USED

### 9.1 Embeddings & Representation Learning

**What are embeddings?** Dense, low-dimensional vector representations of discrete inputs (words, sentences, images) in a continuous vector space where semantically similar items are close together.

**In this project:** Article titles+summaries → 384-dim vectors. Similar articles cluster together in this space.

**Key interview questions:**
- "How are sentence embeddings different from word embeddings?" → Word embeddings (Word2Vec, GloVe) represent individual words; sentence-transformers use the Transformer architecture to produce a single vector for the entire sentence, capturing word order and context.
- "Why not just use TF-IDF?" → TF-IDF is a bag-of-words approach that loses word order and can't capture synonyms. "GPT-5 launches" and "Large language model released" would have zero TF-IDF similarity but high embedding similarity.

### 9.2 Cosine Similarity vs Other Distance Metrics

**Cosine similarity:** Measures angle between vectors. Range [-1, 1].
**Euclidean distance:** Measures straight-line distance. Unbounded.
**Dot product:** Measures similarity + magnitude. Unbounded.

**In this project:** Cosine similarity is used because:
1. Magnitude-invariant (document length doesn't matter)
2. Bounded range makes thresholding easy (0.25 relevance, 0.92 dedup)
3. With normalised vectors, it's just a dot product (fast)

### 9.3 Zero-Shot Classification via Semantic Similarity

The anchor-based relevance system is essentially **zero-shot classification** — classifying articles as "AI/ML relevant" or not, without any labeled training data.

**How traditional classification works:** Train a model on labeled examples (article → relevant/not relevant).
**How we do it:** Define the classes via natural language descriptions (the anchors), embed everything, and use cosine similarity as the classification score.

**This is the same principle behind:**
- CLIP (OpenAI) — classifying images using text descriptions
- Zero-shot NLI-based classification — using entailment as a proxy for classification

### 9.4 Knowledge Distillation

MiniLM was created via distillation from a larger model.

**How it works:**
1. Train a large "teacher" model (e.g., BERT-large, 340M params)
2. Use the teacher to generate soft probability distributions (not just hard labels)
3. Train a smaller "student" (22M params) to match those distributions
4. The student learns from the teacher's uncertainty — "this word is 70% positive, 20% neutral, 10% negative" is more informative than just "positive"

**Why the student can be much smaller:** Most of the teacher's capacity is used to learn the training data; the student only needs to learn the teacher's compressed representation.

### 9.5 Transformer Architecture Fundamentals

**The key components (know these in detail):**

1. **Tokenisation:** Text → subword tokens (BPE or WordPiece)
2. **Embedding:** Tokens → dense vectors + positional encoding
3. **Self-attention:** Each token attends to all other tokens (O(n²) complexity)
4. **Feed-forward:** Two linear layers with ReLU/GELU activation
5. **Layer normalisation:** Stabilises training
6. **Residual connections:** Enables gradient flow in deep networks

**Positional encoding:** Transformers have no inherent notion of order (unlike RNNs). Positional encodings (sinusoidal or learned) are added to token embeddings so the model knows token positions.

### 9.6 LLM Prompt Engineering Best Practices

Demonstrated in `curator.py`:

1. **Structured I/O:** Provide input as JSON, request output as JSON
2. **Schema specification:** Define the exact fields, types, and descriptions
3. **Persona setting:** "You are the editor of..." grounds the model's tone
4. **Negative constraints:** "no markdown, no explanation" prevents common issues
5. **Temperature tuning:** 0.4 balances creativity and reliability
6. **Output sanitisation:** Strip markdown code blocks from responses

### 9.7 Exponential Decay for Recency Scoring

```python
score = exp(-ln(2) * age_hours / half_life)
```

This is the same formula used in:
- Radioactive decay
- Learning rate scheduling
- Temporal difference learning (TD-lambda)
- Time-series anomaly detection

**Properties:** Smooth, continuous, never reaches zero, controlled by a single parameter (half-life).

---

## 10. SYSTEM DESIGN & SCALABILITY DISCUSSION

### Current Scale

- 10 RSS feeds, ~50 articles/day
- 1 LLM API call/day
- 1-10 email recipients
- Total runtime: ~15 seconds
- Cost: $0 (all free tiers)

### How Would You Scale to 10,000 Subscribers?

**Email:** Switch from Gmail SMTP (500/day limit) to a transactional email service (SendGrid, AWS SES, Postmark). These handle deliverability, bounce management, and unsubscribe links.

**Personalisation:** Instead of one newsletter for everyone, cluster subscribers by interest (using their click history) and generate personalised digests. This would require a user database and click tracking.

**Feed volume:** Add more feeds, increase `max_articles`. The ML ranker is O(n²) for dedup but still fast up to ~1000 articles. Beyond that, use approximate nearest neighbors (FAISS) for dedup.

**LLM costs:** At scale, you'd batch-generate newsletters (one per interest cluster) and cache results. Groq's free tier (14,400 req/day) is more than enough for daily generation.

### How Would You Add Real-Time Ranking?

Replace the anchor-based scoring with a learned ranking model trained on user click data:
1. Log which articles each user clicks
2. Train a click-through rate (CTR) prediction model
3. Features: article embedding, user embedding, recency, source quality
4. Model: gradient-boosted trees (XGBoost/LightGBM) or a neural ranker
5. This is essentially a recommender system

### How Would You Evaluate the ML Ranker?

Currently there's no automated evaluation. Options:
1. **A/B testing:** Send different rankings to different user groups, measure click-through
2. **Offline evaluation:** Have human raters label a sample of articles as "relevant" or not, compute precision/recall
3. **Proxy metrics:** Track if articles that rank higher get more clicks (NDCG score)
4. **Embedding quality:** Evaluate on standard STS benchmarks

---

## 11. POTENTIAL INTERVIEW QUESTIONS & ANSWERS

### Q: Walk me through the system architecture.
**A:** "Synapse Daily is a 5-stage pipeline: Collect (RSS fetching with feedparser), Rank (sentence-transformer embeddings + cosine similarity for relevance + exponential decay for recency), Curate (LLM generates structured summaries), Render (Jinja2 templating), Deliver (Gmail SMTP). It runs daily via GitHub Actions cron. The key ML component is the ranker — it uses all-MiniLM-L6-v2 to embed articles into 384-dim vectors and scores them against predefined AI/ML topic anchors using cosine similarity."

### Q: Why did you use embeddings instead of keyword matching?
**A:** "Keyword matching misses semantic similarity. 'GPT-5 releases' and 'large language model launched' share zero keywords but are semantically identical. Embeddings capture this because they're trained on billions of sentence pairs to place semantically similar text close together in vector space. The cosine similarity between their embeddings would be ~0.85+."

### Q: How does your deduplication work?
**A:** "I compute a pairwise cosine similarity matrix for all article embeddings. Any pair with similarity above 0.92 is treated as a duplicate — I keep the one that appeared first (from the higher-quality feed). This is an O(n²) approach, which is fine for n≤50. At larger scale, I'd use approximate nearest neighbors (e.g., FAISS with IVF index) to avoid the quadratic cost."

### Q: What would you do differently with more time?
**A:** "Three things: (1) Add click tracking and train a personalized ranker using user interaction data instead of static anchors. (2) Fine-tune the embedding model on AI/ML-specific text to improve domain relevance scoring. (3) Add automated evaluation — compute NDCG on a labeled test set, and set up A/B testing for the email layout."

### Q: How did you handle the Gemini rate-limiting issue?
**A:** "We systematically ruled out per-key quotas (fresh key still failed), per-minute limits (well under quota), and per-day limits (only 6 total requests). The root cause was IP-based throttling — Google blocks datacenter IP ranges from Azure (where GitHub Actions runs). The fix was migrating to Groq, which has no such restriction. The code change was minimal because Groq uses an OpenAI-compatible API format."

### Q: Explain the temperature parameter in your LLM call.
**A:** "Temperature controls the softmax distribution over next-token probabilities. At T=0, the model always picks the highest-probability token (greedy decoding) — deterministic but potentially repetitive. At T=1, the distribution is unchanged. At T>1, it becomes flatter (more random). I use 0.4 because the task is factual summarisation — I want slight variation between runs but not creative hallucination."

### Q: What's the difference between the sentence-transformer you use and GPT?
**A:** "Fundamental architectural difference. MiniLM is an encoder (like BERT) — it uses bidirectional attention, sees the full text at once, and produces a fixed-size embedding vector. GPT/Llama are decoders — they use causal (left-to-right) attention and generate text token by token. I use both: the encoder for understanding/comparing text (ranking), and the decoder for generating text (summaries)."

### Q: How do you ensure the LLM output is reliable?
**A:** "Four layers of defence: (1) Structured JSON output schema constrains the format. (2) The code strips markdown code blocks that LLMs sometimes add. (3) JSON parse errors are caught and logged with the raw output for debugging. (4) Retry logic with exponential backoff handles transient API failures. In a production system, I'd add response validation — check that URLs are valid, summaries aren't empty, etc."

### Q: Why not fine-tune the embedding model on AI/ML data?
**A:** "Cost-benefit tradeoff. The general-purpose all-MiniLM-L6-v2 already has strong AI/ML understanding from its training data (which included papers, technical blogs, etc.). Fine-tuning would require: (a) a labeled dataset of AI/ML article pairs with similarity scores, (b) GPU training time, (c) ongoing maintenance as the field evolves. The anchor-based approach achieves ~95% of the quality with zero training cost. I'd only fine-tune if click-through data showed the current model is making systematic errors."

### Q: What are the limitations of your approach?
**A:** "Several: (1) Static anchors don't adapt to emerging topics — if a new subfield emerges (like 'mechanistic interpretability'), I'd need to manually add an anchor. (2) No personalisation — every subscriber gets the same digest. (3) The 0.6/0.4 weighting is manually tuned, not learned. (4) No evaluation framework — I can't quantify if today's ranking is better than yesterday's. (5) Single LLM provider with no fallback."
