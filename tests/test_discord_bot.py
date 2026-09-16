"""Deterministic offline tests for the V1 Discord layer.

No Discord connection, no bot token, no Gemini API calls.
The extraction boundary is faked via extract_fn injection.
"""

import asyncio
import logging
import threading
from typing import Any, cast

from notes12.discord_bot import (
    FAILURE_MESSAGE,
    USAGE_MESSAGE,
    _configure_logging,
    build_notes_embed,
    create_bot,
    format_notes_reply,
    handle_notes_text,
    resolve_discord_token,
)
from notes12.extractor import GeminiExtractionError
from notes12.schema import Notes12Document


def make_doc(**overrides: Any) -> Notes12Document:
    payload = {
        "title": "Photosynthesis",
        "summary": "How plants convert light into energy.",
        "map_type": "hierarchy",
        "nodes": [
            {
                "id": "photosynthesis",
                "label": "Photosynthesis",
                "type": "process",
                "description": "Converts light energy into chemical energy.",
            }
        ],
        "relationships": [],
    }
    payload.update(overrides)
    return Notes12Document.model_validate(payload)


def test_format_notes_reply_contains_title_summary_map_type():
    reply = format_notes_reply(make_doc())
    assert reply == (
        "Title: Photosynthesis\nSummary: How plants convert light into energy.\nMap type: hierarchy"
    )


def test_handle_notes_text_passes_text_through_to_extractor():
    seen: list[str] = []

    def fake_extract(text: str) -> Notes12Document:
        seen.append(text)
        return make_doc()

    reply = handle_notes_text("Photosynthesis converts light energy...", extract_fn=fake_extract)
    assert seen == ["Photosynthesis converts light energy..."]
    assert "Title: Photosynthesis" in reply
    assert "Summary: How plants convert light into energy." in reply
    assert "Map type: hierarchy" in reply


def test_handle_notes_text_empty_does_not_call_extractor():
    for bad in ["", "   ", None, 123]:
        called: list[str] = []

        def fake_extract(text: str, _called: list[str] = called) -> Notes12Document:
            _called.append(text)
            return make_doc()

        assert handle_notes_text(bad, extract_fn=fake_extract) == USAGE_MESSAGE
        assert called == []


def test_handle_notes_text_maps_extraction_error_to_friendly_message():
    def boom(text: str) -> Notes12Document:
        raise GeminiExtractionError("boom: quota exceeded (should not leak)")

    reply = handle_notes_text("some text", extract_fn=boom)
    assert reply == FAILURE_MESSAGE
    assert "boom" not in reply
    assert "Traceback" not in reply


def test_resolve_discord_token_missing_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    try:
        resolve_discord_token()
    except RuntimeError as exc:
        assert "DISCORD_BOT_TOKEN" in str(exc)
    else:  # pragma: no cover - must raise
        raise AssertionError("expected RuntimeError for missing token")


def test_resolve_discord_token_prefers_explicit_and_strips(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-token")
    assert resolve_discord_token(explicit="  explicit-token  ") == "explicit-token"
    assert resolve_discord_token() == "env-token"


class FakeCtx:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.embeds: list[Any] = []

    async def send(self, content: str | None = None, *, embed: Any = None) -> None:
        if embed is not None:
            self.embeds.append(embed)
        if content is not None:
            self.sent.append(content)


def test_build_notes_embed_contains_title_summary_map_type():
    embed = build_notes_embed(make_doc())
    assert embed.title == "Photosynthesis"
    assert embed.description == "How plants convert light into energy."
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "Map type"
    assert embed.fields[0].value == "hierarchy"


def test_bot_registers_notes_command_and_replies(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    bot = create_bot(extract_fn=lambda text: make_doc())
    assert "notes" in bot.all_commands

    ctx = FakeCtx()
    cmd = bot.all_commands["notes"]
    asyncio.run(cast(Any, cmd.callback)(ctx, text="Photosynthesis converts light energy..."))
    assert ctx.sent == []
    assert len(ctx.embeds) == 1
    assert ctx.embeds[0].title == "Photosynthesis"
    assert ctx.embeds[0].description == "How plants convert light into energy."
    assert ctx.embeds[0].fields[0].value == "hierarchy"


def test_bot_notes_command_with_empty_text_sends_usage():
    bot = create_bot(extract_fn=lambda text: make_doc())
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="   "))
    assert ctx.sent == [USAGE_MESSAGE]
    assert ctx.embeds == []


def test_bot_notes_command_maps_extraction_error():
    def boom(text: str) -> Notes12Document:
        raise GeminiExtractionError("internal failure")

    bot = create_bot(extract_fn=boom)
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="real input"))
    assert ctx.sent == [FAILURE_MESSAGE]
    assert ctx.embeds == []


def test_bot_runs_extraction_via_to_thread(monkeypatch):
    calls: list[tuple[Any, tuple[Any, ...]]] = []
    real_to_thread = asyncio.to_thread

    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append((func, args))
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    seen: list[str] = []

    def fake_extract(text: str) -> Notes12Document:
        seen.append(text)
        return make_doc()

    bot = create_bot(extract_fn=fake_extract)
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="hello world"))
    assert seen == ["hello world"]
    assert len(calls) == 1
    assert calls[0][0] is fake_extract
    assert calls[0][1] == ("hello world",)
    assert len(ctx.embeds) == 1


def test_bot_empty_input_does_not_touch_to_thread(monkeypatch):
    async def boom_to_thread(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("to_thread must not be called for empty input")

    monkeypatch.setattr(asyncio, "to_thread", boom_to_thread)
    bot = create_bot(extract_fn=lambda text: make_doc())
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="   "))
    assert ctx.sent == [USAGE_MESSAGE]
    assert ctx.embeds == []


def test_bot_does_not_block_event_loop_while_extracting():
    entered = threading.Event()
    release = threading.Event()

    def blocking_extract(text: str) -> Notes12Document:
        entered.set()
        assert release.wait(timeout=5), "timed out waiting for release"
        return make_doc()

    async def main() -> None:
        bot = create_bot(extract_fn=blocking_extract)
        ctx = FakeCtx()
        task = asyncio.create_task(
            cast(Any, bot.all_commands["notes"].callback)(ctx, text="slow input")
        )
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), "extraction never started off the event loop"
        # If extraction blocked the loop, this sleep could not complete while
        # the worker is still gated on `release`.
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.wait_for(task, timeout=5)
        assert len(ctx.embeds) == 1
        assert ctx.embeds[0].title == "Photosynthesis"

    asyncio.run(main())


def test_bot_timing_log_success_without_raw_text(caplog):
    caplog.set_level(logging.INFO, logger="notes12.discord_bot")
    secret_marker = "unique-raw-input-xyz-12345"
    bot = create_bot(extract_fn=lambda text: make_doc())
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text=secret_marker))
    assert len(ctx.embeds) == 1
    timing = [r for r in caplog.records if "notes timing" in r.getMessage()]
    assert len(timing) == 1
    message = timing[0].getMessage()
    assert "outcome=success" in message
    assert "extract_ms=" in message and "respond_ms=" in message
    assert secret_marker not in message


def test_bot_timing_log_error_and_empty(caplog):
    caplog.set_level(logging.INFO, logger="notes12.discord_bot")

    def boom(text: str) -> Notes12Document:
        raise GeminiExtractionError("internal failure")

    bot = create_bot(extract_fn=boom)
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="real input"))
    assert ctx.sent == [FAILURE_MESSAGE]
    assert "outcome=error" in caplog.text

    caplog.clear()
    bot = create_bot(extract_fn=lambda text: make_doc())
    ctx = FakeCtx()
    asyncio.run(cast(Any, bot.all_commands["notes"].callback)(ctx, text="   "))
    assert ctx.sent == [USAGE_MESSAGE]
    assert "outcome=empty" in caplog.text


def test_configure_logging_enables_info_level(monkeypatch):
    calls: dict[str, Any] = {}
    real_basic_config = logging.basicConfig

    def fake_basic_config(*args: Any, **kwargs: Any) -> None:
        calls.update(kwargs)
        calls["called"] = True

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)
    _configure_logging()
    assert calls.get("called") is True
    assert calls.get("level") == logging.INFO
    # Real call is idempotent and must not raise.
    monkeypatch.setattr(logging, "basicConfig", real_basic_config)
    _configure_logging()
