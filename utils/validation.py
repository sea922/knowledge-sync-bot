"""
Environment variable validation helpers for the OptiBot Mini pipeline.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def validate_env() -> tuple[str, str]:
    """
    Validate required environment variables and return them.
    Exits the process with code 1 if required variables are missing.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    vector_store_id = os.environ.get("VECTOR_STORE_ID", "").strip()

    missing = []
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if not vector_store_id:
        missing.append("VECTOR_STORE_ID")

    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Please copy .env.sample to .env and fill in the missing values.")
        sys.exit(1)

    return api_key, vector_store_id
