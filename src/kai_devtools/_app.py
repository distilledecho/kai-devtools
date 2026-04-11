"""Textual TUI for the kai-devtools observability panel (§13).

Thirteen surfaces across twelve tabs:
    Workflows  Scratch  Holding  DAEMON_SELF  DAEMON_REL  Distillation
    Threads    Push     Register  Memory       Contradictions  BORDERLINE

Read surfaces auto-refresh every 10 seconds or on manual 'r' keypress.
Write actions (contradiction resolve/dismiss, BORDERLINE promote/discard)
are posted to the daemon action API via ActionClient — never written directly.
"""

from __future__ import annotations

import difflib
import textwrap
from datetime import UTC, datetime, timedelta
from typing import Any

import yaml
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from ._action_client import ActionClient, ActionResult
from ._reader import DaemonStateReader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_URGENCY_COLOR = {"high": "red", "medium": "yellow", "low": "green"}
_STATUS_COLOR = {
    "success": "green",
    "failure": "red",
    "abandoned": "yellow",
    "active": "green",
    "dormant": "yellow",
    "archived": "dim",
    "nascent": "blue",
    "pending": "yellow",
    "promoted": "green",
    "discarded": "dim",
}


def _color(text: str, color: str | None) -> str:
    if not color:
        return text
    return f"[{color}]{text}[/{color}]"


def _ts(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso)[:16]


def _short(s: str | None, n: int = 8) -> str:
    if not s:
        return "—"
    return s[:n]


def _age(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            return f"{hours}h"
        return f"{days}d"
    except (ValueError, TypeError):
        return "?"


_BAR_WIDTH = 60


def render_cache_bar(fill_frac: float, ck_frac: float | None) -> str:
    """Build a Rich markup string for the KV cache fill bar.

    Parameters
    ----------
    fill_frac:
        Cache fill as a fraction in [0, 1].
    ck_frac:
        Checkpoint position as a fraction in [0, 1], or None if absent.
    """
    fill_frac = max(0.0, min(fill_frac, 1.0))
    if fill_frac >= 0.90:
        fill_color = "red"
    elif fill_frac >= 0.75:
        fill_color = "yellow"
    else:
        fill_color = "green"

    fill_pos = round(fill_frac * _BAR_WIDTH)
    ck_pos: int | None = None
    if ck_frac is not None:
        ck_pos = round(max(0.0, min(ck_frac, 1.0)) * _BAR_WIDTH)

    chars: list[tuple[str, str]] = []
    for i in range(_BAR_WIDTH):
        if ck_pos is not None and i == ck_pos:
            chars.append(("cyan", "│"))
        elif i < fill_pos:
            chars.append((fill_color, "█"))
        else:
            chars.append(("dim", "░"))

    if not chars:
        return ""
    parts: list[str] = []
    cur_color, cur_text = chars[0]
    for color, ch in chars[1:]:
        if color == cur_color:
            cur_text += ch
        else:
            parts.append(f"[{cur_color}]{cur_text}[/{cur_color}]")
            cur_color, cur_text = color, ch
    parts.append(f"[{cur_color}]{cur_text}[/{cur_color}]")
    return "".join(parts)


def format_uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


def _age_days(iso: str | None) -> float:
    """Return age in fractional days, or 0 if unparseable."""
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0


def _yaml_dump(obj: Any) -> str:
    try:
        return yaml.dump(
            obj, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
    except Exception:
        return str(obj)


def _unified_diff(old_text: str, old_label: str, new_text: str, new_label: str) -> str:
    lines_old = old_text.splitlines(keepends=True)
    lines_new = new_text.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(lines_old, lines_new, fromfile=old_label, tofile=new_label)
    )
    return "".join(diff) if diff else "(no differences)"


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------


class StatusBar(Static):
    """One-line info bar shown at the bottom of every tab."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """


# ---------------------------------------------------------------------------
# Panel base class
# ---------------------------------------------------------------------------


class RefreshPanel(ScrollableContainer):
    """Base class for panels that can be refreshed from the reader."""

    def __init__(self, reader: DaemonStateReader, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reader = reader

    def refresh_data(self) -> None:
        """Called when the user presses 'r' or the auto-refresh timer fires."""


# ---------------------------------------------------------------------------
# 1. Workflow runs
# ---------------------------------------------------------------------------


class WorkflowsPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter by workflow name…", id="workflows-filter")
        yield DataTable(id="workflows-table")

    def on_mount(self) -> None:
        table = self.query_one("#workflows-table", DataTable)
        table.add_columns(
            "Started", "Workflow", "Trigger", "Status", "Memory", "Duration"
        )
        self.refresh_data()

    @on(Input.Changed, "#workflows-filter")
    def _on_filter_changed(self, _event: Input.Changed) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#workflows-table", DataTable)
        filter_input = self.query_one("#workflows-filter", Input)
        needle = filter_input.value.lower()
        table.clear()
        runs = self._reader.workflow_runs()
        for run in reversed(runs[-200:]):
            name = run.get("workflow_name", "")
            if needle and needle not in name.lower():
                continue
            status = run.get("status", "")
            started = _ts(run.get("started_at"))
            completed = run.get("completed_at", "")
            try:
                dur = ""
                if started and completed:
                    s = datetime.fromisoformat(run.get("started_at", ""))
                    e = datetime.fromisoformat(completed)
                    dur = f"{(e - s).total_seconds():.1f}s"
            except Exception:
                dur = ""
            mem = "✓" if run.get("memory_server_available") else "✗"
            table.add_row(
                started,
                name,
                run.get("trigger", ""),
                _color(status, _STATUS_COLOR.get(status)),
                mem,
                dur,
            )


# ---------------------------------------------------------------------------
# 2. Scratch space
# ---------------------------------------------------------------------------


class ScratchPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="scratch-table")

    def on_mount(self) -> None:
        table = self.query_one("#scratch-table", DataTable)
        table.add_columns("ID", "Type", "Lifecycle", "Origin", "Workflow", "TTL", "Age")
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#scratch-table", DataTable)
        table.clear()
        for note in self._reader.scratch():
            lc = note.get("lifecycle", "")
            table.add_row(
                _short(note.get("id")),
                note.get("type", ""),
                _color(lc, "dim" if lc == "archived" else None),
                note.get("epistemic_origin", ""),
                note.get("workflow_id", ""),
                _ts(note.get("ttl")),
                _age(note.get("timestamp")),
            )


# ---------------------------------------------------------------------------
# 3. Holding store
# ---------------------------------------------------------------------------


class HoldingPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="holding-table")

    def on_mount(self) -> None:
        table = self.query_one("#holding-table", DataTable)
        table.add_columns(
            "ID", "Type", "Urgency", "Register", "Relevance Trigger", "Age"
        )
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#holding-table", DataTable)
        table.clear()
        for item in self._reader.holding():
            urgency = item.get("urgency", "")
            table.add_row(
                _short(item.get("id")),
                item.get("type", ""),
                _color(urgency, _URGENCY_COLOR.get(urgency)),
                item.get("register_needed", ""),
                item.get("relevance_trigger", ""),
                _age(item.get("created")),
            )


# ---------------------------------------------------------------------------
# 4 & 5. Versioned YAML viewer with diff (DAEMON_SELF / DAEMON_RELATIONAL)
# ---------------------------------------------------------------------------


class VersionedDocPanel(RefreshPanel):
    """Viewer for DAEMON_SELF or DAEMON_RELATIONAL with version diff."""

    def __init__(
        self,
        reader: DaemonStateReader,
        doc_name: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(reader, **kwargs)
        self._doc_name = doc_name  # "daemon_self" or "daemon_relational"
        self._history: list[dict[str, Any]] = []

    def _load_current(self) -> dict[str, Any] | None:
        if self._doc_name == "daemon_self":
            return self._reader.daemon_self()
        return self._reader.daemon_relational()

    def _load_history(self) -> list[dict[str, Any]]:
        if self._doc_name == "daemon_self":
            return self._reader.daemon_self_history()
        return self._reader.daemon_relational_history()

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="current-pane"):
                yield Label("[bold]Current version[/bold]", id="current-label")
                yield Static("", id="current-content")
            with Vertical(id="diff-pane"):
                yield Select(
                    [],
                    id="baseline-select",
                    allow_blank=True,
                    prompt="Select baseline version",
                )
                yield Label("[bold]Diff[/bold]", id="diff-label")
                yield Static("", id="diff-content")

    def on_mount(self) -> None:
        self.refresh_data()

    @on(Select.Changed, "#baseline-select")
    def on_baseline_changed(self, _event: Select.Changed) -> None:
        self._render_diff()

    def refresh_data(self) -> None:
        current = self._load_current()
        self._history = self._load_history()

        current_label = self.query_one("#current-label", Label)
        current_content = self.query_one("#current-content", Static)
        diff_content = self.query_one("#diff-content", Static)

        if current is None:
            current_label.update("[bold]Current version[/bold] — not written yet")
            current_content.update("(no data)")
            diff_content.update("(no data)")
            return

        ver = current.get("version", "?")
        ts = _ts(current.get("timestamp"))
        current_label.update(f"[bold]Current — v{ver}[/bold] ({ts})")
        current_content.update(textwrap.indent(_yaml_dump(current), "  "))

        select = self.query_one("#baseline-select", Select)
        if self._history:
            options = [
                (f"v{h.get('version', '?')}  ({_ts(h.get('timestamp'))})", i)
                for i, h in enumerate(self._history)
            ]
            select.set_options(options)
            # Default: most recent prior version (last entry in history list).
            # Setting select.value fires Select.Changed → on_baseline_changed
            # → _render_diff, so no explicit _render_diff() call is needed here.
            select.value = len(self._history) - 1
        else:
            select.set_options([])
            self._render_diff()

    def _render_diff(self) -> None:
        current = self._load_current()
        diff_label = self.query_one("#diff-label", Label)
        diff_content = self.query_one("#diff-content", Static)

        if current is None:
            diff_content.update("(no data)")
            return

        select = self.query_one("#baseline-select", Select)
        idx = select.value

        if idx is Select.NULL or not isinstance(idx, int):
            diff_content.update("(no prior versions)")
            return

        ver = current.get("version", "?")
        baseline = self._history[idx]
        prev_ver = baseline.get("version", "?")
        diff_label.update(f"[bold]Diff[/bold]: v{prev_ver} → v{ver}")
        diff_text = _unified_diff(
            _yaml_dump(baseline),
            f"v{prev_ver}",
            _yaml_dump(current),
            f"v{ver}",
        )
        colored_lines: list[str] = []
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                colored_lines.append(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                colored_lines.append(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                colored_lines.append(f"[cyan]{line}[/cyan]")
            else:
                colored_lines.append(line)
        diff_content.update("\n".join(colored_lines))


# ---------------------------------------------------------------------------
# 6. Distillation metrics
# ---------------------------------------------------------------------------


class DistillationPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="distillation-table")

    def on_mount(self) -> None:
        table = self.query_one("#distillation-table", DataTable)
        table.add_columns("Cycle", "Timestamp", "DAEMON_SELF v", "Notes")
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#distillation-table", DataTable)
        table.clear()
        for rec in reversed(self._reader.distillation_metrics()[-50:]):
            notes = rec.get("notes", "")
            # Highlight known health signals
            for sig in ("convergence", "flattery_drift", "oscillation"):
                if sig in notes.lower():
                    notes = _color(notes, "yellow")
                    break
            table.add_row(
                str(rec.get("cycle_number", "")),
                _ts(rec.get("timestamp")),
                str(rec.get("daemon_self_version", "")),
                notes,
            )


# ---------------------------------------------------------------------------
# 7. Thread stack
# ---------------------------------------------------------------------------


class ThreadsPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="threads-table")

    def on_mount(self) -> None:
        table = self.query_one("#threads-table", DataTable)
        table.add_columns(
            "ID", "Title", "Status", "Epistemic", "Last touched", "Dormant since"
        )
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#threads-table", DataTable)
        table.clear()
        for t in self._reader.threads():
            status = t.get("status", "")
            stance = t.get("stance", {}) or {}
            ep = stance.get("epistemic_status", "") if isinstance(stance, dict) else ""
            table.add_row(
                _short(t.get("id")),
                t.get("title", ""),
                _color(status, _STATUS_COLOR.get(status)),
                ep,
                _ts(t.get("last_touched")),
                _ts(t.get("dormant_since")),
            )


# ---------------------------------------------------------------------------
# 8. Push history
# ---------------------------------------------------------------------------


class PushHistoryPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="push-table")
        yield Label("", id="ceiling-label")

    def on_mount(self) -> None:
        table = self.query_one("#push-table", DataTable)
        table.add_columns("ID", "Timestamp", "Age", "Content summary")
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#push-table", DataTable)
        label = self.query_one("#ceiling-label", Label)
        table.clear()

        records = self._reader.push_history()
        for rec in reversed(records[-50:]):
            table.add_row(
                _short(rec.get("id")),
                _ts(rec.get("timestamp")),
                _age(rec.get("timestamp")),
                rec.get("content_summary", ""),
            )

        # Ceiling indicator
        within = False
        if records:
            try:
                last_dt = datetime.fromisoformat(records[-1].get("timestamp", ""))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                within = (datetime.now(UTC) - last_dt) < timedelta(days=7)
            except (ValueError, TypeError):
                pass
        if within:
            label.update("[yellow]⚠ Within 7-day push ceiling[/yellow]")
        else:
            label.update("[green]✓ Push ceiling window clear[/green]")


# ---------------------------------------------------------------------------
# 9. Register inference log
# ---------------------------------------------------------------------------


class RegisterPanel(RefreshPanel):
    def compose(self) -> ComposeResult:
        yield DataTable(id="register-table")

    def on_mount(self) -> None:
        table = self.query_one("#register-table", DataTable)
        table.add_columns("Corrected at", "Inferred", "Corrected to", "Thread ID")
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#register-table", DataTable)
        table.clear()
        for entry in reversed(self._reader.register_inference()[-100:]):
            table.add_row(
                _ts(entry.get("corrected_at")),
                entry.get("inferred_register", ""),
                entry.get("corrected_register", ""),
                _short(entry.get("thread_id"), 12),
            )


# ---------------------------------------------------------------------------
# 10. Memory status (availability + backfill queue)
# ---------------------------------------------------------------------------


class MemoryPanel(RefreshPanel):
    def __init__(
        self,
        reader: DaemonStateReader,
        action_client: ActionClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(reader, **kwargs)
        self._client = action_client
        self._server_url = reader.memory_server_url()

    def compose(self) -> ComposeResult:
        yield Label("", id="mem-status")
        yield Label(f"Server: {self._server_url}", id="mem-url")
        yield Label("", id="queue-status")
        yield DataTable(id="queue-table")

    def on_mount(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        table.add_columns("File", "Age (days)", "Size (bytes)")
        self.refresh_data()

    def refresh_data(self) -> None:
        queue = self._reader.embedding_backfill_queue()
        status_label = self.query_one("#queue-status", Label)
        table = self.query_one("#queue-table", DataTable)
        table.clear()

        if not queue:
            status_label.update("[green]Embedding backfill queue: empty[/green]")
        else:
            oldest = max(e["age_days"] for e in queue)
            status_label.update(
                f"[yellow]Backfill queue: {len(queue)} item(s) — "
                f"oldest {oldest:.1f} days[/yellow]"
            )
            for entry in queue:
                table.add_row(
                    entry["path"],
                    str(entry["age_days"]),
                    str(entry["size_bytes"]),
                )
        # Re-probe server on every refresh (fix 3: timer re-probes availability).
        self._probe_server()

    def _update_mem_status(self, available: bool) -> None:
        """Update the memory-server status label — must run on the main thread."""
        label = self.query_one("#mem-status", Label)
        if available:
            label.update("[green]● Memory server ONLINE[/green]")
        else:
            label.update("[red]● Memory server OFFLINE[/red]")

    @work(thread=True)
    def _probe_server(self) -> None:
        available = self._client.check_memory_server(self._server_url)
        # fix 1: DOM mutation must go through call_from_thread from worker thread.
        self.app.call_from_thread(self._update_mem_status, available)


# ---------------------------------------------------------------------------
# 11. Contradiction candidates
# ---------------------------------------------------------------------------


class ContradictionsPanel(RefreshPanel):
    # fix 2: use ctrl+r so the app-level 'r' refresh binding is never shadowed.
    BINDINGS = [
        Binding("ctrl+r", "resolve_selected", "Resolve"),
        Binding("d", "dismiss_selected", "Dismiss"),
    ]

    def __init__(
        self,
        reader: DaemonStateReader,
        action_client: ActionClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(reader, **kwargs)
        self._client = action_client

    def compose(self) -> ComposeResult:
        yield Label(
            "[bold]Contradiction candidates[/bold]  "
            "[dim]ctrl+r=resolve  d=dismiss[/dim]",
        )
        yield DataTable(id="contra-table", cursor_type="row")
        yield Label("", id="contra-status")

    def on_mount(self) -> None:
        table = self.query_one("#contra-table", DataTable)
        table.add_columns(
            "Contradiction ID", "Item ID", "Type", "Urgency", "Age", "Content"
        )
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#contra-table", DataTable)
        table.clear()
        for item in self._reader.contradiction_candidates():
            urgency = item.get("urgency", "")
            content = item.get("content", "")[:60]
            table.add_row(
                _short(item.get("contradiction_id"), 12),
                _short(item.get("id"), 12),
                item.get("type", ""),
                _color(urgency, _URGENCY_COLOR.get(urgency)),
                _age(item.get("created")),
                content,
                key=item.get("contradiction_id", item.get("id", "")),
            )

    def _selected_contradiction_id(self) -> str | None:
        table = self.query_one("#contra-table", DataTable)
        if table.cursor_row < 0:
            return None
        items = self._reader.contradiction_candidates()
        if table.cursor_row >= len(items):
            return None
        return items[table.cursor_row].get("contradiction_id")

    @work(thread=True)
    def action_resolve_selected(self) -> None:
        cid = self._selected_contradiction_id()
        if not cid:
            return
        result = self._client.contradiction_resolve(cid)
        # fix 1: DOM mutations must go through call_from_thread from worker thread.
        self.app.call_from_thread(self._show_result, result, cid)
        self.app.call_from_thread(self.refresh_data)

    @work(thread=True)
    def action_dismiss_selected(self) -> None:
        cid = self._selected_contradiction_id()
        if not cid:
            return
        result = self._client.contradiction_dismiss(cid)
        self.app.call_from_thread(self._show_result, result, cid)
        self.app.call_from_thread(self.refresh_data)

    def _show_result(self, result: ActionResult, cid: str) -> None:
        label = self.query_one("#contra-status", Label)
        if result.ok:
            label.update(f"[green]✓ Action applied to {cid[:12]}[/green]")
        else:
            label.update(f"[red]✗ Error: {result.error}[/red]")


# ---------------------------------------------------------------------------
# 12. BORDERLINE pool
# ---------------------------------------------------------------------------


class BorderlinePanel(RefreshPanel):
    BINDINGS = [
        Binding("p", "promote_selected", "Promote"),
        Binding("x", "discard_selected", "Discard"),
    ]

    def __init__(
        self,
        reader: DaemonStateReader,
        action_client: ActionClient,
        **kwargs: Any,
    ) -> None:
        super().__init__(reader, **kwargs)
        self._client = action_client

    def compose(self) -> ComposeResult:
        yield Label(
            "[bold]BORDERLINE pool[/bold]  [dim]p=promote  x=discard[/dim]  "
            "[dim](auto-expires 30 days)[/dim]",
        )
        yield DataTable(id="bl-table", cursor_type="row")
        yield Label("", id="bl-status")
        yield Static("", id="bl-detail")

    def on_mount(self) -> None:
        table = self.query_one("#bl-table", DataTable)
        table.add_columns("ID", "Status", "Created", "Age", "Raw output (preview)")
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#bl-table", DataTable)
        table.clear()
        for item in self._reader.borderline_pool():
            status = item.get("status", "")
            age_str = _age(item.get("created"))
            overdue = _age_days(item.get("created")) > 30
            age_cell = f"[red]{age_str}[/red]" if overdue else age_str
            preview = (item.get("raw_output", "") or "")[:80]
            table.add_row(
                _short(item.get("id"), 12),
                _color(status, _STATUS_COLOR.get(status)),
                _ts(item.get("created")),
                age_cell,
                preview,
                key=item.get("id", ""),
            )

    @on(DataTable.RowSelected, "#bl-table")
    def _show_detail(self, event: DataTable.RowSelected) -> None:
        items = self._reader.borderline_pool()
        idx = event.cursor_row
        if 0 <= idx < len(items):
            detail = self.query_one("#bl-detail", Static)
            raw = items[idx].get("raw_output", "")
            detail.update(textwrap.fill(raw, width=100))

    def _selected_item_id(self) -> str | None:
        table = self.query_one("#bl-table", DataTable)
        items = self._reader.borderline_pool()
        if table.cursor_row < 0 or table.cursor_row >= len(items):
            return None
        return items[table.cursor_row].get("id")

    @work(thread=True)
    def action_promote_selected(self) -> None:
        item_id = self._selected_item_id()
        if not item_id:
            return
        result = self._client.borderline_promote(item_id)
        # fix 1: DOM mutations must go through call_from_thread from worker thread.
        self.app.call_from_thread(self._show_result, result, item_id)
        self.app.call_from_thread(self.refresh_data)

    @work(thread=True)
    def action_discard_selected(self) -> None:
        item_id = self._selected_item_id()
        if not item_id:
            return
        result = self._client.borderline_discard(item_id)
        self.app.call_from_thread(self._show_result, result, item_id)
        self.app.call_from_thread(self.refresh_data)

    def _show_result(self, result: ActionResult, item_id: str) -> None:
        label = self.query_one("#bl-status", Label)
        if result.ok:
            label.update(f"[green]✓ Action applied to {item_id[:12]}[/green]")
        else:
            label.update(f"[red]✗ Error: {result.error}[/red]")


# ---------------------------------------------------------------------------
# 13. Inference panel (Stage 3.5)
# ---------------------------------------------------------------------------


class InferencePanel(RefreshPanel):
    """KV cache visualisation + inference operation log."""

    _PRIMITIVE_COLOR: dict[str, str] = {
        "prefill": "blue",
        "generate": "green",
        "checkpoint": "cyan",
        "rollback": "yellow",
        "evict": "red",
    }

    def __init__(
        self,
        reader: DaemonStateReader,
        action_client: ActionClient,
        kv_server_url: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(reader, **kwargs)
        self._client = action_client
        self._kv_url = kv_server_url
        self._last_kv_status: dict[str, Any] | None = None
        self._kv_connected: bool = False

    def compose(self) -> ComposeResult:
        yield Label("[bold]KV Cache[/bold]", id="kv-heading")
        yield Static("", id="kv-bar")
        yield Static("", id="kv-stats")
        yield Label(
            "[bold]Operation Log[/bold]  [dim](inference_calls.jsonl)[/dim]",
            id="ops-heading",
        )
        yield Input(
            placeholder="Filter by primitive…",
            id="ops-filter",
        )
        yield DataTable(id="ops-table")
        yield Label("", id="kv-conn-status")

    def on_mount(self) -> None:
        table = self.query_one("#ops-table", DataTable)
        table.add_columns(
            "Timestamp", "Primitive", "Workflow", "Tokens after", "Duration ms"
        )
        self.refresh_data()
        self.set_interval(5.0, self._tick_kv_poll)

    def _tick_kv_poll(self) -> None:
        self._poll_kv_status()

    @on(Input.Changed, "#ops-filter")
    def _on_filter_changed(self, _event: Input.Changed) -> None:
        self._render_ops_table()

    def refresh_data(self) -> None:
        self._render_ops_table()
        self._poll_kv_status()

    def _render_ops_table(self) -> None:
        table = self.query_one("#ops-table", DataTable)
        filter_input = self.query_one("#ops-filter", Input)
        needle = filter_input.value.strip().lower()
        table.clear()
        for entry in reversed(self._reader.inference_calls()[-200:]):
            prim = entry.get("primitive", "")
            if needle and needle not in prim.lower():
                continue
            prim_color = self._PRIMITIVE_COLOR.get(prim, "white")
            wf = entry.get("workflow_id") or "—"
            table.add_row(
                _ts(entry.get("timestamp")),
                _color(prim, prim_color),
                _short(str(wf), 12),
                str(entry.get("tokens_after", "—")),
                str(entry.get("duration_ms", "—")),
            )

    @work(thread=True)
    def _poll_kv_status(self) -> None:
        status, connected = self._client.fetch_kv_status(self._kv_url)
        self.app.call_from_thread(self._update_kv_display, status, connected)

    def _update_kv_display(
        self, status: dict[str, Any] | None, connected: bool
    ) -> None:
        self._kv_connected = connected
        if status is not None:
            self._last_kv_status = status

        conn_label = self.query_one("#kv-conn-status", Label)
        if connected:
            conn_label.update("[green]● mlx-kv-server ONLINE[/green]")
        else:
            suffix = " [dim](showing last known)[/dim]" if self._last_kv_status else ""
            conn_label.update(f"[red]● mlx-kv-server OFFLINE[/red]{suffix}")

        bar_widget = self.query_one("#kv-bar", Static)
        stats_widget = self.query_one("#kv-stats", Static)

        if self._last_kv_status is None:
            bar_widget.update("[dim]No data — mlx-kv-server not reachable[/dim]")
            stats_widget.update("")
            return

        s = self._last_kv_status
        used = int(s.get("cache_used_tokens", 0))
        capacity = int(s.get("cache_capacity_tokens", 1))
        fill_frac = float(
            s.get("cache_used_fraction", used / capacity if capacity else 0.0)
        )
        ck_present = bool(s.get("checkpoint_present", False))
        ck_tokens = int(s.get("checkpoint_tokens", 0))

        ck_frac = (ck_tokens / capacity) if (ck_present and capacity > 0) else None
        bar_widget.update(render_cache_bar(fill_frac, ck_frac))

        pct = f"{fill_frac * 100:.1f}%"
        uptime = format_uptime(float(s.get("uptime_seconds", 0)))
        last_op = str(s.get("last_operation") or "—")
        ck_part = (
            f"  checkpoint @ {ck_tokens:,} tokens" if ck_present else "  no checkpoint"
        )
        stats_widget.update(
            f"Used: {used:,} / {capacity:,} ({pct}){ck_part}  "
            f"Last: {last_op}  Uptime: {uptime}"
        )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class KaiDevtoolsApp(App[None]):
    """kai-devtools observability panel (§13)."""

    TITLE = "kai-devtools"
    BINDINGS = [
        Binding("r", "refresh_all", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    DataTable {
        height: 1fr;
    }
    VersionedDocPanel > Horizontal {
        height: 1fr;
    }
    VersionedDocPanel > Horizontal > Vertical {
        width: 1fr;
        border: solid $panel-lighten-2;
        overflow-y: scroll;
    }
    #diff-pane {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        reader: DaemonStateReader,
        action_client: ActionClient,
        kv_server_url: str = "http://127.0.0.1:8080",
    ) -> None:
        super().__init__()
        self._reader = reader
        self._client = action_client
        self._kv_server_url = kv_server_url

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(
            "Workflows",
            "Scratch",
            "Holding",
            "DAEMON_SELF",
            "DAEMON_REL",
            "Distillation",
            "Threads",
            "Push",
            "Register",
            "Memory",
            "Inference",
            "Contradictions",
            "BORDERLINE",
        ):
            with TabPane("Workflows", id="tab-workflows"):
                yield WorkflowsPanel(self._reader, id="workflows-panel")
            with TabPane("Scratch", id="tab-scratch"):
                yield ScratchPanel(self._reader, id="scratch-panel")
            with TabPane("Holding", id="tab-holding"):
                yield HoldingPanel(self._reader, id="holding-panel")
            with TabPane("DAEMON_SELF", id="tab-self"):
                yield VersionedDocPanel(self._reader, "daemon_self", id="self-panel")
            with TabPane("DAEMON_REL", id="tab-rel"):
                yield VersionedDocPanel(
                    self._reader, "daemon_relational", id="rel-panel"
                )
            with TabPane("Distillation", id="tab-distillation"):
                yield DistillationPanel(self._reader, id="distillation-panel")
            with TabPane("Threads", id="tab-threads"):
                yield ThreadsPanel(self._reader, id="threads-panel")
            with TabPane("Push", id="tab-push"):
                yield PushHistoryPanel(self._reader, id="push-panel")
            with TabPane("Register", id="tab-register"):
                yield RegisterPanel(self._reader, id="register-panel")
            with TabPane("Memory", id="tab-memory"):
                yield MemoryPanel(self._reader, self._client, id="memory-panel")
            with TabPane("Inference", id="tab-inference"):
                yield InferencePanel(
                    self._reader,
                    self._client,
                    self._kv_server_url,
                    id="inference-panel",
                )
            with TabPane("Contradictions", id="tab-contradictions"):
                yield ContradictionsPanel(
                    self._reader, self._client, id="contradictions-panel"
                )
            with TabPane("BORDERLINE", id="tab-borderline"):
                yield BorderlinePanel(self._reader, self._client, id="borderline-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self._reader.data_dir)
        self.set_interval(10.0, self.action_refresh_all)

    def action_refresh_all(self) -> None:
        """Refresh data in all panels."""
        for panel in self.query(RefreshPanel):
            panel.refresh_data()
