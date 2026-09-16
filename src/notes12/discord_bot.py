"""Minimal Discord bot (V1).

Thin layer over the V0 extraction interface:

    Discord !notes <text> -> extract_notes(text) -> Title/Summary/Map type reply.

No Gemini internals, retry logic, JSON parsing, or schema validation here.
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable

import discord
from discord.ext import commands

from notes12 import GeminiExtractionError, Notes12Document, extract_notes

logger = logging.getLogger(__name__)

USAGE_MESSAGE = "Please provide some text after the command. Usage: !notes <text>"
FAILURE_MESSAGE = "Sorry, I couldn't extract notes from that text. Please try again later."

ExtractFn = Callable[[str], Notes12Document]


def format_notes_reply(document: Notes12Document) -> str:
    """Format a validated document as a compact Discord reply."""
    return f"Title: {document.title}\nSummary: {document.summary}\nMap type: {document.map_type}"


def build_notes_embed(document: Notes12Document) -> discord.Embed:
    """Build a Discord embed for a validated document (title/summary/map type)."""
    embed = discord.Embed(title=document.title, description=document.summary)
    embed.add_field(name="Map type", value=document.map_type, inline=False)
    return embed


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


def _configure_logging() -> None:
    """Ensure timing INFO logs are visible for normal module runs."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


def create_bot(*, extract_fn: ExtractFn = extract_notes) -> commands.Bot:
    """Create the minimal !notes bot. No network I/O until the caller runs it."""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.command(name="notes")
    async def notes(ctx: commands.Context, *, text: str = "") -> None:
        # Minimal measurement-only timing (easy to remove later). Logs durations
        # only — never keys, tokens, raw text, or model output.
        start = time.perf_counter()
        if not isinstance(text, str) or not text.strip():
            await ctx.send(USAGE_MESSAGE)
            total_ms = (time.perf_counter() - start) * 1000
            logger.info("notes timing outcome=empty total_ms=%.1f", total_ms)
            return
        dispatch_ms = (time.perf_counter() - start) * 1000
        input_chars = len(text)
        extract_start = time.perf_counter()
        try:
            # extract_notes() is synchronous (blocking network I/O + sleep for
            # retries), so run it in a worker thread to avoid blocking the
            # Discord gateway heartbeat.
            document = await asyncio.to_thread(extract_fn, text)
        except GeminiExtractionError:
            extract_ms = (time.perf_counter() - extract_start) * 1000
            total_ms = (time.perf_counter() - start) * 1000
            await ctx.send(FAILURE_MESSAGE)
            logger.info(
                "notes timing outcome=error dispatch_ms=%.1f extract_ms=%.1f "
                "total_ms=%.1f input_chars=%d",
                dispatch_ms,
                extract_ms,
                total_ms,
                input_chars,
            )
            return
        extract_ms = (time.perf_counter() - extract_start) * 1000
        respond_start = time.perf_counter()
        await ctx.send(embed=build_notes_embed(document))
        respond_ms = (time.perf_counter() - respond_start) * 1000
        total_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "notes timing outcome=success dispatch_ms=%.1f extract_ms=%.1f "
            "respond_ms=%.1f total_ms=%.1f input_chars=%d",
            dispatch_ms,
            extract_ms,
            respond_ms,
            total_ms,
            input_chars,
        )

    return bot


def main() -> None:
    """Entry point: `uv run python -m notes12.discord_bot`."""
    _configure_logging()
    bot = create_bot()
    bot.run(resolve_discord_token())


if __name__ == "__main__":
    main()
