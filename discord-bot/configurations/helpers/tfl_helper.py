import hashlib
import html
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import discord


def clean_tfl_text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(value))).split())


def display_tfl_text(value: str, limit: int = 500) -> str:
    text = clean_tfl_text(value)
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return discord.utils.escape_markdown(discord.utils.escape_mentions(text))


def normalise_tfl_line(value: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", value.lower()).split()
    return " ".join(word for word in words if word != "line")


def matching_tfl_lines(query: str, lines: list[dict]) -> list[dict]:
    query = normalise_tfl_line(query)
    exact = [
        line for line in lines
        if query in (normalise_tfl_line(line["id"]), normalise_tfl_line(line["name"]))
    ]
    if exact:
        return exact
    return [line for line in lines if query == normalise_tfl_line(line.get("modeName", ""))]


def tfl_status_items(line: dict) -> list[dict]:
    statuses = line.get("lineStatuses")
    if not isinstance(statuses, list):
        return []
    return [
        status for status in statuses
        if isinstance(status, dict) and isinstance(status.get("statusSeverityDescription"), str)
        and status["statusSeverityDescription"].strip()
    ]


def tfl_status_fingerprint(line: dict) -> str | None:
    statuses = tfl_status_items(line)
    if not statuses:
        return None
    # IDs and validity timestamps can change without the actual service changing.
    snapshot = sorted(
        (
            str(status.get("statusSeverity", "")),
            clean_tfl_text(status["statusSeverityDescription"]),
            clean_tfl_text(status.get("reason") or ""),
        )
        for status in statuses
    )
    return hashlib.sha256(json.dumps(snapshot).encode("utf-8")).hexdigest()


def format_tfl_line(line: dict) -> str:
    statuses = tfl_status_items(line)
    descriptions = list(dict.fromkeys(
        display_tfl_text(status["statusSeverityDescription"], 100) for status in statuses
    ))
    result = f"**{display_tfl_text(line['name'], 100)}**: "
    result += "; ".join(descriptions) if descriptions else "Status unavailable"
    reasons = list(dict.fromkeys(
        clean_tfl_text(status.get("reason") or "") for status in statuses
        if status.get("reason")
    ))
    for reason in reasons[:3]:
        result += "\n" + display_tfl_text(reason)
    return result


def tfl_timestamp(value: str) -> int | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Europe/London"))
        return int(parsed.timestamp())
    except (ValueError, TypeError, AttributeError):
        return None


def tfl_footer(checked_at: int, source: str = "https://tfl.gov.uk/status-updates/") -> str:
    return f"\n\n[TfL]({source}) · fetched <t:{checked_at}:R>. Estimates and service can change."


def format_tfl_stops(matches: list[dict]) -> str:
    lines = []
    for match in matches[:8]:
        modes = ", ".join(match.get("modes", []))
        towards = match.get("towards")
        detail = f" ({display_tfl_text(modes, 100)})" if modes else ""
        if towards:
            detail += f" towards {display_tfl_text(towards, 100)}"
        lines.append(
            f"- **{display_tfl_text(match['name'], 120)}**{detail}\n"
            f"  Stop ID: `{display_tfl_text(match['id'], 80)}`"
        )
    return "\n".join(lines)


def format_tfl_journeys(data: dict, origin: str, destination: str, checked_at: int) -> str:
    # TfL returns HTTP 300, not an error, when a location needs clarification.
    choices = []
    for field, label in (("fromLocationDisambiguation", "Origin"), ("toLocationDisambiguation", "Destination")):
        options = (data.get(field) or {}).get("disambiguationOptions", [])
        if options:
            choices.append(f"**{label}: choose a more specific location**")
            for option in options[:5]:
                place = option.get("place") or {}
                name = place.get("commonName") or "Location"
                value = option.get("parameterValue") or ""
                choices.append(f"- {display_tfl_text(name, 120)}: `{display_tfl_text(value, 80)}`")
    if choices:
        return "\n".join(choices) + "\nRun `/tfl journey` again using the chosen ID or coordinates."

    journeys = data.get("journeys") or []
    if not journeys:
        return "TfL returned no journey options. Try more specific stations or postcodes."

    lines = [f"**{display_tfl_text(origin, 120)} → {display_tfl_text(destination, 120)}**"]
    for number, journey in enumerate(journeys[:3], start=1):
        start = tfl_timestamp(journey.get("startDateTime"))
        end = tfl_timestamp(journey.get("arrivalDateTime"))
        timing = f"<t:{start}:t> → <t:{end}:t>" if start is not None and end is not None else "Time unavailable"
        duration = journey.get("duration")
        label = f" · {duration} min" if isinstance(duration, int) else ""
        lines.append(f"\n**Option {number}** · {timing}{label}")
        for leg in journey.get("legs", [])[:12]:
            instruction = (leg.get("instruction") or {}).get("summary")
            if not instruction:
                departure = (leg.get("departurePoint") or {}).get("commonName", "Origin")
                arrival = (leg.get("arrivalPoint") or {}).get("commonName", "Destination")
                instruction = f"{departure} → {arrival}"
            lines.append("- " + display_tfl_text(instruction, 250))
            if leg.get("isDisrupted") or leg.get("disruptions") or leg.get("plannedWorks"):
                lines.append("  Disruption/planned work reported; check TfL before travelling.")
    return "\n".join(lines) + tfl_footer(checked_at, "https://tfl.gov.uk/plan-a-journey/")
