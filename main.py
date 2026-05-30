from __future__ import annotations

import logging
import os
import sys

import openai
from dotenv import load_dotenv

from pipeline import KnowledgeSyncPipeline
from uploader.setup import ensure_vector_store, ensure_assistant
from utils.logging_config import setup_logging
from utils.validation import validate_env

# Initialize logging configuration at startup
setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()


def main() -> None:
    logger.info("=" * 60)
    logger.info("OptiBot Mini — Knowledge Sync Pipeline")
    logger.info("=" * 60)

    api_key, vector_store_id, assistant_id = validate_env()

    # Auto-provision resources if IDs are missing
    client = openai.OpenAI(api_key=api_key)
    vector_store_id = ensure_vector_store(client, vector_store_id)
    assistant_id = ensure_assistant(client, assistant_id, vector_store_id)

    logger.info("Vector Store ID : %s", vector_store_id)
    logger.info("Assistant ID    : %s", assistant_id)

    # Instantiate and run the pipeline
    pipeline = KnowledgeSyncPipeline(api_key=api_key, vector_store_id=vector_store_id)
    success = pipeline.run()

    if not success:
        logger.error("Pipeline execution failed.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Pipeline complete. Exiting 0.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
