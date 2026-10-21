import discord
from discord import app_commands

from clients import ollama_client
from configurations.helpers.response_helper import shorten_text
from configurations.helpers.server_helper import redact_logs
from configurations.server_config import get_monitor_owner_id
from database import get_autonomy_actions, get_autonomy_state


async def check_autonomy_owner(interaction):
    owner_id = get_monitor_owner_id()
    if owner_id is not None and str(interaction.user.id) == owner_id:
        return True
    message = (
        "Set ARIES_OWNER_ID to your own Discord user ID in .env and restart Aries first."
        if owner_id is None else "Only the configured Aries owner can control autonomous mode."
    )
    await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    return False


def register_autonomy(bot):
    autonomy = app_commands.Group(name="autonomy", description="Owner only: control Aries' autonomous background mode")

    @autonomy.command(name="start", description="Enable autonomous work toward a goal in one approved text channel")
    @app_commands.describe(
        goal="What Aries should work on and when an update is worthwhile (up to 2000 characters)",
        channel="The ONLY channel Aries may post in; everyone with access can see those posts",
        interval_minutes="Minimum time between cycles; Aries may choose a longer wait (5–1440 minutes)",
        allow_actions="Also permit creating polls and one-time reminders; off by default",
    )
    async def start(
        interaction: discord.Interaction, goal: str, channel: discord.TextChannel,
        interval_minutes: app_commands.Range[int, 5, 1440] = 15, allow_actions: bool = False,
    ):
        if not await check_autonomy_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        if interaction.guild is None or channel.guild.id != interaction.guild.id:
            answer = "Choose a text channel in this server, not a DM or another server."
        elif not goal.strip() or len(goal) > 2000:
            answer = "Provide a goal between 1 and 2000 characters."
        elif not channel.permissions_for(interaction.user).view_channel:
            answer = "You must be able to view the chosen channel."
        elif channel.guild.me is None or not channel.permissions_for(channel.guild.me).view_channel or not channel.permissions_for(channel.guild.me).send_messages:
            answer = "Give Aries View Channel and Send Messages permissions in that channel first."
        else:
            await bot.autonomy.start(str(interaction.user.id), str(channel.guild.id), str(channel.id),
                                     redact_logs(goal.strip()), interval_minutes, allow_actions)
            answer = (
                f"Autonomous mode enabled in {channel.mention}. First check within a minute; "
                f"minimum interval {interval_minutes} minutes.\n"
                "Aries can search, read public pages, check TfL and post useful updates there. "
                + ("Polls and one-time reminders are also permitted.\n" if allow_actions else "Polls and reminders are disabled.\n")
                + "Limits: one outward action per cycle, three per hour, no mass mentions. "
                "Settings survive restarts. Stop with `/autonomy stop`; inspect `/autonomy status` and `/autonomy activity`."
            )
        await interaction.edit_original_response(content=answer, allowed_mentions=discord.AllowedMentions.none())

    @autonomy.command(name="stop", description="Disable autonomous mode and cancel its current cycle")
    async def stop(interaction: discord.Interaction):
        if not await check_autonomy_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        await bot.autonomy.stop()
        await interaction.edit_original_response(
            content="Autonomous mode stopped. Already-sent messages and previously saved reminders are not undone; use /reminders to manage those.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @autonomy.command(name="status", description="View the autonomous goal, progress, next check and model fallback state")
    async def status(interaction: discord.Interaction):
        if not await check_autonomy_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        state = await get_autonomy_state()
        if state is None or state.owner_id != str(interaction.user.id):
            answer = "Autonomous mode is off. Use `/autonomy start` with a goal and a channel to enable it."
        else:
            backend = ollama_client.ollama_backend_status()
            answer = (
                f"**Autonomous mode: {'ON' if state.enabled else 'OFF'}**\n"
                f"Channel: <#{state.channel_id}>\nGoal: {shorten_text(redact_logs(state.goal), 650)}\n"
                f"Minimum interval: {state.interval_minutes} minutes\n"
                f"Polls/reminders: {'allowed' if state.allow_actions else 'disabled'}\n"
                f"Model routing: {backend}; automatic local fallback "
                f"{'enabled' if ollama_client.ollama_fallback_enabled() else 'disabled'}.\n"
                + (f"Next check: <t:{state.next_run_at}:R>\n" if state.enabled else "")
                + "**Saved progress**\n" + (shorten_text(redact_logs(state.memory), 700) or "No progress note yet.")
            )
        await interaction.edit_original_response(content=shorten_text(answer), allowed_mentions=discord.AllowedMentions.none())

    @autonomy.command(name="activity", description="View the last ten autonomous tool attempts and cycle outcomes")
    async def activity(interaction: discord.Interaction):
        if not await check_autonomy_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        entries = await get_autonomy_actions(10, str(interaction.user.id))
        answer = "**Recent autonomous activity**\n" + "\n".join(
            f"<t:{item.created_at}:R> · **{item.name}** [{item.status}]\n"
            + shorten_text(" ".join(redact_logs(item.detail).split()), 130)
            for item in entries
        ) if entries else "No autonomous activity recorded yet."
        await interaction.edit_original_response(content=shorten_text(answer), allowed_mentions=discord.AllowedMentions.none())

    bot.commands.add_command(autonomy)
