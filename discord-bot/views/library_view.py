from io import BytesIO
import logging

import discord

from configurations.helpers.response_helper import shorten_text
from database import delete_user_library_item, get_user_library, get_user_library_item
from modals import SourceQuestionModal

class LibraryView(discord.ui.View):
    def __init__(
        self,
        guild_id: str | None,
        user_id: str,
        items,
        query: str = "",
    ):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.user_id = user_id
        self.items = items
        self.query = query
        self.index = 0
        self.source_link = discord.ui.Button(
            label="Open original message",
            style=discord.ButtonStyle.link,
            url="https://discord.com",
            row=1,
        )
        self.add_item(self.source_link)

    def build_embed(self):
        empty = not self.items
        self.previous.disabled = empty or self.index == 0
        self.next.disabled = empty or self.index >= len(self.items) - 1
        self.ask.disabled = empty
        self.download.disabled = empty
        self.remove.disabled = empty

        if empty:
            self.source_link.disabled = True
            self.source_link.url = "https://discord.com"
            return discord.Embed(
                title="Your library",
                description=(
                    "No saved items match. Use /save or right-click a message "
                    "> Apps > Save to Aries."
                ),
                colour=discord.Colour.blurple(),
            )

        item = self.items[self.index]
        self.source_link.disabled = item.source_url is None
        self.source_link.url = item.source_url or "https://discord.com"
        embed = discord.Embed(
            title=item.title,
            description=shorten_text(item.content, 1600),
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Saved", value=f"<t:{item.created_at}:f>")
        embed.set_footer(text=(
            f"Item {self.index + 1} of {len(self.items)} | "
            f"Saved #{item.id} | Latest 50 matches"
        ))
        return embed

    async def refresh(self):
        self.items = await get_user_library(self.guild_id, self.user_id, self.query)
        self.index = min(self.index, max(0, len(self.items) - 1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "Please open your own library with /library.", ephemeral=True
            )
            return False
        return True

    async def current_item(self):
        if not self.items:
            return None
        return await get_user_library_item(
            self.items[self.index].id, self.guild_id, self.user_id
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.refresh()
        self.index = max(0, self.index - 1)
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.refresh()
        self.index = min(max(0, len(self.items) - 1), self.index + 1)
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Ask Aries", style=discord.ButtonStyle.primary, row=0)
    async def ask(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = await self.current_item()
        if item is None:
            await interaction.response.send_message(
                "That saved item was removed. Reopen /library.", ephemeral=True
            )
            return

        source = f"TITLE: {item.title}\n\n{item.content}"
        await interaction.response.send_modal(SourceQuestionModal(self.user_id, source))

    @discord.ui.button(label="Download", style=discord.ButtonStyle.secondary, row=0)
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        item = await self.current_item()
        if item is None:
            await interaction.edit_original_response(content="That saved item was removed.")
            return

        text = f"# {item.title}\n\n{item.content}"
        if item.source_url:
            text += f"\n\nOriginal message: {item.source_url}"
        await interaction.followup.send(
            file=discord.File(
                BytesIO(text.encode("utf-8")), filename=f"aries_saved_{item.id}.md"
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Remove saved copy", style=discord.ButtonStyle.danger, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.items:
            await delete_user_library_item(
                self.items[self.index].id, self.guild_id, self.user_id
            )
        await self.refresh()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def on_error(self, interaction, error, item):
        logging.getLogger(__name__).error(
            "Library control failed", exc_info=(type(error), error, error.__traceback__)
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                "I couldn't update your library. Please try again.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "I couldn't update your library. Please try again.", ephemeral=True
            )
