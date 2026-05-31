"""
Uploads Markdown files to an OpenAI Vector Store with delta detection.

Delta logic:
  - Hashes for each article are stored in state/article_hashes.json
    keyed by article slug → {hash, file_id}.
  - On each run:
      New article                          → upload & store hash + file_id
      Changed article                      → delete old file, re-upload, update hash + file_id
      Unchanged, present in vector store   → skip
      Unchanged, deleted from vector store → re-upload (treat as new)
  - Logs a summary: Added | Updated | Skipped
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from pathlib import Path

import openai
from openai import AuthenticationError

logger = logging.getLogger(__name__)

STATE_DIR = "state"
STATE_FILE = os.path.join(STATE_DIR, "article_hashes.json")


def _md5(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def load_state() -> dict:
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


def _fetch_remote_file_ids(
    client: openai.OpenAI, vector_store_id: str
) -> set[str]:
    """
    Return the set of file IDs currently attached to the vector store.
    Handles pagination so no files are missed.
    """
    remote_ids: set[str] = set()
    after: str | None = None
    while True:
        params: dict = {"limit": 100}
        if after:
            params["after"] = after
        try:
            page = client.vector_stores.files.list(
                vector_store_id=vector_store_id, **params
            )
        except Exception as exc:
            logger.warning(
                "Could not list vector store files (skipping remote check): %s", exc
            )
            break
        for vf in page.data:
            remote_ids.add(vf.id)
        if not page.has_more:
            break
        after = page.data[-1].id
    return remote_ids


# Auto-chunking parameters (mirrors OpenAI's "auto" defaults)
_CHUNK_TOKENS = 800
_CHUNK_OVERLAP = 400
_CHARS_PER_TOKEN = 4  # rough but consistent estimate


def _estimate_chunks(filepath: str) -> int:
    """
    Estimate the number of chunks OpenAI will create for a file.

    Formula (mirrors the auto strategy: 800-token chunks with 400-token overlap):
        chunks = max(1, ceil((total_tokens - chunk_size) / stride) + 1)
    where stride = chunk_size - overlap = 800 - 400 = 400.
    """
    char_count = Path(filepath).stat().st_size
    total_tokens = char_count / _CHARS_PER_TOKEN
    if total_tokens <= _CHUNK_TOKENS:
        return 1
    stride = _CHUNK_TOKENS - _CHUNK_OVERLAP  # 400
    return math.ceil((total_tokens - _CHUNK_TOKENS) / stride) + 1


def _upload_file(
    client: openai.OpenAI, vector_store_id: str, filepath: str
) -> tuple[str, int]:
    """
    Upload a single file to the vector store using OpenAI's auto chunking strategy
    (800-token chunks, 400-token overlap).

    Returns:
        (file_id, estimated_chunk_count)
    """
    chunks = _estimate_chunks(filepath)
    with open(filepath, "rb") as f:
        response = client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store_id,
            file=(os.path.basename(filepath), f, "text/plain"),
        )
    return response.id, chunks


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
            "Invalid OpenAI API key — aborting upload. "
        )
        raise

    state = load_state()
    added = updated = skipped = errors = 0
    files_embedded = 0   # files actually uploaded this run
    chunks_embedded = 0  # estimated chunks for those files

    # Fetch the live file IDs from the vector store once.
    # This lets us detect articles that were manually deleted from the store
    # even when their content hash hasn't changed.
    logger.debug("Fetching remote file list from vector store %s ...", vector_store_id)
    remote_file_ids = _fetch_remote_file_ids(client, vector_store_id)
    logger.debug("Remote vector store contains %d file(s).", len(remote_file_ids))

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
                file_id = existing.get("file_id")
                if file_id and file_id in remote_file_ids:
                    # Content unchanged AND file still present remotely → skip
                    skipped += 1
                    logger.debug("Skipped (unchanged): %s", slug)
                    continue
                # Content unchanged BUT file was deleted from the vector store
                # (or no file_id recorded) → fall through to re-upload as new
                logger.info(
                    "Re-uploading (missing from vector store): %s", slug
                )

            if existing and existing.get("file_id"):
                # Changed — delete old, re-upload
                _delete_from_vector_store(
                    client, vector_store_id, existing["file_id"]
                )
                file_id, chunk_count = _upload_file(client, vector_store_id, filepath)
                state[slug] = {"hash": current_version, "file_id": file_id}
                _save_state(state)
                updated += 1
                files_embedded += 1
                chunks_embedded += chunk_count
                logger.info("Updated: %s (~%d chunk(s))", slug, chunk_count)
            else:
                # New article
                file_id, chunk_count = _upload_file(client, vector_store_id, filepath)
                state[slug] = {"hash": current_version, "file_id": file_id}
                _save_state(state)
                added += 1
                files_embedded += 1
                chunks_embedded += chunk_count
                logger.info("Added:   %s (~%d chunk(s))", slug, chunk_count)

        except AuthenticationError:
            raise
        except Exception as exc:
            errors += 1
            logger.error("Error processing %s: %s", slug, exc)

    summary = {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "files_embedded": files_embedded,
        "chunks_embedded": chunks_embedded,
    }
    if files_embedded > 0:
        logger.info(
            "Embedded %d file(s), ~%d chunk(s) this run",
            files_embedded,
            chunks_embedded,
        )
    logger.info("Upload complete!")
    return summary
