"""
-----------
Orchestrator class for the OptiBot Mini knowledge synchronization pipeline.
"""

from __future__ import annotations

import logging
import time

from openai import AuthenticationError

import os

from scraper.scraper import scrape_articles
from converter.markdown import convert_article, ARTICLES_DIR
from uploader.vector_store import upload_delta, load_state
from observability.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class KnowledgeSyncPipeline:
    """Manages the end-to-end sync workflow: Scrape -> Convert -> Upload Delta."""

    def __init__(self, api_key: str, vector_store_id: str) -> None:
        self.api_key = api_key
        self.vector_store_id = vector_store_id
        # Initialize metrics early so we can record failure states if needed
        self.metrics = PipelineMetrics()

    def run(self) -> bool:
        """
        Executes the full pipeline.
        
        Returns:
            True if pipeline runs successfully with zero errors, False otherwise.
        """
        pipeline_start = time.perf_counter()
        success = False

        try:
            # Phase 1: Scrape
            logger.info("[Phase 1] Scraping articles from support.optisigns.com ...")
            
            articles: list[dict] = []
            md_paths: list[str] = []

            scrape_start = time.perf_counter()
            for article in scrape_articles(100):
                articles.append(article)
            scrape_duration = time.perf_counter() - scrape_start

            self.metrics.articles_scraped.set(len(articles))
            self.metrics.phase_duration.labels(phase="scrape").set(round(scrape_duration, 3))
            logger.info("Scrape complete: %d articles in %.1fs", len(articles), scrape_duration)

            # Phase 2: Convert
            # Articles whose content changed (or are new) are converted and written to disk.
            # Articles that are unchanged are NOT re-converted, but their existing .md paths
            # are still collected so Phase 3 can verify they still exist in the vector store
            # (a user may have manually deleted them there).
            state = load_state()
            convert_start = time.perf_counter()
            skipped_convert = 0
            for article in articles:
                slug = article.get("slug")
                updated_at = article.get("updated_at") or ""
                existing = state.get(slug)

                if existing and updated_at and existing.get("hash") == updated_at:
                    existing_md = os.path.abspath(
                        os.path.join(ARTICLES_DIR, f"{slug}.md")
                    )
                    if os.path.exists(existing_md):
                        # Content unchanged AND .md on disk → skip re-conversion,
                        # but keep the path so Phase 3 can verify remote existence.
                        md_paths.append(existing_md)
                        skipped_convert += 1
                        continue
                    # Content unchanged BUT .md missing from disk → fall through
                    # to convert_article so the file is regenerated before upload.
                    logger.info(
                        "Re-converting (missing .md on disk): %s", slug
                    )

                try:
                    path = convert_article(article)
                    md_paths.append(path)
                except Exception as exc:
                    logger.error("Conversion failed for '%s': %s", article.get("title"), exc)
            convert_duration = time.perf_counter() - convert_start

            self.metrics.articles_converted.set(len(md_paths))
            self.metrics.phase_duration.labels(phase="convert").set(round(convert_duration, 3))
            logger.info(
                "[Phase 2] Convert complete: %d/%d articles in %.1fs (Skipped convert: %d)",
                len(md_paths), len(articles), convert_duration, skipped_convert
            )

            if not md_paths:
                logger.error("No articles to upload (no .md files found).")
                return False

            # Phase 3: Upload delta to Vector Store
            logger.info("[Phase 3] Uploading delta to Vector Store %s ...", self.vector_store_id)

            upload_start = time.perf_counter()
            
            updated_at_map = {a["slug"]: a.get("updated_at") or "" for a in articles}
            
            summary = upload_delta(
                filepaths=md_paths,
                vector_store_id=self.vector_store_id,
                updated_at_map=updated_at_map,
                openai_api_key=self.api_key,
            )
            upload_duration = time.perf_counter() - upload_start

            self.metrics.record_upload_summary(summary)
            self.metrics.phase_duration.labels(phase="upload").set(round(upload_duration, 3))

            logger.info(
                "Added: %(added)d | Updated: %(updated)d | "
                "Skipped: %(skipped)d | Errors: %(errors)d",
                summary,
            )

            if summary["errors"] > 0:
                logger.error("Pipeline finished with %d upload error(s).", summary["errors"])
                return False

            success = True
            return True

        except AuthenticationError:
            return False

        except Exception as exc:
            logger.exception("Unhandled error during pipeline execution: %s", exc)
            return False

        finally:
            # Always push metrics — even on failure — so the dashboard reflects the status
            total_duration = time.perf_counter() - pipeline_start
            self.metrics.last_run_success.set(1 if success else 0)
            self.metrics.phase_duration.labels(phase="total").set(round(total_duration, 3))
            self.metrics.push()
