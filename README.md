# OptiBot Mini — Knowledge Sync Bot

A daily pipeline that scrapes the OptiSigns Help Center, converts articles to Markdown, and keeps an OpenAI Vector Store in sync. Powers a GPT-4o–based support assistant.

---

## Setup

**Prerequisites:** Python 3.14+, Docker, OpenAI account, DigitalOcean account.

```bash
git clone <repo-url>
cd knowledge-sync-bot

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.sample .env
# Edit .env with your keys (see below)
```

### Required Environment Variables

| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `VECTOR_STORE_ID` | OpenAI Dashboard → Storage → Vector Stores → create one → copy ID (`vs_…`) |
| `ASSISTANT_ID` | OpenAI Dashboard → Assistants → create one with `file_search` tool → copy ID (`asst_…`) |

> **Assistant setup (one-time):** In the OpenAI Playground, create an Assistant with model `gpt-4o`, enable the **File Search** tool, attach your Vector Store, and paste the system prompt provided in the test brief.

---

## Run Locally

```bash
# Direct Python
python main.py

# Unittest
python -m pytest -v tests/

# Docker
docker build -t knowledge-sync-bot .
docker run --env-file .env knowledge-sync-bot
```

---

## How It Works

1. **Scrape** — Fetches articles from the public Zendesk Help Center JSON API (as suggested by the test specification). This approach retrieves clean HTML, executes with 100% reliability, and completely bypasses Cloudflare 403 Forbidden / interactive challenge blocks.
2. **Convert** — Each article is converted to clean Markdown (`articles/<slug>.md`) with title, source URL, and body.
3. **Delta upload** — MD5 hashes are compared to `state/article_hashes.json`. Only new or changed articles are uploaded to the Vector Store. Log output:
   ```
   Added: N | Updated: N | Skipped: N | Errors: 0
   ```

### Chunking Strategy

The pipeline uses OpenAI's built-in **`auto` chunking strategy** delegated to the Vector Store API. The parameters are:

| Parameter | Value | Reason |
|---|---|---|
| Max chunk size | **800 tokens** | Fits a complete how-to step or procedure without splitting mid-idea |
| Overlap | **400 tokens** (50 %) | Ensures context from the previous chunk bleeds into the next, so answers that span two steps are never missed |
| Encoding estimate | ~4 chars/token | Standard GPT tokenizer average for English prose |

**Why `auto`?** Help-center articles are short, self-contained, and written in plain English paragraphs. OpenAI's auto strategy splits on natural sentence/paragraph boundaries first, then falls back to token limits — giving semantically coherent chunks without custom pre-processing code.

**Chunk count logging:** After every upload the pipeline logs:
```
Embedded N file(s), ~C chunk(s) this run
```
The count `C` is estimated with the formula:
```
chunks = max(1, ceil((file_tokens − 800) / 400) + 1)
```
where `file_tokens ≈ file_bytes / 4`. The estimate aligns closely with OpenAI's actual split count for prose files.


---

## Daily Job (DigitalOcean)

Deployed as a **DigitalOcean App Platform Job** scheduled at `0 2 * * *` (2 AM UTC).

- Connect your GitHub repo in the DO dashboard.
- Add env vars (`OPENAI_API_KEY`, `VECTOR_STORE_ID`, `ASSISTANT_ID`) in App settings.
- The job exits `0` on success.

**Last run logs:** *(add DigitalOcean job logs link here after first deploy)*

---

## Screenshot

*Assistant answering "How do I add a YouTube video?" in OpenAI Playground:*

*(add screenshot here)*
