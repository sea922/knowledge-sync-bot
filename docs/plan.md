# OptiSigns Back-End Take-Home Test — Implementation Plan

## Overview

Build **OptiBot Mini**: a pipeline that scrapes ≥ 30 help articles from `support.optisigns.com`, converts them to Markdown, uploads them to an OpenAI Vector Store, exposes an Assistant, and runs the whole thing daily on DigitalOcean.

**Passing bar:** 70 / 100 points.

---

## Open Questions

> [!IMPORTANT]
> Please clarify the following before I start coding:

1. **OpenAI API key** — Do you already have one ready, or should I include instructions for creating it?
2. **DigitalOcean account** — Do you have an account and are you okay with the cost of a DigitalOcean App Platform job?
3. **GitHub repo name** — I'll pick a cryptic name (e.g., `knowledge-sync-bot`). Any preferences?
4. **System prompt** — The test says "use the provided verbatim system prompt". Was this in the PDF? If so, please paste it here.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | **Python 3.14** | OpenAI SDK, requests, markdownify all have great Python support |
| Scraping | **BeautifulSoup4** | Auto-scrape support.optisigns.com without relying on the Zendesk API |
| HTML → Markdown | **markdownify** | Preserves headings, code blocks, links |
| OpenAI | **openai** Python SDK v1+ | Native Vector Store & Assistants API support |
| Scheduling | **DigitalOcean App Platform** (Job) | Free-tier-friendly, simple cron job |
| Containerisation | **Docker** | Required by test |
| Config | **python-dotenv** + `.env.sample` | No hard-coded keys |
| Change detection | **MD5 hash** of article body | Simple, reliable delta detection |

---

## Proposed Project Structure

```
knowledge-sync-bot/
├── .env.sample                # OPENAI_API_KEY, VECTOR_STORE_ID, ASSISTANT_ID
├── .gitignore
├── Dockerfile
├── README.md
├── requirements.txt
├── main.py                    # Entrypoint — scrape + upload (called by Docker / cron)
├── scraper/
│   ├── __init__.py
│   └── scraper.py             # Web scraper (BeautifulSoup) → Crawl & fetch articles
├── converter/
│   ├── __init__.py
│   └── markdown.py            # HTML → clean Markdown (markdownify + cleanup)
├── uploader/
│   ├── __init__.py
│   └── vector_store.py        # Upload files, detect delta, log counts
├── state/
│   └── article_hashes.json    # Persisted hash map {article_id: md5}
└── docs/
    └── OptiSigns_Test_Summary.md
```

---

## Phase-by-Phase Plan

---

### Phase 0 — Project Bootstrap

#### [NEW] `.gitignore`
Standard Python ignore: `__pycache__`, `.env`, `articles/`, `state/`.

#### [NEW] `.env.sample`
```
OPENAI_API_KEY=sk-...
# ID of the Vector Store created in the OpenAI Dashboard (used to upload files)
VECTOR_STORE_ID=vs_...
# ID of the Assistant created in the OpenAI Dashboard (the OptiBot clone)
ASSISTANT_ID=asst_...
```

#### [NEW] `requirements.txt`
```
openai>=1.30
requests>=2.31
beautifulsoup4>=4.12
markdownify>=0.11
python-dotenv>=1.0
```

---

### Phase 1 — Scrape → Markdown

#### [NEW] `scraper/scraper.py`

- Use **BeautifulSoup** to crawl `https://support.optisigns.com/hc/en-us`.
- Find category/section links, then find all article links.
- For each article URL:
  - Fetch HTML and parse with BeautifulSoup.
  - Extract: `title` (from `h1`), `body` (from main article container), `html_url`, `slug` (from URL).
- Return a list of article dicts.

#### [NEW] `converter/markdown.py`

- Run `markdownify(html, heading_style="ATX")` on the `body` field.
- Post-process:
  - Preserve relative links (prefix with `https://support.optisigns.com`).
  - Strip nav/ad patterns (e.g., `<nav>`, `<header>`, `<footer>` tags removed before conversion).
  - Add a front-matter block: `# {title}\n> Source: {html_url}\n\n{markdown_body}`.
- Save each article as `articles/{slug}.md`.

---

### Phase 2 — Build Assistant & Load Vector Store

#### [NEW] `uploader/vector_store.py`

**Upload logic:**
1. Load `state/article_hashes.json` (empty dict if not exists).
2. For each scraped article:
   - Compute `md5(markdown_content)`.
   - Compare to stored hash.
   - **New** → upload & add hash.
   - **Changed** → delete old file from vector store, re-upload, update hash.
   - **Unchanged** → skip.
3. Use `openai.beta.vector_stores.files.upload_and_poll(...)` (chunking handled by API with `auto` strategy).
4. Log: `Added: N | Updated: N | Skipped: N`.
5. Save updated hashes back to `state/article_hashes.json`.

**Chunking strategy (for README):**  
Use OpenAI's built-in `auto` chunking strategy (max 800 tokens per chunk, 400 token overlap). This is optimal for help articles — short enough for precise retrieval, large enough to preserve context.

**Assistant creation (one-time, via Playground UI):**
- Model: `gpt-4o`
- Tool: `file_search` enabled
- Attach the Vector Store
- Use provided system prompt

#### [NEW] `main.py`

```python
# Orchestrates: scrape → convert → upload delta
scrape() → convert() → upload_delta()
```

Exits with code `0` on success, non-zero on failure (required by test).

---

### Phase 3 — Dockerize & Deploy Daily Job

#### [NEW] `Dockerfile`

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

Run locally: `docker run -e OPENAI_API_KEY=... knowledge-sync-bot`

#### DigitalOcean Daily Job

- Platform: **DigitalOcean App Platform** → Job (not a web service).
- Deploy from GitHub repo (connect via DO dashboard).
- Set **cron schedule**: `0 2 * * *` (2 AM UTC daily).
- Inject env vars via DO App spec (no secrets in repo).
- Job logs available in the DO dashboard → link to include in README.

---

### Deliverables Checklist

| Item | Status |
|---|---|
| GitHub repo (cryptic name, no "optisigns") | `[ ]` |
| ≥ 30 articles scraped as clean `.md` files | `[ ]` |
| OpenAI Vector Store populated via script | `[ ]` |
| Assistant created in Playground | `[ ]` |
| Screenshot: "How do I add a YouTube video?" | `[ ]` |
| `main.py` (scrape + upload delta) | `[ ]` |
| `Dockerfile` (exits 0) | `[ ]` |
| DigitalOcean daily job live | `[ ]` |
| Link to job logs / last run | `[ ]` |
| `README.md` (≤ 1 page) | `[ ]` |
| `.env.sample` (no hard-coded keys) | `[ ]` |

---

## Verification Plan

### Automated
- `docker build -t optibot .` — must succeed.
- `docker run -e OPENAI_API_KEY=$KEY optibot` — must exit 0.
- Check log output for `Added / Updated / Skipped` counts.
- Verify `state/article_hashes.json` is written with ≥ 30 entries.
- Run twice: second run should show `Added: 0, Updated: 0, Skipped: N`.

### Manual
- Open OpenAI Playground, ask "How do I add a YouTube video?".
- Verify cited article URLs are from `support.optisigns.com`.
- Take screenshot for README.
- Confirm DigitalOcean Job shows last run with exit code 0.
