"""Tests for ChatPanel — message formatting, payload construction, error path."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from http.client import HTTPMessage
from pathlib import Path
from typing import Any
from unittest import mock

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from kai_devtools._app import ChatPanel, format_chat_message
from kai_devtools._reader import DaemonStateReader


class _ChatApp(App[None]):
    def __init__(
        self,
        reader: DaemonStateReader,
        conv_url: str = "http://localhost:9272",
    ) -> None:
        super().__init__()
        self._reader = reader
        self._conv_url = conv_url

    def compose(self) -> ComposeResult:
        yield ChatPanel(self._reader, self._conv_url, id="panel")


def _make_ok_response(content: str) -> Any:
    resp = mock.MagicMock()
    resp.__enter__ = mock.MagicMock(return_value=resp)
    resp.__exit__ = mock.MagicMock(return_value=False)
    resp.read.return_value = json.dumps(
        {"choices": [{"message": {"content": content}}]}
    ).encode()
    return resp


async def _poll_for(condition: Any, timeout: float = 2.0) -> bool:
    """Poll condition() with small sleeps, returning True if it becomes True."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
        if condition():
            return True
    return False


# ---------------------------------------------------------------------------
# Message formatting — pure function
# ---------------------------------------------------------------------------


def test_user_message_has_cyan_you_prefix() -> None:
    result = format_chat_message("user", "hello")
    assert "[bold cyan]You:[/bold cyan]" in result
    assert "hello" in result


def test_assistant_message_has_magenta_kai_prefix() -> None:
    result = format_chat_message("assistant", "hi there")
    assert "[bold magenta]Kai:[/bold magenta]" in result
    assert "hi there" in result


def test_user_message_contains_no_magenta() -> None:
    assert "magenta" not in format_chat_message("user", "test")


def test_assistant_message_contains_no_cyan() -> None:
    assert "cyan" not in format_chat_message("assistant", "test")


def test_message_content_preserved() -> None:
    content = "a fairly long message with punctuation: yes!"
    assert content in format_chat_message("user", content)
    assert content in format_chat_message("assistant", content)


# ---------------------------------------------------------------------------
# Payload construction — correct OpenAI format, full history sent
# ---------------------------------------------------------------------------


def test_payload_openai_format(data_dir: Path) -> None:
    """POSTed body contains 'model' and 'messages' keys in OpenAI format."""
    captured: list[dict[str, Any]] = []

    def fake_urlopen(req: urllib.request.Request, timeout: int | None = None) -> Any:
        assert isinstance(req.data, bytes)
        captured.append(json.loads(req.data))
        return _make_ok_response("Reply")

    async def run() -> None:
        app = _ChatApp(DaemonStateReader(data_dir))
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one("#panel", ChatPanel)
                inp = panel.query_one("#chat-input", Input)
                inp.value = "Hello"
                inp.post_message(Input.Submitted(inp, "Hello"))
                await pilot.pause()
                await asyncio.sleep(0.3)
                await pilot.pause()

    asyncio.run(run())
    assert len(captured) == 1
    body = captured[0]
    assert "model" in body
    assert "messages" in body
    msgs = body["messages"]
    assert isinstance(msgs, list)
    assert msgs[-1]["role"] == "user"
    assert "Hello" in msgs[-1]["content"]


def test_payload_sends_full_history(data_dir: Path) -> None:
    """Second request includes prior assistant turn in the messages array."""
    captured: list[list[dict[str, str]]] = []
    call_count = 0

    def fake_urlopen(req: urllib.request.Request, timeout: int | None = None) -> Any:
        nonlocal call_count
        assert isinstance(req.data, bytes)
        data: dict[str, Any] = json.loads(req.data)
        captured.append(data["messages"])
        resp = _make_ok_response(f"Reply {call_count + 1}")
        call_count += 1
        return resp

    async def run() -> None:
        app = _ChatApp(DaemonStateReader(data_dir))
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one("#panel", ChatPanel)
                inp = panel.query_one("#chat-input", Input)

                inp.value = "First"
                inp.post_message(Input.Submitted(inp, "First"))
                await pilot.pause()
                await asyncio.sleep(0.3)
                await pilot.pause()

                inp.value = "Second"
                inp.post_message(Input.Submitted(inp, "Second"))
                await pilot.pause()
                await asyncio.sleep(0.3)
                await pilot.pause()

    asyncio.run(run())
    assert len(captured) == 2
    assert captured[0][0]["role"] == "user"
    assert "First" in captured[0][0]["content"]
    roles = [m["role"] for m in captured[1]]
    assert roles == ["user", "assistant", "user"]
    assert "Second" in captured[1][-1]["content"]


# ---------------------------------------------------------------------------
# Error path — non-200 / network failure shows error inline, input re-enabled
# ---------------------------------------------------------------------------


def test_http_error_shows_inline_error(data_dir: Path) -> None:
    """HTTPError from the conv server shows an error message and re-enables input."""

    def fake_urlopen(req: urllib.request.Request, timeout: int | None = None) -> Any:
        raise urllib.error.HTTPError(
            req.full_url, 503, "Service Unavailable", HTTPMessage(), None
        )

    async def run() -> None:
        app = _ChatApp(DaemonStateReader(data_dir))
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one("#panel", ChatPanel)
                inp = panel.query_one("#chat-input", Input)

                inp.value = "Hello"
                inp.post_message(Input.Submitted(inp, "Hello"))
                await pilot.pause()

                # Poll until input is re-enabled (signals _on_error ran)
                history = panel.query_one("#chat-history")
                re_enabled = await _poll_for(lambda: not inp.disabled)
                assert re_enabled, "Input was not re-enabled after error"

                # Poll until error text is mounted in history
                error_shown = await _poll_for(
                    lambda: any(
                        "Error" in str(s.render()) for s in history.query(Static)
                    )
                )
                assert error_shown, "Error message not shown in conversation history"

    asyncio.run(run())


def test_network_error_shows_inline_error(data_dir: Path) -> None:
    """Connection failure shows an error message and re-enables input."""

    def fake_urlopen(req: urllib.request.Request, timeout: int | None = None) -> Any:
        raise OSError("Connection refused")

    async def run() -> None:
        app = _ChatApp(DaemonStateReader(data_dir))
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one("#panel", ChatPanel)
                inp = panel.query_one("#chat-input", Input)

                inp.value = "Hello"
                inp.post_message(Input.Submitted(inp, "Hello"))
                await pilot.pause()

                history = panel.query_one("#chat-history")
                re_enabled = await _poll_for(lambda: not inp.disabled)
                assert re_enabled, "Input was not re-enabled after error"

                error_shown = await _poll_for(
                    lambda: any(
                        "Error" in str(s.render()) for s in history.query(Static)
                    )
                )
                assert error_shown, "Error message not shown in conversation history"

    asyncio.run(run())


def test_input_initially_enabled(data_dir: Path) -> None:
    """Chat input is enabled and generating indicator is hidden on mount."""

    async def run() -> None:
        app = _ChatApp(DaemonStateReader(data_dir))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = pilot.app.query_one("#panel", ChatPanel)
            inp = panel.query_one("#chat-input", Input)
            gen = panel.query_one("#chat-generating", Static)
            assert not inp.disabled
            assert not gen.display

    asyncio.run(run())
