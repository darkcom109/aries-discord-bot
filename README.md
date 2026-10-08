# Aries Discord Bot

Aries is a self-hosted Discord chatbot powered by a local Ollama model. It keeps conversation memory in SQLite and can create polls, reminders, and study notes from PDF or PowerPoint files.

## What you need

- Python 3.12 recommended
- A Discord application and bot token
- [Ollama](https://ollama.com/download/linux) with the `gemma4:e4b` model
- SearXNG on `localhost:8088` for web search (optional)

## Run on Linux

From the repository root, create a Python environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a `.env` file in the repository root and add your Discord bot token:

```env
DISCORD_TOKEN=your_bot_token_here
```

Keep `.env` private; it is ignored by Git. Install Ollama, then download Aries's model:

```bash
ollama pull gemma4:e4b
```

Start Aries from the `discord-bot` directory so its SQLite database stays in the expected location:

```bash
cd discord-bot
python main.py
```

This runs Aries in the foreground for testing. Set up `systemd` auto-start after confirming the bot works on the mini PC.

Invite the bot using the `bot` and `applications.commands` scopes, with permissions to view and send messages, create polls, and attach files.

## Optional web search

Web search requires SearXNG to be running locally on port `8088`. Its configuration file is `searxng-config/settings.yml`; Aries sends searches to `http://localhost:8088/search`.

## Data

Conversation memory and reminders are stored in `discord-bot/aries.db`. Back it up before moving Aries to another machine if you want to keep that data. Scanned PDFs without extractable text are not supported for notes yet.
