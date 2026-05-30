import os
from typing import Any

from openai import OpenAI

client = OpenAI(
    api_key= "sk-proj--"
)

def list_all_vector_store_files(vector_store_id: str):
    all_files = []
    after = None

    while True:
        params: dict[str, Any] = {}
        if after:
            params["after"] = after

        resp = client.vector_stores.files.list(
            vector_store_id=vector_store_id,
            limit=100,
            **params,
        )

        all_files.extend(resp.data)

        if not resp.has_more:
            break

        after = resp.data[-1].id

    return all_files


def clear_vector_store(vector_store_id: str, delete_store: bool = False):
    print(f"Listing files in vector store: {vector_store_id}...")
    files = list_all_vector_store_files(vector_store_id)
    print(f"Found {len(files)} files in the vector store.")

    for f in files:
        file_id = getattr(f, "file_id", None) or f.id

        print(f"Deleting {file_id}")

        try:
            client.vector_stores.files.delete(
                vector_store_id=vector_store_id,
                file_id=file_id,
            )
        except Exception as e:
            print(f"Detach failed: {e}")

        try:
            client.files.delete(file_id)
        except Exception as e:
            print(f"File delete failed: {e}")

    if delete_store:
        client.vector_stores.delete(vector_store_id)
        print(f"Deleted vector store {vector_store_id}")


clear_vector_store("vs_6a1b14b0f0688191b2883280e6fbf476")