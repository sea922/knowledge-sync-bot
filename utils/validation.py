"""
Environment variable validation helpers for the OptiBot Mini pipeline.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def validate_env() -> tuple[str, str, str]:
    """
    Validate required environment variables and return them.
    VECTOR_STORE_ID and ASSISTANT_ID are optional — if missing, the pipeline
    will auto-create them.

    Returns:
        tuple of (api_key, vector_store_id, assistant_id)
        vector_store_id and assistant_id may be empty strings.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    vector_store_id = os.environ.get("VECTOR_STORE_ID", "").strip()
    assistant_id = os.environ.get("ASSISTANT_ID", "").strip()

    if not api_key:
        logger.error("Missing required environment variable: OPENAI_API_KEY")
        logger.error("Please copy .env.sample to .env and fill in the missing values.")
        sys.exit(1)

    if not vector_store_id:
        logger.warning(
            "VECTOR_STORE_ID not set — a new Vector Store will be created automatically."
        )
    if not assistant_id:
        logger.warning(
            "ASSISTANT_ID not set — a new Assistant will be created automatically."
        )

    return api_key, vector_store_id, assistant_id
