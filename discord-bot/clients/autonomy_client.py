import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import logging
import time

import discord

from clients.ollama_client import ollama_request
from clients.page_client import fetch_page_text
from configurations.handlers.tfl_handler import tfl_answer
from configurations.handlers.web_search_handler import web_search
from configurations.helpers.response_helper import shorten_text
from configurations.helpers.reminder_helper import format_reminder_content
from configurations.helpers.server_helper import redact_logs
from configurations.prompts.autonomy_prompt import get_autonomy_prompt
from configurations.server_config import get_monitor_owner_id
from configurations.tools.autonomy_tools import autonomy_tools
from database import (
    autonomy_is_current, claim_autonomy_run, complete_autonomy_action, configure_autonomy,
    disable_autonomy, finish_autonomy_run, get_autonomy_actions, get_autonomy_state,
    reserve_autonomy_action, save_message, save_reminder,
)


class AutonomyStopped(Exception):
    pass


def required_text(arguments: dict, key: str, limit: int) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-16-le")) > limit * 2:
        raise ValueError(f"Provide a non-empty {key} of at most {limit} characters.")
    return value.strip()


class AutonomyClient:
    def __init__(self, bot):
        self.bot = bot
        self.control_lock = asyncio.Lock()
        self.cycle_task: asyncio.Task[None] | None = None

    async def start(self, owner_id, guild_id, channel_id, goal, interval_minutes, allow_actions=False):
        async with self.control_lock:
            await self.cancel_cycle()
            return await configure_autonomy(owner_id, guild_id, channel_id, goal, interval_minutes, allow_actions)

    async def stop(self):
        async with self.control_lock:
            await disable_autonomy()
            await self.cancel_cycle()

    async def cancel_cycle(self):
        if self.cycle_task is not None and not self.cycle_task.done():
            self.cycle_task.cancel()
            await asyncio.gather(self.cycle_task, return_exceptions=True)

    async def tick(self):
        async with self.control_lock:
            if self.cycle_task is not None and not self.cycle_task.done():
                return
            state = await get_autonomy_state()
            if state is None or not state.enabled:
                return
            if state.owner_id != get_monitor_owner_id():
                await disable_autonomy()
                return
            state = await claim_autonomy_run(int(time.time()))
            if state is None:
                return
            self.cycle_task = asyncio.create_task(self.run_cycle(state))
            task = self.cycle_task
        try:
            await task
        except asyncio.CancelledError:
            # /autonomy stop cancels the child, not the Discord background loop.
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise

    async def ensure_current(self, state):
        if state.owner_id != get_monitor_owner_id() or not await autonomy_is_current(state):
            raise AutonomyStopped()

    async def approved_channel(self, state):
        channel = self.bot.get_channel(int(state.channel_id))
        if channel is None:
            channel = await self.bot.fetch_channel(int(state.channel_id))
        if not isinstance(channel, discord.TextChannel) or str(channel.guild.id) != state.guild_id:
            raise ValueError("The approved text channel is unavailable.")
        owner = await channel.guild.fetch_member(int(state.owner_id))
        if not channel.permissions_for(owner).view_channel:
            raise ValueError("The owner can no longer view the approved channel.")
        member = channel.guild.me
        if member is None:
            raise ValueError("Aries' server membership is unavailable.")
        permissions = channel.permissions_for(member)
        if not permissions.view_channel or not permissions.send_messages:
            raise ValueError("Aries cannot view or send messages in the approved channel.")
        return channel

    async def audit(self, state, name, detail, signature=None):
        return await reserve_autonomy_action(name, redact_logs(detail), signature, state.owner_id, state.channel_id)

    async def run_cycle(self, state):
        try:
            async with asyncio.timeout(240):
                channel = await self.approved_channel(state)
                actions = await get_autonomy_actions(6, state.owner_id, state.channel_id)
                context = {
                    "owner_goal": state.goal, "saved_progress_untrusted": state.memory,
                    "polls_and_reminders_allowed": state.allow_actions,
                    "recent_activity_untrusted": [f"{item.name} [{item.status}]: {item.detail}" for item in actions],
                }
                messages = [
                    {"role": "system", "content": get_autonomy_prompt(state.interval_minutes)},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ]
                tools = [deepcopy(item) for item in autonomy_tools if state.allow_actions
                         or item["function"]["name"] not in {"create_poll", "create_reminder"}]
                tools[-1]["function"]["parameters"]["properties"]["wait_minutes"]["minimum"] = state.interval_minutes
                used_calls = 0
                acted = False
                for _ in range(3):
                    await self.ensure_current(state)
                    data = await ollama_request(messages, tools=tools, max_tokens=512)
                    await self.ensure_current(state)
                    message = data["message"]
                    calls = message.get("tool_calls") or []
                    if not calls:
                        # A normal completion is quiet, never automatically broadcast.
                        note = message.get("content") or state.memory
                        await finish_autonomy_run(state, redact_logs(note), state.interval_minutes)
                        await self.record_cycle(state, "idle", "Cycle ended without another tool call.")
                        return
                    if not isinstance(calls, list):
                        raise ValueError("Malformed tool calls.")
                    messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls[:4 - used_calls]})
                    for call in calls[:4 - used_calls]:
                        used_calls += 1
                        function = call.get("function", {}) if isinstance(call, dict) else {}
                        name = function.get("name")
                        arguments = function.get("arguments", {})
                        try:
                            if not isinstance(arguments, dict):
                                raise ValueError("Tool arguments must be an object.")
                            if name == "finish_cycle":
                                memory = required_text(arguments, "memory", 3000)
                                wait = arguments.get("wait_minutes")
                                if type(wait) is not int or not state.interval_minutes <= wait <= 1440:
                                    raise ValueError(f"Wait must be {state.interval_minutes}–1440 minutes.")
                                await finish_autonomy_run(state, redact_logs(memory), wait)
                                await self.record_cycle(state, "sleep", f"Next check in {wait} minutes.")
                                return
                            outward = name in {"send_message", "create_poll", "create_reminder"}
                            if outward and acted:
                                raise ValueError("Only one outward action is allowed per cycle.")
                            result = await self.run_tool(state, channel, name, arguments)
                            acted = acted or outward
                        except ValueError as error:
                            result = "Rejected: " + str(error)
                        messages.append({"role": "tool", "tool_name": name or "unknown", "content": str(result)[:6500]})
                    if used_calls >= 4:
                        break
                await self.record_cycle(state, "budget", "Cycle stopped at its model/tool limit; next check remains scheduled.")
        except AutonomyStopped:
            return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # No raw exception text: HTTP exceptions may contain private URLs/credentials.
            logging.getLogger(__name__).warning("Autonomy cycle failed (%s)", type(error).__name__)
            await self.record_cycle(state, "error", f"Cycle failed: {type(error).__name__}. Check service logs and configuration.")
            # Avoid repeating a broken backend or missing permission every few minutes.
            await finish_autonomy_run(state, state.memory, max(30, state.interval_minutes))

    async def record_cycle(self, state, name, detail):
        action_id = await self.audit(state, name, detail)
        await complete_autonomy_action(action_id, "success" if name != "error" else "error")

    async def run_tool(self, state, channel, name, arguments):
        await self.ensure_current(state)
        allowed = {item["function"]["name"] for item in autonomy_tools}
        if name not in allowed or name == "finish_cycle":
            raise ValueError("That tool is not available in autonomous mode.")
        action_id = None
        try:
            if name in {"web_search", "read_web_page", "get_tfl"}:
                action_id = await self.audit(state, name, json.dumps(arguments, ensure_ascii=False))
                if name == "web_search":
                    query = required_text(arguments, "query", 300)
                    if redact_logs(query) != query:
                        raise ValueError("Search queries must not contain credentials.")
                    result = "UNTRUSTED SEARCH RESULTS:\n" + json.dumps(await web_search(query), ensure_ascii=False)
                elif name == "read_web_page":
                    url = required_text(arguments, "url", 2000)
                    if redact_logs(url) != url:
                        raise ValueError("URLs containing credentials are blocked.")
                    result = "UNTRUSTED PAGE TEXT:\n" + (await asyncio.to_thread(fetch_page_text, url) or "No readable public page text.")
                else:
                    result = await tfl_answer(self.bot.tfl, arguments)
            else:
                if name != "send_message" and not state.allow_actions:
                    raise ValueError("Polls and reminders require the owner's allow_actions opt-in.")
                content = None
                poll = None
                due_at = None
                question = ""
                effective = {}
                if name == "send_message":
                    content = redact_logs(required_text(arguments, "content", 1800))
                    effective = {"content": content}
                elif name == "create_poll":
                    question = redact_logs(required_text(arguments, "question", 300))
                    options = arguments.get("options")
                    if not isinstance(options, list) or not 2 <= len(options) <= 10:
                        raise ValueError("Polls need 2–10 options.")
                    poll = discord.Poll(question=question, duration=timedelta(hours=24))
                    choices = []
                    for option in options:
                        choice = redact_logs(required_text({"option": option}, "option", 55))
                        choices.append(choice)
                        poll.add_answer(text=choice)
                    effective = {"question": question, "options": choices}
                elif name == "create_reminder":
                    content = format_reminder_content(redact_logs(required_text(arguments, "content", 500)))
                    target = datetime.fromisoformat(required_text(arguments, "time", 50))
                    if target.tzinfo is None:
                        raise ValueError("Reminder times must include a UTC offset.")
                    due_at = int(target.timestamp())
                    if not int(time.time()) + 60 <= due_at <= int(time.time()) + 7 * 86400:
                        raise ValueError("Reminders must be 1 minute to 7 days in the future.")
                    effective = {"content": content, "due_at": due_at}
                # Reserve BEFORE sending. A crash/uncertain delivery isn't automatically replayed.
                signature = hashlib.sha256(json.dumps(
                    [state.owner_id, state.channel_id, name, effective], sort_keys=True,
                ).encode()).hexdigest()
                action_id = await self.audit(state, name, json.dumps(effective, ensure_ascii=False), signature)
                if action_id is None:
                    raise ValueError("Hourly action limit reached, or this action was already attempted in the last 24 hours.")
                await self.ensure_current(state)
                if name == "create_reminder":
                    assert content is not None and due_at is not None
                    reminder_id = await save_reminder(state.guild_id, state.channel_id, state.owner_id, content, due_at, "none")
                    result = f"Saved one-time reminder #{reminder_id}."
                else:
                    sent = await channel.send(
                        content=shorten_text(content) if content else "Autonomous poll:", poll=poll,
                        allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True,
                    )
                    result = f"Posted message {sent.id} in the approved channel."
                    await save_message(state.guild_id, state.channel_id, state.owner_id, "assistant",
                                       content or f"Created poll: {question}")
            await complete_autonomy_action(action_id, "success")
            return result
        except BaseException:
            if action_id is not None:
                # Keep reservations after failure/cancellation to avoid duplicate sends.
                await complete_autonomy_action(action_id, "error")
            raise
