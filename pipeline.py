"""
-----------
Orchestrator class for the OptiBot Mini knowledge synchronization pipeline.
"""

from __future__ import annotations

import logging
import time

from scraper.scraper import scrape_articles
from converter.markdown import convert_article
from uploader.vector_store import upload_delta
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
            for article in scrape_articles():
                articles.append(article)
            scrape_duration = time.perf_counter() - scrape_start

            self.metrics.articles_scraped.set(len(articles))
            self.metrics.phase_duration.labels(phase="scrape").set(round(scrape_duration, 3))
            logger.info("Scrape complete: %d articles in %.1fs", len(articles), scrape_duration)

            # Phase 2: Convert
            convert_start = time.perf_counter()
            for article in articles:
                try:
                    path = convert_article(article)
                    md_paths.append(path)
                except Exception as exc:
                    logger.error("Conversion failed for '%s': %s", article.get("title"), exc)
            convert_duration = time.perf_counter() - convert_start

            self.metrics.articles_converted.set(len(md_paths))
            self.metrics.phase_duration.labels(phase="convert").set(round(convert_duration, 3))
            logger.info(
                "Convert complete: %d/%d articles in %.1fs",
                len(md_paths), len(articles), convert_duration,
            )

            if len(md_paths) < 30:
                logger.warning(
                    "WARNING: Only %d articles collected (target >= 30). "
                    "The site structure may have changed.",
                    len(md_paths),
                )

            if not md_paths:
                logger.error("No articles to upload.")
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

        except Exception as exc:
            logger.exception("Unhandled error during pipeline execution: %s", exc)
            return False

        finally:
            # Always push metrics — even on failure — so the dashboard reflects the status
            total_duration = time.perf_counter() - pipeline_start
            self.metrics.last_run_success.set(1 if success else 0)
            self.metrics.phase_duration.labels(phase="total").set(round(total_duration, 3))
            self.metrics.push()
