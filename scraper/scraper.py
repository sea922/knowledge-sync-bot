"""
Fetches help articles from the OptiSigns Help Center using Zendesk Help Center JSON API.
This approach bypasses Cloudflare browser challenges and is highly robust and efficient.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Generator
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://support.optisigns.com"
API_URL = f"{BASE_URL}/api/v2/help_center/en-us/articles.json"

# Polite crawl delay (seconds) between API requests
CRAWL_DELAY = 0.2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def _slug_from_url(url: str) -> str:
    """Derive a filesystem-safe slug from an article URL."""
    path = urlparse(url).path  # e.g. /hc/en-us/articles/12345-some-title
    # Take the last path segment and strip leading numeric ID
    last = path.rstrip("/").split("/")[-1]
    # Remove leading digits and dash  e.g. "12345678-some-title" → "some-title"
    slug = re.sub(r"^\d+-", "", last)
    # Fallback: use the raw numeric id if slug is empty
    return slug or last


def scrape_articles(max_articles: int = 0) -> Generator[dict, None, None]:
    """
    Crawl support.optisigns.com Zendesk API and yield article dicts.

    Args:
        max_articles: If > 0, stop after collecting this many articles.
                      Set to 0 (default) for unlimited.

    Yields:
        dict with keys: title, html_url, slug, body_html
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    
    next_url = f"{API_URL}?per_page=100"
    count = 0
    
    logger.info("Starting crawl from %s", next_url)
    
    while next_url:
        try:
            resp = session.get(next_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch API page %s: %s", next_url, exc)
            break
            
        data = resp.json()
        articles_list = data.get("articles", [])
        
        for article in articles_list:
            # Skip drafts or articles without a body
            if article.get("draft") or not article.get("body"):
                continue
                
            title = article.get("title") or article.get("name") or "Untitled"
            html_url = article.get("html_url")
            if not html_url:
                continue
                
            slug = _slug_from_url(html_url)
            body_html = article.get("body", "")
            
            yield {
                "title": title,
                "html_url": html_url,
                "slug": slug,
                "body_html": body_html,
                "updated_at": article.get("updated_at") or article.get("edited_at", ""),
            }
            
            count += 1
            if max_articles and count >= max_articles:
                logger.info("Reached maximum articles limit of %d", max_articles)
                break
                
        if max_articles and count >= max_articles:
            break
            
        next_url = data.get("next_page")
        if next_url:
            time.sleep(CRAWL_DELAY)
            
    logger.info("Scraping complete. Total articles scraped: %d", count)
