"""Minimal Discord bot (V1).

Thin layer over the V0 extraction interface:

    Discord !notes <text> -> extract_notes(text) -> Title/Summary/Map type reply.

No Gemini internals, retry logic, JSON parsing, or schema validation here.
"""

import os
from collections.abc import Callable

import discord
from discord.ext import commands

from notes12 import GeminiExtractionError, Notes12Document, extract_notes

USAGE_MESSAGE = "Please provide some text after the command. Usage: !notes <text>"
FAILURE_MESSAGE = "Sorry, I couldn't extract notes from that text. Please try again later."

ExtractFn = Callable[[str], Notes12Document]


def format_notes_reply(document: Notes12Document) -> str:
    """Format a validated document as a compact Discord reply."""
    return f"Title: {document.title}\nSummary: {document.summary}\nMap type: {document.map_type}"


def handle_notes_text(text: object, *, extract_fn: ExtractFn = extract_notes) -> str:
    """Offline-testable !notes handler: validate input, extract, format.

    Returns a user-facing reply string. Never raises GeminiExtractionError.
    """
    if not isinstance(text, str) or not text.strip():
        return USAGE_MESSAGE
    try:
        document = extract_fn(text)
    except GeminiExtractionError:
        return FAILURE_MESSAGE
    return format_notes_reply(document)


def resolve_discord_token(explicit: str | None = None) -> str:
    """Resolve DISCORD_BOT_TOKEN without ever logging the value."""
    token = (explicit if explicit is not None else os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set. Export it or pass a token explicitly.")
    return token


def create_bot(*, extract_fn: ExtractFn = extract_notes) -> commands.Bot:
    """Create the minimal !notes bot. No network I/O until the caller runs it."""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.command(name="notes")
    async def notes(ctx: commands.Context, *, text: str = "") -> None:
        await ctx.send(handle_notes_text(text, extract_fn=extract_fn))

    return bot


def main() -> None:
    """Entry point: `uv run python -m notes12.discord_bot`."""
    bot = create_bot()
    bot.run(resolve_discord_token())


if __name__ == "__main__":
    main()
