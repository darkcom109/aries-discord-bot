import discord

from file_reader import extract_text
from io import BytesIO
from generate_notes_client import generate_notes

def register_notes(bot):
    @bot.commands.command(
        name="notes",
        description="Read a PDF or Powerpoint file"
    )
    async def notes(interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not file.filename.lower().endswith((".pdf", ".pptx")):
            await interaction.followup.send("Please attach a PDF or Powerpoint (.pptx)")
            return

        file_bytes = await file.read()
        text = extract_text(file.filename, file_bytes)

        if not text.strip():
            await interaction.followup.send(
                "I couldn't find readable text in that file. It may be a scanned PDF."
            )
            return

        notes = await generate_notes(text, file.filename)

        if not notes:
            await interaction.followup.send("I couldn't generate notes from that file.")
            return

        notes_files = discord.File(
            fp=BytesIO(notes.encode("utf-8")),
            filename=f"{file.filename.rsplit('.', 1)[0]}_notes.md"
        )

        await interaction.followup.send(
            content=f"Here are the notes for **{file.filename}**:",
            file=notes_files
        )