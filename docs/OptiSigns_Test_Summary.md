# OptiSigns – Back-End Take-Home Test Summary

**Goal:** Build a mini-clone of "OptiBot" (OptiSigns' customer support bot) by scraping help articles, uploading them to OpenAI, and automating the process as a daily job.

## 0. Warm-up
- Create a free [optisigns.com](https://www.optisigns.com/) trial account and chat with OptiBot.
- Open a free [platform.openai.com](https://platform.openai.com/) account.

## 1. Scrape ⇒ Markdown
- **Task:** Pull ≥ 30 articles from `support.optisigns.com`.
- **Formatting:** Convert each article to clean Markdown. Save as `<slug>.md`.
- **Requirements:** Preserve relative links, code blocks, and headings. Remove navigation and ads.
- **Hint:** Use the Zendesk API to read the articles.

## 2. Build Assistant & Programmatically Load Vector Store
- **Create Assistant:** Use the OpenAI Playground UI. Use the provided verbatim system prompt.
- **Python Script:** Write a script to upload the Markdown files to an OpenAI Vector Store via the OpenAI API (no UI drag-and-drop).
  - Chunking strategy is up to you (explain it in the README).
  - Log how many files and chunks were embedded.
- **Sanity Check:** Ask the Assistant "How do I add a YouTube video?" in the Playground and take a screenshot of the correct answer with citations.

## 3. Deploy Scraper as Daily Job
- **Wrap up:** Put your scraper and uploader logic in `main.py`.
- **Dockerize:** Create a `Dockerfile`.
- **Scheduling:** Schedule it to run once per day on the DigitalOcean Platform.
- **Job Requirements:**
  - Re-scrape articles.
  - Detect new or updated articles (using hash, `Last-Modified`, etc.).
  - Upload only the delta.
  - Log counts: added, updated, skipped.
  - Provide a link to job logs or the last run artifact.

## Deliverables
- **GitHub Repo:** Use a cryptic name (do NOT use "optisigns" in the name). Clear commits, no hard-coded keys (use a `.env.sample`).
- **Dockerfile:** Must run with `docker run -e OPENAI_API_KEY=... main.py` and exit 0.
- **README (≤ 1 page):** Include setup instructions, how to run locally, a link to the daily job logs, and the screenshot of the Playground answer.
- **Screenshot:** Showing the Assistant correctly answering sample questions with cited URLs.

## Grading & Review
- **Passing Bar:** 70 points (Graded on scrape/clean quality, API vector store upload, daily job deployment/logs, and code clarity/README).
- **1h Project Review:** Be prepared to discuss your concept understanding, approach, how you learn new things, and suggestions/challenges for OptiBots.
