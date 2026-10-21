import logging

import discord

from clients.tfl_client import TflError
from configurations.helpers.response_helper import shorten_text
from configurations.helpers.tfl_helper import format_tfl_line, tfl_footer, tfl_status_fingerprint
from database import load_tfl_watches, update_tfl_watch_status


async def handle_tfl_watches(bot):
    watches = await load_tfl_watches()
    if not watches:
        return
    try:
        lines, checked_at = await bot.tfl.line_statuses()
    except TflError as error:
        logging.getLogger(__name__).warning("TfL alerts: %s", error)
        return

    by_id = {line["id"]: line for line in lines}
    for watch in watches:
        line = by_id.get(watch.line_id)
        status = tfl_status_fingerprint(line) if line is not None else None
        if status is None or status == watch.last_status:
            continue
        try:
            channel = bot.get_partial_messageable(int(watch.channel_id))
            await channel.send(
                shorten_text("**TfL service update**\n" + format_tfl_line(line) + tfl_footer(checked_at)
                             + f"\nStop alerts with `/tfl unwatch line:{watch.line_id}`."),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logging.getLogger(__name__).warning("Couldn't deliver TfL alert for watch %s; will retry.", watch.id)
            continue
        # Keep the previous snapshot on failure, so an undelivered update can retry.
        await update_tfl_watch_status(watch.id, status)
