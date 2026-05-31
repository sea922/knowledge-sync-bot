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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    except Exception as exc:
        logger.debug("Could not delete from vector store (might already be detached): %s", exc)

    try:
        client.files.delete(file_id)
        logger.debug("Deleted file %s from OpenAI Files API", file_id)
    except Exception as exc:
        logger.debug("Could not delete from OpenAI Files API: %s", exc)
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

MAX_UPLOAD_WORKERS = 10


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


def _process_one_file(
    filepath: str,
    client: openai.OpenAI,
    vector_store_id: str,
    updated_at_map: dict[str, str] | None,
    state: dict,
    state_lock: threading.Lock,
    remote_file_ids: set[str],
) -> dict:
    slug = Path(filepath).stem
    try:
        if updated_at_map and updated_at_map.get(slug):
            current_version = updated_at_map[slug]
        else:
            content = Path(filepath).read_text(encoding="utf-8")
            current_version = _md5(content)

        existing = state.get(slug)

        # ── Case 1: unchanged content ──────────────────────────────────────
        if existing and existing.get("hash") == current_version:
            file_id = existing.get("file_id")

            if file_id and file_id in remote_file_ids:
                # Unchanged AND still in vector store → nothing to do
                logger.debug("Skipped (unchanged): %s", slug)
                return {"action": "skipped", "slug": slug, "chunks": 0, "file_id": None}

            # Unchanged BUT file was deleted from the vector store.
            # The file is already gone — just upload a fresh copy.
            # No delete call needed (and no 404 risk).
            logger.info("Re-uploading (missing from vector store): %s", slug)
            file_id, chunk_count = _upload_file(client, vector_store_id, filepath)
            with state_lock:
                state[slug] = {"hash": current_version, "file_id": file_id}
                _save_state(state)
            logger.info("Added:   %s (~%d chunk(s))", slug, chunk_count)
            return {"action": "added", "slug": slug, "chunks": chunk_count, "file_id": file_id}

        # ── Case 2: content changed, old file exists ───────────────────────
        if existing and existing.get("file_id"):
            _delete_from_vector_store(client, vector_store_id, existing["file_id"])
            file_id, chunk_count = _upload_file(client, vector_store_id, filepath)
            with state_lock:
                state[slug] = {"hash": current_version, "file_id": file_id}
                _save_state(state)
            logger.info("Updated: %s (~%d chunk(s))", slug, chunk_count)
            return {"action": "updated", "slug": slug, "chunks": chunk_count, "file_id": file_id}

        # ── Case 3: brand-new article ──────────────────────────────────────
        file_id, chunk_count = _upload_file(client, vector_store_id, filepath)
        with state_lock:
            state[slug] = {"hash": current_version, "file_id": file_id}
            _save_state(state)
        logger.info("Added:   %s (~%d chunk(s))", slug, chunk_count)
        return {"action": "added", "slug": slug, "chunks": chunk_count, "file_id": file_id}

    except AuthenticationError:
        raise  # Propagate immediately so the caller can cancel other workers
    except Exception as exc:
        logger.error("Error processing %s: %s", slug, exc)
        return {"action": "error", "slug": slug, "chunks": 0, "file_id": None}


def _upload_file(
    client: openai.OpenAI, vector_store_id: str, filepath: str
) -> tuple[str, int]:
    """
    Upload a single file to the vector store using OpenAI's auto chunking strategy
    Upload a single file to OpenAI's Files API (does not attach to vector store).

    Returns:
        (file_id, estimated_chunk_count)
    """
    chunks = _estimate_chunks(filepath)
    with open(filepath, "rb") as f:
        response = client.files.create(
            file=(os.path.basename(filepath), f, "text/plain"),
            purpose="assistants",
        )
    return response.id, chunks


def upload_delta(
    filepaths: list[str],
    vector_store_id: str,
    updated_at_map: dict[str, str] | None = None,
    openai_api_key: str | None = None,
    max_workers: int = MAX_UPLOAD_WORKERS,
) -> dict:
    """
    Upload only new or changed Markdown files to the OpenAI Vector Store.

    Args:
        filepaths: list of absolute paths to .md files
        vector_store_id: the Vector Store ID (vs_...)
        openai_api_key: optional; falls back to OPENAI_API_KEY env var
        max_workers: max parallel upload threads

    Returns:
        dict with counts: added, updated, skipped, errors
    """
    client = openai.OpenAI(api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"))

    # Preflight: validate key before doing any real work
    try:
        client.models.list()
    except AuthenticationError:
        logger.error("Invalid OpenAI API key — aborting upload.")
        raise

    state = load_state()
    state_lock = threading.Lock()

    # Fetch the live file IDs from the vector store once.
    # This lets us detect articles that were manually deleted from the store
    # even when their content hash hasn't changed.
    logger.debug("Fetching remote file list from vector store %s ...", vector_store_id)
    remote_file_ids = _fetch_remote_file_ids(client, vector_store_id)
    logger.debug("Remote vector store contains %d file(s).", len(remote_file_ids))

    results: list[dict] = []
    logger.info(
        "Processing %d file(s) with up to %d parallel worker(s) ...",
        len(filepaths), max_workers,
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_one_file,
                fp, client, vector_store_id, updated_at_map,
                state, state_lock, remote_file_ids,
            ): fp
            for fp in filepaths
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except AuthenticationError:
                for f in futures:
                    f.cancel()
                raise
            except Exception as exc:
                slug = Path(futures[future]).stem
                logger.error("Unexpected error for %s: %s", slug, exc)
                results.append({"action": "error", "slug": slug, "chunks": 0})

    added    = sum(1 for r in results if r["action"] == "added")
    updated  = sum(1 for r in results if r["action"] == "updated")
    skipped  = sum(1 for r in results if r["action"] == "skipped")
    errors   = sum(1 for r in results if r["action"] == "error")
    files_embedded  = added + updated
    chunks_embedded = sum(r["chunks"] for r in results if r["action"] in ("added", "updated"))

    # Now that all files are uploaded, attach them to the vector store in ONE batch!
    batch_file_ids = [r["file_id"] for r in results if r["action"] in ("added", "updated") and r.get("file_id")]
    if batch_file_ids:
        logger.info(
            "Attaching %d uploaded file(s) to vector store in a single batch...",
            len(batch_file_ids)
        )
        try:
            client.vector_stores.file_batches.create_and_poll(
                vector_store_id=vector_store_id,
                file_ids=batch_file_ids
            )
            logger.info("Batch processing complete!")
        except Exception as exc:
            logger.error("Failed to process file batch in vector store: %s", exc)
            # We don't fail the entire script here; files are uploaded and recorded in state.
            # Next run they'll be retried under "missing from vector store".

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
