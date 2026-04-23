"""Tests for the Inference panel — cache bar renderer and widget behaviour."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Label, Static

from kai_devtools._action_client import ActionClient
from kai_devtools._app import InferencePanel, format_uptime, render_cache_bar
from kai_devtools._reader import DaemonStateReader

# ---------------------------------------------------------------------------
# render_cache_bar — pure function, no TUI
# ---------------------------------------------------------------------------


def test_bar_green_below_75() -> None:
    bar = render_cache_bar(0.50, None)
    assert "green" in bar
    assert "red" not in bar
    assert "yellow" not in bar


def test_bar_amber_between_75_and_90() -> None:
    bar = render_cache_bar(0.80, None)
    assert "yellow" in bar
    assert "red" not in bar


def test_bar_red_above_90() -> None:
    bar = render_cache_bar(0.95, None)
    assert "red" in bar


def test_bar_checkpoint_marker_present() -> None:
    bar = render_cache_bar(0.50, 0.30)
    assert "magenta" in bar
    assert "│" in bar


def test_bar_no_checkpoint_when_none() -> None:
    bar = render_cache_bar(0.50, None)
    assert "│" not in bar


def test_bar_full_cache_no_empty_chars() -> None:
    bar = render_cache_bar(1.0, None)
    assert "░" not in bar


def test_bar_empty_cache_no_fill_chars() -> None:
    bar = render_cache_bar(0.0, None)
    assert "█" not in bar


def test_bar_clamped_above_one() -> None:
    # Should not raise or produce garbage
    bar = render_cache_bar(1.5, None)
    assert bar  # non-empty


def test_bar_exactly_at_75_threshold() -> None:
    # 0.75 → amber
    bar = render_cache_bar(0.75, None)
    assert "yellow" in bar


def test_bar_exactly_at_90_threshold() -> None:
    # 0.90 → red
    bar = render_cache_bar(0.90, None)
    assert "red" in bar


def test_bar_checkpoint_in_empty_region() -> None:
    # ck_frac > fill_frac: checkpoint marker appears in the empty area
    bar = render_cache_bar(0.20, 0.50)
    assert "magenta" in bar
    assert "│" in bar


# ---------------------------------------------------------------------------
# format_uptime — pure function
# ---------------------------------------------------------------------------


def test_format_uptime_seconds() -> None:
    assert format_uptime(45) == "45s"


def test_format_uptime_minutes() -> None:
    assert format_uptime(90) == "1m 30s"


def test_format_uptime_hours() -> None:
    assert format_uptime(3661) == "1h 1m"


# ---------------------------------------------------------------------------
# InferencePanel widget — smoke tests
# ---------------------------------------------------------------------------

_KV_STATUS: dict[str, Any] = {
    "cache_used_tokens": 1842,
    "cache_capacity_tokens": 8192,
    "cache_used_fraction": 0.225,
    "checkpoint_present": True,
    "checkpoint_tokens": 1204,
    "last_operation": "checkpoint",
    "last_operation_at": "2026-04-06T21:44:01Z",
    "model": "test-model",
    "uptime_seconds": 3124,
}


class _MockClient(ActionClient):
    """ActionClient that returns a pre-set KV status without network calls."""

    def __init__(self, status: dict[str, Any] | None, connected: bool) -> None:
        super().__init__(base_url="http://127.0.0.1:1")
        self._mock_status = status
        self._mock_connected = connected

    def fetch_kv_status(self) -> tuple[dict[str, Any] | None, bool]:
        return self._mock_status, self._mock_connected


class _InferencePanelApp(App[None]):
    def __init__(self, reader: DaemonStateReader, client: ActionClient) -> None:
        super().__init__()
        self._reader = reader
        self._client = client

    def compose(self) -> ComposeResult:
        yield InferencePanel(
            self._reader,
            self._client,
            id="panel",
        )


def test_inference_panel_mounts_connected(data_dir: Path) -> None:
    """Panel renders without error when KV server is online."""

    async def run() -> None:
        client = _MockClient(status=_KV_STATUS, connected=True)
        app = _InferencePanelApp(DaemonStateReader(data_dir), client)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()
            panel = pilot.app.query_one("#panel", InferencePanel)
            conn = panel.query_one("#kv-conn-status", Label)
            assert "ONLINE" in str(conn.render())

    asyncio.run(run())


def test_inference_panel_mounts_disconnected(data_dir: Path) -> None:
    """Panel degrades gracefully when KV server is unreachable."""

    async def run() -> None:
        client = _MockClient(status=None, connected=False)
        app = _InferencePanelApp(DaemonStateReader(data_dir), client)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()
            panel = pilot.app.query_one("#panel", InferencePanel)
            conn = panel.query_one("#kv-conn-status", Label)
            assert "OFFLINE" in str(conn.render())

    asyncio.run(run())


def test_inference_panel_ops_table_populated(data_dir: Path) -> None:
    """Ops table shows entries from inference_calls.jsonl."""

    async def run() -> None:
        client = _MockClient(status=None, connected=False)
        app = _InferencePanelApp(DaemonStateReader(data_dir), client)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = pilot.app.query_one("#panel", InferencePanel)
            table = panel.query_one("#ops-table", DataTable)
            assert table.row_count == 2

    asyncio.run(run())


def test_inference_panel_filter_primitive(data_dir: Path) -> None:
    """Filtering by primitive reduces the ops table rows."""
    from textual.widgets import Input

    async def run() -> None:
        client = _MockClient(status=None, connected=False)
        app = _InferencePanelApp(DaemonStateReader(data_dir), client)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = pilot.app.query_one("#panel", InferencePanel)
            # Set the filter value directly — triggers Input.Changed via reactive
            filter_input = panel.query_one("#ops-filter", Input)
            filter_input.value = "prefill"
            await pilot.pause()
            table = panel.query_one("#ops-table", DataTable)
            assert table.row_count == 1

    asyncio.run(run())


def test_inference_panel_disconnected_shows_no_data(data_dir: Path) -> None:
    """When never connected, bar shows a no-data message."""

    async def run() -> None:
        client = _MockClient(status=None, connected=False)
        app = _InferencePanelApp(DaemonStateReader(data_dir), client)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()
            panel = pilot.app.query_one("#panel", InferencePanel)
            bar = panel.query_one("#kv-bar", Static)
            assert "No data" in str(bar.render())

    asyncio.run(run())
