import time
from datetime import datetime, timedelta

def format_reminder_content(content: str) -> str:
    content = " ".join(content.split())
    return content[:1].upper() + content[1:]

def next_reminder_due_at(due_at: int, repeat: str, now: int | None = None):
    if repeat == "none":
        return None

    if repeat not in ("daily", "weekly"):
        raise ValueError("Unknown reminder repeat interval.")

    now = int(time.time()) if now is None else now
    interval = timedelta(days=1 if repeat == "daily" else 7)
    next_time = datetime.fromtimestamp(due_at) + interval

    # Send one notification after downtime, then resume at the next future occurrence.
    while next_time.timestamp() <= now:
        next_time += interval

    return int(next_time.timestamp())
