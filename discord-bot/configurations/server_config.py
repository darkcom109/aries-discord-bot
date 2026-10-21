import os
from pathlib import Path
import re


PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
LOG_SERVICES = {"aries": "Aries", "searxng": "SearXNG"}
MAX_LOG_LINES = 200
MAX_LOG_BYTES = 64 * 1024
MAX_COMMAND_BYTES = 256 * 1024
COMMAND_TIMEOUT = 8


def get_monitor_owner_id() -> str | None:
    value = os.getenv("ARIES_OWNER_ID", "").strip()
    if not 1 <= len(value) <= 20 or not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2 ** 64:
        return None
    return str(int(value))


def get_aries_unit() -> str:
    unit = os.getenv("ARIES_SYSTEMD_UNIT", "aries.service").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,100}\.service", unit):
        raise ValueError("ARIES_SYSTEMD_UNIT must be a single systemd .service name.")
    return unit
