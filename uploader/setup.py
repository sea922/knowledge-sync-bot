"""
Auto-provisions the OpenAI Vector Store and Assistant if their IDs are not
provided via environment variables. The generated IDs are persisted to the
state/ directory so subsequent runs re-use the same resources.
"""

from __future__ import annotations

import json
import logging
import os

import openai

logger = logging.getLogger(__name__)

STATE_DIR = "state"
RESOURCES_FILE = os.path.join(STATE_DIR, "resources.json")

VECTOR_STORE_NAME = "OptiBot-Knowledge-Base"
ASSISTANT_NAME = "OptiBot Mini"
ASSISTANT_INSTRUCTIONS = """\
You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.\
"""


def _load_resources() -> dict:
    os.makedirs(STATE_DIR, exist_ok=True)
    if not os.path.exists(RESOURCES_FILE):
        return {}
    with open(RESOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_resources(resources: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(RESOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(resources, f, indent=2)


def ensure_vector_store(client: openai.OpenAI, vector_store_id: str) -> str:
    """
    Return the given vector_store_id if provided.
    Otherwise, look it up in the persisted state or create a new one.
    """
    if vector_store_id:
        return vector_store_id

    resources = _load_resources()
    if resources.get("vector_store_id"):
        vs_id = resources["vector_store_id"]
        logger.info("Re-using existing Vector Store from state: %s", vs_id)
        return vs_id

    logger.info("VECTOR_STORE_ID not set — creating a new Vector Store '%s'...", VECTOR_STORE_NAME)
    vs = client.vector_stores.create(name=VECTOR_STORE_NAME)
    resources["vector_store_id"] = vs.id
    _save_resources(resources)
    logger.info("Created Vector Store: %s", vs.id)
    return vs.id


def ensure_assistant(client: openai.OpenAI, assistant_id: str, vector_store_id: str) -> str:
    """
    Return the given assistant_id if provided.
    Otherwise, look it up in the persisted state or create a new one linked
    to the vector store.
    """
    if assistant_id:
        return assistant_id

    resources = _load_resources()
    if resources.get("assistant_id"):
        asst_id = resources["assistant_id"]
        logger.info("Re-using existing Assistant from state: %s", asst_id)
        return asst_id

    logger.info("ASSISTANT_ID not set — creating a new Assistant '%s'...", ASSISTANT_NAME)
    assistant = client.beta.assistants.create(
        name=ASSISTANT_NAME,
        instructions=ASSISTANT_INSTRUCTIONS,
        model="gpt-4o-mini",
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    )
    resources["assistant_id"] = assistant.id
    _save_resources(resources)
    logger.info("Created Assistant: %s", assistant.id)
    return assistant.id
