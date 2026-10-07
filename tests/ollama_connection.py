import requests

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen3:8b",
        "messages": [
            {"role": "user", "content": "Explain what a discord bot is in one sentence."}
        ],
        "stream": False,
    }
)

response.raise_for_status()
data = response.json()

print(data["message"]["content"])