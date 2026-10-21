import asyncio
from collections import deque
import os
import re
import time
from urllib.parse import quote

import requests

from configurations.helpers.tfl_helper import (
    display_tfl_text,
    format_tfl_journeys,
    format_tfl_line,
    format_tfl_stops,
    matching_tfl_lines,
    normalise_tfl_line,
    tfl_footer,
    tfl_timestamp,
)


class TflError(Exception):
    pass


class TflClient:
    def __init__(self):
        self.cache = {}
        self.request_times = deque()
        self.retry_at = 0.0
        self.lock = asyncio.Lock()

    async def request(self, path: str, params: dict | None = None, ttl: int = 20):
        params = dict(params or {})
        cache_key = (path, tuple(sorted(params.items())))

        # Share in-flight/cache checks between commands and the background watcher.
        async with self.lock:
            now = time.monotonic()
            cached = self.cache.get(cache_key)
            if cached is not None and cached[0] > now:
                return cached[1], cached[2]

            while self.request_times and self.request_times[0] <= now - 60:
                self.request_times.popleft()
            if now < self.retry_at or len(self.request_times) >= 40:
                raise TflError("TfL requests are temporarily rate-limited. Please try again in a minute.")
            self.request_times.append(now)

            api_key = os.getenv("TFL_APP_KEY", "").strip()
            if api_key:
                params["app_key"] = api_key
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    "https://api.tfl.gov.uk" + path,
                    params=params,
                    headers={"Accept": "application/json", "User-Agent": "AriesDiscordBot/1.0"},
                    timeout=10,
                    allow_redirects=False,
                )
            except requests.RequestException:
                # Requests exceptions contain the URL, which may contain the key.
                raise TflError("I couldn't reach TfL. Please try again shortly.") from None

            if response.status_code == 429:
                try:
                    delay = int(response.headers.get("Retry-After", "60"))
                except ValueError:
                    delay = 60
                self.retry_at = time.monotonic() + max(60, min(delay, 3600))
                raise TflError("TfL is rate-limiting requests. Please try again later.")
            if response.status_code in (401, 403):
                raise TflError("TfL refused access. Check TFL_APP_KEY if configured, or try again later.")
            if response.status_code == 404:
                raise TflError("TfL couldn't find that stop or journey. Try `/tfl stops` to find a stop ID.")
            if response.status_code not in (200, 300):
                raise TflError("TfL couldn't complete that request. Try different locations or try again later.")
            try:
                data = response.json()
            except ValueError:
                raise TflError("TfL returned an unreadable response. Please try again later.") from None
            if not isinstance(data, (dict, list)):
                raise TflError("TfL returned an unexpected response. Please try again later.")

            checked_at = int(time.time())
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[cache_key] = (time.monotonic() + ttl, data, checked_at)
            return data, checked_at

    async def line_statuses(self):
        data, checked_at = await self.request(
            "/Line/Mode/tube,dlr,elizabeth-line,overground,tram/Status",
            {"detail": "false"},
        )
        if not isinstance(data, list):
            raise TflError("TfL line status is unavailable right now.")
        lines = [line for line in data if isinstance(line, dict) and line.get("id") and line.get("name")]
        if not lines:
            raise TflError("TfL returned no line status data. Please try again later.")
        return lines, checked_at

    async def status(self, line: str | None = None) -> str:
        lines, checked_at = await self.line_statuses()
        if line is not None:
            lines = matching_tfl_lines(required_tfl_text(line, "line"), lines)
            if not lines:
                raise TflError("I couldn't find that rail line. Use `/tfl status` to see the supported TfL lines.")
        return "**TfL service status**\n\n" + "\n\n".join(format_tfl_line(item) for item in lines) + tfl_footer(checked_at)

    async def search_stops(self, query: str):
        query = required_tfl_text(query, "stop name")
        data, checked_at = await self.request(
            "/StopPoint/Search", {"query": query, "maxResults": 8, "includeHubs": "false"}, ttl=300
        )
        if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
            raise TflError("TfL stop search is unavailable right now.")
        matches = [match for match in data["matches"] if isinstance(match, dict) and match.get("id") and match.get("name")]
        return matches, checked_at

    async def stops(self, query: str) -> str:
        matches, checked_at = await self.search_stops(query)
        if not matches:
            return "I couldn't find any matching TfL stops. Try a more specific station or street name."
        return "**Matching TfL stops**\n" + format_tfl_stops(matches) + "\n\nUse a stop ID with `/tfl arrivals`." + tfl_footer(checked_at)

    async def arrivals(self, stop: str, line: str | None = None) -> str:
        stop = required_tfl_text(stop, "stop name or ID")
        if line is not None:
            line = required_tfl_text(line, "line")
        name = stop
        if not re.fullmatch(r"(?:\d{3,}[A-Za-z][A-Za-z0-9]*|HUB[A-Za-z0-9]+)", stop):
            matches, _ = await self.search_stops(stop)
            if not matches:
                return "I couldn't find that stop. Try `/tfl stops` with a station or street name."
            exact = [match for match in matches if match["name"].casefold() == stop.casefold()]
            if len(exact) == 1:
                matches = exact
            if len(matches) != 1:
                return "That name matches several stops. Choose a stop ID:\n" + format_tfl_stops(matches)
            stop, name = matches[0]["id"], matches[0]["name"]

        data, checked_at = await self.request(f"/StopPoint/{quote(stop, safe='')}/Arrivals", ttl=15)
        if not isinstance(data, list):
            raise TflError("TfL arrival predictions are unavailable right now.")
        predictions = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if line and normalise_tfl_line(line) not in (
                normalise_tfl_line(item.get("lineId") or ""),
                normalise_tfl_line(item.get("lineName") or ""),
            ):
                continue
            arrival = tfl_timestamp(item.get("expectedArrival"))
            seconds = item.get("timeToStation")
            if arrival is None and isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
                arrival = checked_at + int(seconds)
            if arrival is not None and arrival >= checked_at - 15:
                predictions.append((arrival, item))
        if not predictions:
            return "TfL returned no live arrivals for that stop/filter. This does not necessarily mean the service is cancelled." + tfl_footer(checked_at)

        predictions.sort(key=lambda item: item[0])
        name = predictions[0][1].get("stationName") or name
        lines = [f"**Next arrivals: {display_tfl_text(name, 150)}**"]
        for arrival, item in predictions[:8]:
            route = item.get("lineName") or item.get("lineId") or "Service"
            destination = item.get("destinationName") or item.get("towards") or "Destination unavailable"
            platform = item.get("platformName") or ""
            lines.append(f"- **{display_tfl_text(route, 80)}** → {display_tfl_text(destination, 120)} · <t:{arrival}:R>")
            if platform:
                lines.append("  " + display_tfl_text(platform, 120))
        return "\n".join(lines) + tfl_footer(checked_at, "https://tfl.gov.uk/travel-information/stations-stops-and-piers/")

    async def journey(self, origin: str, destination: str) -> str:
        origin = required_tfl_text(origin, "origin")
        destination = required_tfl_text(destination, "destination")
        data, checked_at = await self.request(
            f"/Journey/JourneyResults/{quote(origin, safe='')}/to/{quote(destination, safe='')}",
            {"timeIs": "Departing", "useRealTimeLiveArrivals": "true", "applyHtmlMarkup": "false"},
        )
        if not isinstance(data, dict):
            raise TflError("TfL journey planning is unavailable right now.")
        return format_tfl_journeys(data, origin, destination, checked_at)


def required_tfl_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise TflError(f"Please provide a {label} between 1 and 120 characters.")
    return value.strip()
