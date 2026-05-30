"""
Uploads Markdown files to an OpenAI Vector Store with delta detection.

Delta logic:
  - Hashes for each article are stored in state/article_hashes.json
    keyed by article slug → {hash, file_id}.
  - On each run:
      New article     → upload & store hash + file_id
      Changed article → delete old file, re-upload, update hash + file_id
      Unchanged       → skip
  - Logs a summary: Added | Updated | Skipped
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import openai
from openai import AuthenticationError

logger = logging.getLogger(__name__)

STATE_DIR = "state"
STATE_FILE = os.path.join(STATE_DIR, "article_hashes.json")


def _md5(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _load_state() -> dict:
    """Load the persisted hash map from disk."""
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    """Persist the hash map to disk."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _delete_from_vector_store(
    client: openai.OpenAI, vector_store_id: str, file_id: str
) -> None:
    """Delete a file from the vector store (and the Files API)."""
    try:
        client.vector_stores.files.delete(
            vector_store_id=vector_store_id,
            file_id=file_id,
        )
        client.files.delete(file_id)
        logger.debug("Deleted file %s from vector store", file_id)
    except Exception as exc:
        logger.warning("Could not delete file %s: %s", file_id, exc)


def _upload_file(
    client: openai.OpenAI, vector_store_id: str, filepath: str
) -> str:
    """
    Upload a single file to the vector store using OpenAI's chunking (auto strategy).
    Returns the file_id of the newly uploaded file.
    """
    with open(filepath, "rb") as f:
        response = client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store_id,
            file=(os.path.basename(filepath), f, "text/plain"),
        )
    return response.id


def upload_delta(
    filepaths: list[str],
    vector_store_id: str,
    updated_at_map: dict[str, str] | None = None,
    openai_api_key: str | None = None,
) -> dict:
    """
    Upload only new or changed Markdown files to the OpenAI Vector Store.

    Args:
        filepaths: list of absolute paths to .md files
        vector_store_id: the Vector Store ID (vs_...)
        openai_api_key: optional; falls back to OPENAI_API_KEY env var

    Returns:
        dict with counts: added, updated, skipped, errors
    """
    client = openai.OpenAI(api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"))

    # Preflight: validate key before doing any real work
    try:
        client.models.list()
    except AuthenticationError:
        logger.error(
            "Invalid or missing OpenAI API key — aborting upload. "
        )
        raise

    state = _load_state()
    added = updated = skipped = errors = 0

    for filepath in filepaths:
        slug = Path(filepath).stem
        try:
            if updated_at_map and updated_at_map.get(slug):
                current_version = updated_at_map[slug]
            else:
                content = Path(filepath).read_text(encoding="utf-8")
                current_version = _md5(content)

            existing = state.get(slug)

            if existing and existing.get("hash") == current_version:
                skipped += 1
                logger.debug("Skipped (unchanged): %s", slug)
                continue

            if existing and existing.get("file_id"):
                # Changed — delete old, re-upload
                _delete_from_vector_store(
                    client, vector_store_id, existing["file_id"]
                )
                file_id = _upload_file(client, vector_store_id, filepath)
                state[slug] = {"hash": current_version, "file_id": file_id}
                updated += 1
                logger.info("Updated: %s", slug)
            else:
                # New article
                file_id = _upload_file(client, vector_store_id, filepath)
                state[slug] = {"hash": current_version, "file_id": file_id}
                added += 1
                logger.info("Added:   %s", slug)

        except AuthenticationError:
            raise
        except Exception as exc:
            errors += 1
            logger.error("Error processing %s: %s", slug, exc)

    _save_state(state)

    summary = {"added": added, "updated": updated, "skipped": skipped, "errors": errors}
    logger.info(
        "Upload complete - Added: %d | Updated: %d | Skipped: %d | Errors: %d",
        added,
        updated,
        skipped,
        errors,
    )
    return summary
