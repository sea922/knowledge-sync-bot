"""
Prometheus metric definitions and push helper for the OptiBot Mini pipeline.

All metrics are pushed to a Prometheus Pushgateway at the end of each run.
If PUSHGATEWAY_URL is not set, push_metrics() is a no-op — safe to call always.

Metrics exposed:
    pipeline_last_run_success          — Gauge: 1=success, 0=failure
    pipeline_last_run_timestamp        — Gauge: Unix timestamp of last run
    pipeline_articles_scraped_total    — Gauge: count of scraped articles
    pipeline_articles_converted_total  — Gauge: count of successfully converted articles
    pipeline_upload_total{status}      — Gauge: upload counts by status (added/updated/skipped/errors)
    pipeline_phase_duration_seconds{phase} — Gauge: duration of each phase in seconds
"""

from __future__ import annotations

import logging
import os
import time

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

logger = logging.getLogger(__name__)

# Job name used as the Pushgateway grouping key.
# Each push overwrites the previous values for this job — correct for batch jobs.
_JOB_NAME = "optibot_pipeline"


class PipelineMetrics:
    """Container for all pipeline Prometheus metrics, using a private registry."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()

        self.last_run_success = Gauge(
            "pipeline_last_run_success",
            "1 if the last pipeline run succeeded, 0 if it failed",
            registry=self.registry,
        )
        self.last_run_timestamp = Gauge(
            "pipeline_last_run_timestamp",
            "Unix timestamp of the last pipeline run completion",
            registry=self.registry,
        )
        self.articles_scraped = Gauge(
            "pipeline_articles_scraped_total",
            "Number of articles scraped from the Zendesk API in the last run",
            registry=self.registry,
        )
        self.articles_converted = Gauge(
            "pipeline_articles_converted_total",
            "Number of articles successfully converted to Markdown in the last run",
            registry=self.registry,
        )
        self.upload_total = Gauge(
            "pipeline_upload_total",
            "Number of files processed by the uploader, by status",
            labelnames=["status"],
            registry=self.registry,
        )
        self.phase_duration = Gauge(
            "pipeline_phase_duration_seconds",
            "Duration of each pipeline phase in seconds",
            labelnames=["phase"],
            registry=self.registry,
        )

    def record_upload_summary(self, summary: dict) -> None:
        """Record upload counts from the upload_delta() summary dict."""
        for status in ("added", "updated", "skipped", "errors"):
            self.upload_total.labels(status=status).set(summary.get(status, 0))

    def push(self, gateway_url: str | None = None) -> None:
        """
        Push all metrics to the Pushgateway.

        Uses the PUSHGATEWAY_URL env var if gateway_url is not provided.
        No-op (with a warning) if the URL is not configured.
        """
        url = gateway_url or os.environ.get("PUSHGATEWAY_URL", "").strip()
        if not url:
            logger.debug("PUSHGATEWAY_URL not set — skipping metrics push")
            return

        try:
            self.last_run_timestamp.set(time.time())
            push_to_gateway(url, job=_JOB_NAME, registry=self.registry)
            logger.info("Metrics pushed to Pushgateway at %s", url)
        except Exception as exc:
            # Never let observability failures crash the pipeline
            logger.warning("Failed to push metrics to Pushgateway: %s", exc)
