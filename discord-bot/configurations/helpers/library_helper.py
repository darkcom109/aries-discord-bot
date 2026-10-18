import asyncio

import discord

from configurations.helpers.file_reader import extract_text

SUPPORTED_FILES = (".pdf", ".pptx", ".txt", ".md", ".csv", ".json")

async def read_library_file(file: discord.Attachment) -> str:
    if not file.filename.lower().endswith(SUPPORTED_FILES):
        raise ValueError("Please attach a PDF, PowerPoint, TXT, Markdown, CSV, or JSON file.")

    if file.size > 8 * 1024 * 1024:
        raise ValueError("Please use a file smaller than 8 MB.")

    data = await file.read()

    if file.filename.lower().endswith((".pdf", ".pptx")):
        try:
            text = await asyncio.to_thread(extract_text, file.filename, data)
        except Exception as error:
            raise ValueError("I couldn't read that document. It may be damaged or encrypted.") from error
    else:
        text = data.decode("utf-8-sig", errors="replace")

    if not text.strip():
        raise ValueError("That file has no readable text. Scanned PDFs need OCR first.")

    return text[:100_000]

async def read_library_message(message: discord.Message) -> str:
    sections = [message.content.strip()] if message.content.strip() else []

    for file in message.attachments[:3]:
        if file.filename.lower().endswith(SUPPORTED_FILES):
            text = await read_library_file(file)
            sections.append(f"FILE: {file.filename}\n{text}")

    text = "\n\n".join(sections).strip()

    if not text:
        raise ValueError("I can save text and readable documents. Use Ask Aries for images.")

    return text[:100_000]
