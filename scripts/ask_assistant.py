"""
Ask the OptiBot Assistant a question and display the response.

Uses the OpenAI Responses API (the modern replacement for the deprecated
Assistants/Threads API) with the file_search tool pointed at the project's
Vector Store.

Usage:
    python scripts/ask_assistant.py
    python scripts/ask_assistant.py "Your custom question here"

Reads OPENAI_API_KEY and VECTOR_STORE_ID from .env (or environment).
Falls back to state/resources.json when env vars are not set.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

# System prompt mirrors the one used when the assistant was originally created
# (see uploader/setup.py) so answers are consistent in tone and format.
SYSTEM_PROMPT = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    '• Cite up to 3 "Article URL:" lines per reply.'
)

MODEL = "gpt-4o-mini"

def _load_dotenv() -> None:
    """Minimal .env loader — no external dependencies required."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _get_vector_store_id() -> str:
    """Return vector store ID from env or state/resources.json."""
    vs_id = os.environ.get("VECTOR_STORE_ID", "").strip()
    if vs_id:
        return vs_id

    resources_path = os.path.join(PROJECT_ROOT, "state", "resources.json")
    if os.path.exists(resources_path):
        try:
            with open(resources_path, encoding="utf-8") as f:
                data = json.load(f)
            vs_id = data.get("vector_store_id", "").strip()
            if vs_id:
                print(f"[info] Using vector store ID from state/resources.json: {vs_id}")
                return vs_id
        except Exception as exc:
            print(f"[warn] Could not read state/resources.json: {exc}")

    return ""


def _print_sep(char: str = "─", width: int = 60) -> None:
    print(char * width)



def ask(question: str) -> None:
    """Send *question* to OptiBot via the Responses API and display the answer."""
    try:
        from openai import OpenAI
    except ImportError:
        print("[error] openai package is not installed. Run: pip install openai")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("[error] OPENAI_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    vector_store_id = _get_vector_store_id()
    if not vector_store_id:
        print(
            "[error] No Vector Store ID found.\n"
            "  Set VECTOR_STORE_ID in .env, or run `python main.py` once to auto-create it."
        )
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    _print_sep()
    print(f"  Question : {question}")
    _print_sep()
    print(f"  Model    : {MODEL}")
    print(f"  Store    : {vector_store_id}")
    _print_sep()
    print("  Waiting for OptiBot...")

    start = time.perf_counter()

    try:
        # Single stateless call — no threads, no runs, no polling
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=question,
            tools=[{
                "type": "file_search",
                "vector_store_ids": [vector_store_id],
            }],
        )
    except Exception as exc:
        err = str(exc)
        print(f"\n[error] API call failed: {err}")
        if "quota" in err.lower() or "rate_limit" in err.lower() or "insufficient_quota" in err.lower():
            print(
                "\n[hint] Your API key has exceeded its quota.\n"
                "  • Top up your account at https://platform.openai.com/account/billing\n"
                "  • Or set a different OPENAI_API_KEY in .env"
            )
        sys.exit(1)

    elapsed = time.perf_counter() - start

    # response.output_text is the convenience property for plain-text output
    reply_text = (response.output_text or "").strip()
    if not reply_text:
        print("\n[warn] The assistant returned an empty response.")
        sys.exit(1)

    _print_sep()
    print("  OptiBot Answer:")
    _print_sep()
    for line in reply_text.splitlines():
        if line.strip():
            print(textwrap.fill(line, width=76, subsequent_indent="    "))
        else:
            print()
    _print_sep()
    print(f"  Response received in {elapsed:.1f}s")
    _print_sep()


if __name__ == "__main__":
    _load_dotenv()

    # Accept an optional question from the command line; fall back to the
    # task-specified question for the take-home test.
    user_question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How do I add a YouTube video?"
    ask(user_question)
