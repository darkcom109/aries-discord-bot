import os

OLLAMA_API_URL = "https://ollama.com/api/chat"
OLLAMA_MODEL = "gemma4:31b"


def get_ollama_headers() -> dict[str, str]:
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is missing from the environment")

    return {"Authorization": f"Bearer {api_key}"}
