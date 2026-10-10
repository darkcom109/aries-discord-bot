import os
from pathlib import Path

import requests
from dotenv import load_dotenv

project_directory = Path(__file__).resolve().parents[1]
load_dotenv(project_directory / "discord-bot" / ".env")
load_dotenv(project_directory / ".env")

api_key = os.getenv("OLLAMA_API_KEY")
if not api_key:
    raise RuntimeError("OLLAMA_API_KEY is missing from the root .env file")

response = requests.post(
    "https://ollama.com/api/chat",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "model": "gemma4:31b",
        "messages": [
            {"role": "user", "content": "Explain what a discord bot is in one sentence."}
        ],
        "stream": False,
    },
    timeout=120,
)

response.raise_for_status()
data = response.json()

print(data["message"]["content"])
