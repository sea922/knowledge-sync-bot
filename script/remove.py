import os
import requests

api_key = ""

headers = {
    "Authorization": f"Bearer {api_key}"
}

# List files
resp = requests.get(
    "https://api.openai.com/v1/files",
    headers=headers,
)
resp.raise_for_status()

for file in resp.json()["data"]:
    file_id = file["id"]

    print("Deleting", file_id)

    r = requests.delete(
        f"https://api.openai.com/v1/files/{file_id}",
        headers=headers,
    )
    print(r.status_code)