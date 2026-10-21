import discord
from discord import app_commands

from clients.tfl_client import TflError, required_tfl_text
from configurations.handlers.tfl_handler import tfl_answer
from configurations.helpers.response_helper import send_answer, shorten_text
from configurations.helpers.tfl_helper import (
    display_tfl_text,
    format_tfl_line,
    matching_tfl_lines,
    tfl_footer,
    tfl_status_fingerprint,
)
from database import delete_user_tfl_watch, get_user_tfl_watches, save_tfl_watch


def register_tfl(bot):
    tfl = app_commands.Group(name="tfl", description="London transport status, arrivals, journeys and private alerts")

    async def show_tfl(interaction, action, **arguments):
        await interaction.response.defer(thinking=True, ephemeral=True)
        answer = await tfl_answer(bot.tfl, {"action": action, **arguments})
        await send_answer(interaction, answer)

    @tfl.command(name="status", description="Check Tube, DLR, Elizabeth line, Overground and tram status")
    @app_commands.describe(line="Optional line or group, e.g. Victoria, Elizabeth line, or Overground")
    async def status(interaction: discord.Interaction, line: str | None = None):
        await show_tfl(interaction, "status", line=line)

    @tfl.command(name="stops", description="Find station or bus stop IDs, including direction")
    async def stops(interaction: discord.Interaction, query: str):
        await show_tfl(interaction, "stops", stop=query)

    @tfl.command(name="arrivals", description="Get the next live arrivals at a station or bus stop")
    @app_commands.describe(stop="A specific stop name or ID from /tfl stops", line="Optional line or bus route filter")
    async def arrivals(interaction: discord.Interaction, stop: str, line: str | None = None):
        await show_tfl(interaction, "arrivals", stop=stop, line=line)

    @tfl.command(name="journey", description="Plan a London journey departing now")
    @app_commands.describe(origin="Station, postcode, stop ID or coordinates", destination="Station, postcode, stop ID or coordinates")
    async def journey(interaction: discord.Interaction, origin: str, destination: str):
        await show_tfl(interaction, "journey", origin=origin, destination=destination)

    @tfl.command(name="watch", description="Opt in to private DMs when one rail line's service status changes")
    async def watch(interaction: discord.Interaction, line: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            line = required_tfl_text(line, "line")
            lines, checked_at = await bot.tfl.line_statuses()
            matches = matching_tfl_lines(line, lines)
            if len(matches) != 1:
                choices = ", ".join(item["name"] for item in matches) if matches else "use /tfl status to see available lines"
                raise TflError(f"Choose one specific rail line: {choices}.")
            selected = matches[0]
            fingerprint = tfl_status_fingerprint(selected)
            if fingerprint is None:
                raise TflError("TfL has no status for that line right now. Please try again later.")
            user_id = str(interaction.user.id)
            watches = await get_user_tfl_watches(user_id)
            if any(item.line_id == selected["id"] for item in watches):
                raise TflError("You're already watching that line. Use `/tfl watches` to see your alerts.")
            if len(watches) >= 8:
                raise TflError("You can watch up to 8 lines. Remove one with `/tfl unwatch` first.")
            channel = await interaction.user.create_dm()
            watch_id = await save_tfl_watch(user_id, str(channel.id), selected["id"], selected["name"], fingerprint)
            if watch_id is None:
                raise TflError("You're already watching that line.")
            try:
                await channel.send(
                    shorten_text("**TfL alerts enabled**\n" + format_tfl_line(selected) + tfl_footer(checked_at)
                                 + f"\nI'll check every minute and DM service changes, including recovery and closures."
                                 + f"\nStop with `/tfl unwatch line:{selected['id']}`."),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                await delete_user_tfl_watch(user_id, selected["id"])
                raise TflError("I couldn't DM you. Enable DMs from this server, then try `/tfl watch` again.") from None
            answer = f"Watching **{display_tfl_text(selected['name'])}**. I've sent you a DM. Alerts survive restarts; stop them with `/tfl unwatch`."
        except (TflError, discord.Forbidden) as error:
            answer = str(error) if isinstance(error, TflError) else "I couldn't open a DM. Enable DMs from this server and try again."
        await send_answer(interaction, answer)

    @tfl.command(name="watches", description="List your private TfL line alerts")
    async def watches(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        saved = await get_user_tfl_watches(str(interaction.user.id))
        answer = "You aren't watching any lines. Use `/tfl watch line:Victoria` to start."
        if saved:
            answer = "**Your TfL alerts**\n" + "\n".join(
                f"- {display_tfl_text(item.line_name)} · `/tfl unwatch line:{item.line_id}`" for item in saved
            )
        await send_answer(interaction, answer)

    @tfl.command(name="unwatch", description="Stop your private alerts for one line; no TfL connection needed")
    async def unwatch(interaction: discord.Interaction, line: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        saved = await get_user_tfl_watches(str(interaction.user.id))
        matches = matching_tfl_lines(line, [{"id": item.line_id, "name": item.line_name} for item in saved])
        if len(matches) != 1:
            answer = "You're not watching that line. Use `/tfl watches` to see your saved alerts."
        else:
            await delete_user_tfl_watch(str(interaction.user.id), matches[0]["id"])
            answer = f"Stopped your **{display_tfl_text(matches[0]['name'])}** alerts."
        await send_answer(interaction, answer)

    bot.commands.add_command(tfl)
