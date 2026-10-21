# Aries Discord Bot

Aries is a self-hosted Discord chatbot powered by Ollama's Gemma 4 31B cloud model through Ollama's API. It keeps conversation memory in SQLite and can create polls, reminders, search the web, analyse images, generate study notes, and keep a private searchable library.

## Interactive features

- **Save and find things:** use `/save` with text or a PDF, PPTX, TXT, Markdown, CSV, or JSON attachment (up to 8 MB). `/library query:docker` searches your saved titles and content. The browser lets you ask questions, download the saved text, open its original message, or remove the saved copy.
- **Right-click messages:** under **Apps**, choose **Save to Aries** or **Ask Aries about this**. Questions can use the message's text, readable attachments, and first image; answers are visible only to you.
- **Snooze reminders:** delivered reminders offer preset snooze times, a custom form (1 minute to 7 days), and Dismiss. New reminder controls survive bot restarts. Snoozing adds a one-time reminder and leaves daily/weekly schedules intact.
- **Keep full answers:** long replies include a Markdown attachment instead of silently losing the rest of the answer.
- **London transport:** check TfL service status, find stop IDs, look up live arrivals, plan a journey, and opt into private line-change alerts.
- **Owner-only monitoring:** `/server` shows the host's metrics and service status; `/logs` previews or downloads a redacted log sample from Aries or SearXNG. Replies are private.

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

Keep `.env` private; it is ignored by Git. Aries normally calls `https://ollama.com/api/chat` directly using the `gemma4:31b` cloud model. Cloud usage is subject to your Ollama account's credits and limits. Local Ollama is optional for cloud-only use, but required for the automatic backup below.

You can keep `DISCORD_TOKEN` and `OLLAMA_API_KEY` in `discord-bot/.env` instead. The root `.env` must still contain `SEARXNG_SECRET` for Docker Compose.

Start Aries from the `discord-bot` directory so its SQLite database stays in the expected location:

```bash
cd discord-bot
python main.py
```

This runs Aries in the foreground for testing. Conversation context and attached images are sent to Ollama's cloud API for inference. Set up `systemd` auto-start after confirming the bot works on the mini PC.

Invite the bot using the `bot` and `applications.commands` scopes, with permissions to view and send messages, embed links, create polls, and attach files.

## Local model backup

On the **machine running Aries**, install/start Ollama and download the backup once:

```bash
ollama pull qwen3.5:2b
```

The default settings (also in `.env.example`) are:

```env
OLLAMA_FALLBACK_ENABLED=true
OLLAMA_LOCAL_API_URL=http://127.0.0.1:11434/api/chat
OLLAMA_LOCAL_MODEL=qwen3.5:2b
```

All AI features share this route: chat, images, web answers, summaries, notes, saved-source questions and autonomous work. Cloud quota/rate-limit responses, temporary server failures and network outages select local inference; the cloud API key is **never** forwarded to the backup. Tools, messages, images, output caps and `think: false` are preserved. The smaller backup may be less capable and slower than cloud.

Aries waits before retrying cloud (normally 15 minutes for HTTP errors, respecting a numeric `Retry-After` of 1 minute–24 hours; 1 minute after a connection/timeout failure). Missing/invalid API keys, missing cloud models and malformed requests are not silently hidden by fallback. If the backup is unavailable too, the request fails instead of inventing an answer. Set `OLLAMA_FALLBACK_ENABLED=false` for cloud-only operation. This does not install models or start the local Ollama service automatically; on Linux, ensure your existing `ollama` service starts at boot. Logs include `[cloud]` or `[local]` for each successful AI response.

## Autonomous mode

This is an opt-in background agent, **not consciousness**. Set `ARIES_OWNER_ID` to your own Discord user ID, restart Aries to create its new tables/sync commands, and use a dedicated channel:

```text
/autonomy start goal:Research useful self-hosted tools. Post only genuinely new, worthwhile discoveries with sources. channel:#aries-lab interval_minutes:15
/autonomy status
/autonomy activity
/autonomy stop
```

Only the configured owner can control it. Starting enables public-page reading, SearXNG searches, TfL lookups and autonomous posts **in that one channel**. Use a private channel if the goal/results are personal. Add `allow_actions:true` when starting to also authorize 24-hour polls and one-time reminders for you in that channel; recurring reminders are not available to the agent. The model cannot choose other recipients, enable watches, access your private library/server logs, run shell commands, access accounts or make arbitrary HTTP writes.

- First check is within a minute. Each cycle has at most 3 model requests, 4 tool calls and a 4-minute deadline. Default minimum interval is 15 minutes (configurable 5–1440); Aries can choose to wait longer, up to a day. It is a periodic worker, not a continuously thinking model, and plain model replies are quiet unless it explicitly calls `send_message`.
- At most one post/poll/reminder creation per cycle and three total per rolling hour. Identical actions are suppressed for 24 hours; failed/uncertain attempts still consume the budget to avoid automatic duplicate sends. Posts cannot ping users/roles/everyone. Saved reminders use normal reminder delivery and will mention you when due.
- Goals, short progress notes, due times and activity persist in SQLite across restarts. Activity is retained for 30 days and shown privately via `/autonomy activity`. Search/page evidence is treated as untrusted; public-page requests block private/reserved IPs, recheck redirects, verify TLS, and cap downloads. These safeguards reduce risk but do not eliminate prompt injection: start with a narrow goal and review activity.
- `/autonomy stop` disables future cycles and cancels the current one. It cannot undo messages already accepted by Discord or delete previously created reminders; manage those with `/reminders` and `/cancel_reminder`. An in-flight local inference thread may finish after stopping, but its result is not used to resume the cancelled cycle. Normal chat/reminders remain available.

Mode stays off until explicitly started, and is automatically disabled if the configured owner changes/disappears. It runs only while the bot/service is online, uses cloud allowance while enabled, and does not replay missed cycles after downtime. No live autonomous actions are performed by the test suite.

## Optional web search

Web search requires SearXNG to be running locally on port `8088`. Its configuration file is `searxng-config/settings.yml`; Aries sends searches to `http://localhost:8088/search`.

## TfL transport

Restart Aries to create the watch table and sync the new `/tfl` commands:

- `/tfl status line:Victoria` checks one rail line; omit `line` for all supported lines. Tube, DLR, Elizabeth line, Overground and tram are included.
- `/tfl stops query:Oxford Circus` finds stop IDs, modes and available directions. Copy an ID to avoid mixing up nearby stops.
- `/tfl arrivals stop:940GZZLUOXC line:Victoria` shows up to eight predictions; the line/bus route filter is optional.
- `/tfl journey origin:940GZZLUWLO destination:940GZZLUBNK` plans a journey departing now. Names, postcodes and coordinates also work; ambiguous locations produce choices rather than a guessed route.
- `/tfl watch line:Victoria` enables DMs when that line's status changes. `/tfl watches` lists your alerts; `/tfl unwatch line:Victoria` removes one, even while TfL is unavailable.

These slash-command replies are private and make no AI requests. You can also ask `/ask` or mention Aries with a transport question; the model can call the same TfL lookups. Those replies follow the normal chat visibility/history rules. Enabling alerts requires the explicit `/tfl watch` command, not an AI tool call.

No TfL account is needed for anonymous access. Optionally add `TFL_APP_KEY=` to either `.env` file if you have a [TfL subscription key](https://api-portal.tfl.gov.uk/products). Aries shares a short-lived cache and caps outgoing requests at 40/minute per bot process, including with a key; 429 responses trigger a cooldown. There are no new Python dependencies. TfL requests go to `https://api.tfl.gov.uk` and include only your requested locations/filters and optional key, not Discord IDs or chat history.

Line watches are saved in SQLite and checked every minute while Aries is running. They monitor the whole line, all day, including recovery and service closures; they aren't timetable-linked or route-specific. Up to eight lines can be watched per user. DMs must be enabled. Missed intermediate changes during downtime aren't replayed, and failed deliveries retry on a later check. Arrival times are predictions, not guarantees: rerun the command for a new snapshot and check [TfL](https://tfl.gov.uk/status-updates/) before travelling.

## Host monitoring

Update the existing environment from the repository root with `.venv/bin/python -m pip install -r requirements.txt` (Windows: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`). This adds `psutil`; `requirements.txt` is now UTF-8 instead of UTF-16.

Set these in either bot `.env`, then restart Aries to load the settings and sync commands:

```env
ARIES_OWNER_ID=your_discord_user_id
ARIES_SYSTEMD_UNIT=aries.service
```

Use **Copy User ID** in Discord's Developer Mode for the owner ID. Missing/invalid IDs disable monitoring; server administrators do not automatically get access. Change the unit only if your systemd service has another name. On the mini PC, restart your existing service with `sudo systemctl restart aries` after updating.

- `/server`: CPU, RAM, free space on Aries' filesystem, host/process uptime, process RAM, available temperatures, and Aries/systemd + SearXNG/Compose status. **Refresh** uses a shared five-second cache. Docker's running state is not an application health guarantee.
- `/logs service:aries minutes:30 errors_only:true`: journal entries from the configured systemd unit. `/logs service:searxng` reads only this repo's Compose service. Optional `lines` is 1–200 (default 100); `minutes` is 1–1440 (default 30).
- Log controls provide **Refresh**, **Errors only/Show all**, and a private **Download logs** `.txt` attachment. Filtering/download use the captured sample, not the entire journal; Python traceback context is retained where possible. Keyword filtering is approximate, not proof that no errors occurred.

Metrics describe the machine/environment running Aries, not a remote machine. Aries service logs require Linux/systemd; SearXNG status/logs require the Docker CLI, Compose plugin and existing daemon permissions. Missing tools/access produce an explanation. No `sudo`, shell commands, restarts or permission changes are executed by these controls. If journal reading is denied, review the service account's permissions; the [systemd-journal group grants broad journal-reading access](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html), so it is not granted automatically. Keep Aries unprivileged.

Commands and every button are owner-checked; responses/downloads are ephemeral, controls expire after five minutes, and these reads make no AI requests or conversation/database writes. Log reads have an eight-second timeout, bounded subprocess capture, a 64 KiB message budget, and a two-second refresh cooldown. Loaded environment credentials and common token/password patterns are redacted before preview/download; redaction is best-effort, so review logs before sharing them. Private results are still delivered through Discord. No background health alerts or external offline monitoring are enabled by this feature.

## Data

Conversation memory, reminders, saved library entries, TfL watches, autonomous settings/progress and recent activity are stored in `discord-bot/aries.db`. Back it up before moving Aries to another machine if you want to keep that data. Scanned PDFs without extractable text are not supported for notes or saved document text yet.

Runtime databases are ignored by Git; keep database backups private too. Ignore rules do not remove older committed copies from repository history.

## Project layout

`discord-bot/main.py` starts Aries. Related code is grouped into packages, with imports exposed through each package's `__init__.py`:

- `commands/`: slash commands, message actions, and command/event registration.
- `clients/`: requests to Ollama and other services.
- `configurations/`: settings, prompts, tool definitions, handlers, and helpers.
- `database/`: models, connection setup, and queries for messages, reminders, and saved items.
- `views/`: message buttons and dropdown menus.
- `modals/`: popup forms for questions and custom snooze times.

Run the offline checks from the repository root with `python -m unittest discover -s tests -p 'test_*.py'`. They use isolated temporary databases and mocked AI requests.
