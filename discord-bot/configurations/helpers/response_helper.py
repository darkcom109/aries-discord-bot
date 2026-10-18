from io import BytesIO

import discord

def shorten_text(text: str, limit: int = 2000) -> str:
    encoded = text.encode("utf-16-le")

    if len(encoded) <= limit * 2:
        return text

    return encoded[:(limit - 3) * 2].decode("utf-16-le", errors="ignore") + "..."

def answer_parts(answer: str, filename: str = "aries_answer.md"):
    answer = answer.strip() or "I couldn't generate a reply. Please try again."
    preview = shorten_text(answer)
    files = []

    if preview != answer:
        preview = shorten_text(answer, 1900) + "\n\nThe full answer is attached."
        files.append(discord.File(BytesIO(answer.encode("utf-8")), filename=filename))

    return preview, files

async def send_answer(interaction: discord.Interaction, answer: str):
    preview, files = answer_parts(answer)
    await interaction.edit_original_response(
        content=preview,
        attachments=files,
        allowed_mentions=discord.AllowedMentions.none(),
    )
