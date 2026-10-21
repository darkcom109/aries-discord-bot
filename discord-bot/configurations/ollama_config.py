import os

OLLAMA_API_URL = "https://ollama.com/api/chat"
OLLAMA_MODEL = "gemma4:31b"


def get_ollama_headers() -> dict[str, str]:
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is missing from the environment")

    return {"Authorization": f"Bearer {api_key}"}


def local_ollama_settings():
    return (
        os.getenv("OLLAMA_LOCAL_API_URL", "http://127.0.0.1:11434/api/chat"),
        os.getenv("OLLAMA_LOCAL_MODEL", "qwen3.5:2b"),
    )


def ollama_fallback_enabled() -> bool:
    return os.getenv("OLLAMA_FALLBACK_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
