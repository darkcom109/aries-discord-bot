# Aries Discord Bot

Aries is a self-hosted Discord chatbot powered by Ollama's Gemma 4 31B cloud model through Ollama's API. It keeps conversation memory in SQLite and can create polls, reminders, search the web, analyse images, generate study notes, and keep a private searchable library.

## Interactive features

- **Save and find things:** use `/save` with text or a PDF, PPTX, TXT, Markdown, CSV, or JSON attachment (up to 8 MB). `/library query:docker` searches your saved titles and content. The browser lets you ask questions, download the saved text, open its original message, or remove the saved copy.
- **Right-click messages:** under **Apps**, choose **Save to Aries** or **Ask Aries about this**. Questions can use the message's text, readable attachments, and first image; answers are visible only to you.
- **Snooze reminders:** delivered reminders offer preset snooze times, a custom form (1 minute to 7 days), and Dismiss. New reminder controls survive bot restarts. Snoozing adds a one-time reminder and leaves daily/weekly schedules intact.
- **Keep full answers:** long replies include a Markdown attachment instead of silently losing the rest of the answer.

Libraries are private to each user within a server; DMs have a separate library. Search uses keywords and shows up to 50 matches. Saved documents keep up to 100,000 characters of extracted text. Questions about long sources use selected excerpts, so they do not guarantee coverage of the entire document. Browsing and saving need no AI request; asking about a source sends excerpts and any selected image to Ollama's cloud API. `/forget` clears conversation history, not your saved library.

Restart Aries after updating so it creates the additional SQLite tables and syncs the commands. Existing reminder notifications from before this update do not gain persistent controls. Library browser controls last 10 minutes; reopen `/library` when needed.

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

Invite the bot using the `bot` and `applications.commands` scopes, with permissions to view and send messages, embed links, create polls, and attach files.

## Optional web search

Web search requires SearXNG to be running locally on port `8088`. Its configuration file is `searxng-config/settings.yml`; Aries sends searches to `http://localhost:8088/search`.

## Data

Conversation memory, reminders, and saved library entries are stored in `discord-bot/aries.db`. Back it up before moving Aries to another machine if you want to keep that data. Scanned PDFs without extractable text are not supported for notes or saved document text yet.

The database is currently tracked by Git. Before saving private content, use `git rm --cached discord-bot/aries.db` to stop tracking it while keeping your local data. The ignore rules then keep it out of future commits; they do not remove older committed copies.

## Project layout

`discord-bot/main.py` starts Aries. Related code is grouped into packages, with imports exposed through each package's `__init__.py`:

- `commands/`: slash commands, message actions, and command/event registration.
- `clients/`: requests to Ollama and other services.
- `configurations/`: settings, prompts, tool definitions, handlers, and helpers.
- `database/`: models, connection setup, and queries for messages, reminders, and saved items.
- `views/`: message buttons and dropdown menus.
- `modals/`: popup forms for questions and custom snooze times.

Run the offline checks from the repository root with `python -m unittest discover -s tests -p 'test_*.py'`. They use isolated temporary databases and mocked AI requests.
