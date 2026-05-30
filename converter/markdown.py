"""
Converts a raw article dict (from scraper) to clean Markdown and saves it to disk.

Conversion steps:
  1. Parse body HTML with BeautifulSoup for pre-cleaning.
  2. Fix relative links → absolute URLs.
  3. Strip noise (nav, header, footer, ads).
  4. Run markdownify to convert HTML → Markdown.
  5. Post-process: collapse excessive blank lines, clean up artefacts.
  6. Prepend a front-matter header with title and source URL.
  7. Write to articles/<slug>.md.
"""

from __future__ import annotations

import logging
import os
import re

from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger(__name__)

BASE_URL = "https://support.optisigns.com"
ARTICLES_DIR = "articles"


def _fix_relative_links(soup: BeautifulSoup) -> None:
    """Convert relative href and src attributes to absolute URLs in-place."""
    for tag in soup.find_all(href=True):
        href = tag["href"]
        if href.startswith("/"):
            tag["href"] = BASE_URL + href

    for tag in soup.find_all(src=True):
        src = tag["src"]
        if src.startswith("/"):
            tag["src"] = BASE_URL + src


def _clean_html(html: str) -> BeautifulSoup:
    """Parse HTML, remove noise elements, and fix relative links."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise tags
    for noise in soup.find_all(
        ["nav", "header", "footer", "aside", "form", "script", "style", "iframe"]
    ):
        noise.decompose()

    # Remove elements that look like breadcrumbs or feedback widgets
    for el in soup.find_all(True):
        classes = " ".join(el.get("class", []))
        if any(
            kw in classes
            for kw in [
                "breadcrumb",
                "feedback",
                "vote",
                "share",
                "social",
                "related",
                "sidebar",
                "navigation",
                "cookie",
            ]
        ):
            el.decompose()

    _fix_relative_links(soup)
    return soup


def _post_process(text: str) -> str:
    """Clean up raw markdownify output."""
    # Collapse 3+ consecutive blank lines to max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove trailing whitespace on each line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def convert_article(article: dict, output_dir: str = ARTICLES_DIR) -> str:
    """
    Convert an article dict to Markdown and write it to disk.

    Args:
        article: dict with keys: title, html_url, slug, body_html
        output_dir: directory to write the .md file (default: articles/)

    Returns:
        Absolute path to the written .md file.
    """
    os.makedirs(output_dir, exist_ok=True)

    soup = _clean_html(article["body_html"])

    # markdownify with ATX-style headings (# ## ###)
    raw_md = md(str(soup), heading_style="ATX", bullets="-")

    body = _post_process(raw_md)

    # Compose final document
    front_matter = (
        f"# {article['title']}\n\n"
        f"> **Source:** {article['html_url']}\n\n"
        "---\n\n"
    )
    content = front_matter + body

    slug = article["slug"] or "untitled"
    filepath = os.path.join(output_dir, f"{slug}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.debug("Wrote %s (%d chars)", filepath, len(content))
    return os.path.abspath(filepath)


def convert_all(articles: list[dict], output_dir: str = ARTICLES_DIR) -> list[str]:
    """
    Convert a list of article dicts to Markdown files.

    Args:
        articles: list of article dicts from the scraper
        output_dir: directory to write .md files

    Returns:
        List of absolute file paths written.
    """
    paths: list[str] = []
    for article in articles:
        try:
            path = convert_article(article, output_dir)
            paths.append(path)
        except Exception as exc:
            logger.error("Error converting '%s': %s", article.get("title"), exc)
    logger.info("Converted %d articles to Markdown in '%s/'", len(paths), output_dir)
    return paths
