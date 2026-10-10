# Aries Discord Bot

Aries is a self-hosted Discord chatbot powered by Ollama's Gemma 4 31B cloud model through Ollama's API. It keeps conversation memory in SQLite and can create polls, reminders, search the web, analyse images, and generate study notes from PDF or PowerPoint files.

## What you need

- Python 3.12 recommended
- A Discord application and bot token
- An [Ollama API key](https://ollama.com/settings/keys) with access to cloud models
- SearXNG on `localhost:8088` for web search (optional)

## Run on Linux

From the repository root, create a Python environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` in the repository root, then fill in your Discord token, Ollama API key, and SearXNG secret:

```env
DISCORD_TOKEN=your_discord_bot_token
OLLAMA_API_KEY=your_ollama_api_key
SEARXNG_SECRET=replace_with_a_random_secret
```

Keep `.env` private; it is ignored by Git. Aries calls `https://ollama.com/api/chat` directly using the `gemma4:31b` cloud model, so Ollama does not need to be installed or running on the bot host. Cloud usage is subject to your Ollama account's credits and limits.

You can keep `DISCORD_TOKEN` and `OLLAMA_API_KEY` in `discord-bot/.env` instead. The root `.env` must still contain `SEARXNG_SECRET` for Docker Compose.

Start Aries from the `discord-bot` directory so its SQLite database stays in the expected location:

```bash
cd discord-bot
python main.py
```

This runs Aries in the foreground for testing. Conversation context and attached images are sent to Ollama's cloud API for inference. Set up `systemd` auto-start after confirming the bot works on the mini PC.

Invite the bot using the `bot` and `applications.commands` scopes, with permissions to view and send messages, create polls, and attach files.

## Optional web search

Web search requires SearXNG to be running locally on port `8088`. Its configuration file is `searxng-config/settings.yml`; Aries sends searches to `http://localhost:8088/search`.

## Data

Conversation memory and reminders are stored in `discord-bot/aries.db`. Back it up before moving Aries to another machine if you want to keep that data. Scanned PDFs without extractable text are not supported for notes yet.
