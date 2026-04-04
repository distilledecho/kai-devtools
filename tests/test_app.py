"""Widget-level tests for VersionedDocPanel version selector."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Label, Select, Static

from kai_devtools._app import VersionedDocPanel
from kai_devtools._reader import DaemonStateReader


class _PanelApp(App[None]):
    """Minimal host app that renders a single VersionedDocPanel."""

    def __init__(self, reader: DaemonStateReader, doc_name: str) -> None:
        super().__init__()
        self._reader = reader
        self._doc_name = doc_name

    def compose(self) -> ComposeResult:
        yield VersionedDocPanel(self._reader, self._doc_name, id="panel")


def _diff_label_text(pilot: object) -> str:  # type: ignore[type-arg]
    from textual.pilot import Pilot

    assert isinstance(pilot, Pilot)
    panel = pilot.app.query_one("#panel", VersionedDocPanel)
    label = panel.query_one("#diff-label", Label)
    return str(label.render())


def _diff_content_text(pilot: object) -> str:  # type: ignore[type-arg]
    from textual.pilot import Pilot

    assert isinstance(pilot, Pilot)
    panel = pilot.app.query_one("#panel", VersionedDocPanel)
    static = panel.query_one("#diff-content", Static)
    return str(static.render())


def _select_value(pilot: object) -> object:  # type: ignore[type-arg]
    from textual.pilot import Pilot

    assert isinstance(pilot, Pilot)
    panel = pilot.app.query_one("#panel", VersionedDocPanel)
    sel = panel.query_one("#baseline-select", Select)
    return sel.value


# ---------------------------------------------------------------------------
# Default selection: diffs against the immediately prior (most recent) version
# ---------------------------------------------------------------------------


def test_versioned_panel_default_selects_prior_version(data_dir: Path) -> None:
    """After mount the Select defaults to history[-1] — most recent prior version."""

    async def run() -> None:
        app = _PanelApp(DaemonStateReader(data_dir), "daemon_self")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            # daemon_self history: [v1, v2]; current: v3 → default baseline index 1 (v2)
            assert _select_value(pilot) == 1
            assert "v2" in _diff_label_text(pilot)
            assert "v3" in _diff_label_text(pilot)

    asyncio.run(run())


def test_versioned_panel_default_diff_content_references_prior_field(
    data_dir: Path,
) -> None:
    """Diff content shows the change from the default baseline (v2) to current (v3)."""

    async def run() -> None:
        app = _PanelApp(DaemonStateReader(data_dir), "daemon_self")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            text = _diff_content_text(pilot)
            # v2 has who_daemon_is="Version 2 self." → removed in current
            assert "Version 2 self." in text
            # current has who_daemon_is="A curious entity." → added
            assert "A curious entity." in text

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Selecting an earlier version updates the diff to use that version as baseline
# ---------------------------------------------------------------------------


def test_versioned_panel_selecting_earlier_version_changes_diff(data_dir: Path) -> None:
    """Changing the Select to an earlier version re-diffs against that version."""

    async def run() -> None:
        app = _PanelApp(DaemonStateReader(data_dir), "daemon_self")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            # Change baseline from v2 (index 1) to v1 (index 0)
            panel = pilot.app.query_one("#panel", VersionedDocPanel)
            sel = panel.query_one("#baseline-select", Select)
            sel.value = 0
            await pilot.pause()
            assert _select_value(pilot) == 0
            assert "v1" in _diff_label_text(pilot)
            assert "v3" in _diff_label_text(pilot)

    asyncio.run(run())


def test_versioned_panel_earlier_version_diff_content(data_dir: Path) -> None:
    """Diff against v1 shows v1-specific content being replaced by current."""

    async def run() -> None:
        app = _PanelApp(DaemonStateReader(data_dir), "daemon_self")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            panel = pilot.app.query_one("#panel", VersionedDocPanel)
            sel = panel.query_one("#baseline-select", Select)
            sel.value = 0  # baseline = v1
            await pilot.pause()
            text = _diff_content_text(pilot)
            # v1 has who_daemon_is="Version 1 self." → should appear as removed
            assert "Version 1 self." in text

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Works for DAEMON_RELATIONAL (single history entry → defaults to that entry)
# ---------------------------------------------------------------------------


def test_versioned_panel_relational_default_baseline(data_dir: Path) -> None:
    """DAEMON_RELATIONAL has one history entry; default baseline is that entry."""

    async def run() -> None:
        app = _PanelApp(DaemonStateReader(data_dir), "daemon_relational")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            # daemon_relational history: [v1]; current: v2 → baseline index 0
            assert _select_value(pilot) == 0
            assert "v1" in _diff_label_text(pilot)
            assert "v2" in _diff_label_text(pilot)

    asyncio.run(run())
