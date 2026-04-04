"""Tests for DaemonStateReader and the no-direct-writes constraint (§CLAUDE.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from kai_devtools._reader import DaemonStateReader

# ---------------------------------------------------------------------------
# No-writes constraint (acceptance criterion)
# ---------------------------------------------------------------------------


def test_reader_never_writes_to_data_dir(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DaemonStateReader must never write to the data directory.

    This is the automated test required by the Stage 3 acceptance criteria:
    'No writes to daemon state from this tool (automated test asserts this).'
    """
    writes: list[str] = []
    original_write_text = Path.write_text

    def intercept_write_text(self: Path, *args: object, **kwargs: object) -> object:
        if str(self).startswith(str(data_dir)):
            writes.append(str(self))
        return original_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", intercept_write_text)

    reader = DaemonStateReader(data_dir)

    # Invoke every public read method — none should trigger a write.
    reader.workflow_runs()
    reader.scratch()
    reader.holding()
    reader.daemon_self()
    reader.daemon_self_history()
    reader.daemon_relational()
    reader.daemon_relational_history()
    reader.distillation_metrics()
    reader.threads()
    reader.push_history()
    reader.register_inference()
    reader.embedding_backfill_queue()
    reader.borderline_pool()
    reader.borderline_pending()
    reader.contradiction_candidates()
    reader.memory_server_config()
    reader.memory_server_url()

    assert writes == [], (
        f"DaemonStateReader wrote directly to data dir (violates constraint): {writes}"
    )


# ---------------------------------------------------------------------------
# Workflow runs
# ---------------------------------------------------------------------------


def test_workflow_runs_returns_list(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    runs = reader.workflow_runs()
    assert len(runs) == 1
    assert runs[0]["workflow_name"] == "distillation_health_check"
    assert runs[0]["status"] == "success"


def test_workflow_runs_empty_when_file_absent(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path)
    assert reader.workflow_runs() == []


# ---------------------------------------------------------------------------
# Scratch space
# ---------------------------------------------------------------------------


def test_scratch_returns_active_item(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    items = reader.scratch()
    assert len(items) == 1
    assert items[0]["type"] == "signal"
    assert items[0]["lifecycle"] == "active"
    assert items[0]["epistemic_origin"] == "internal"


def test_scratch_empty_when_absent(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path)
    assert reader.scratch() == []


# ---------------------------------------------------------------------------
# Holding store
# ---------------------------------------------------------------------------


def test_holding_returns_all_items(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    items = reader.holding()
    assert len(items) == 2
    types = {i["type"] for i in items}
    assert "observation" in types
    assert "reasoned_disagreement" in types


def test_contradiction_candidates_filters_correctly(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    candidates = reader.contradiction_candidates()
    assert len(candidates) == 1
    assert candidates[0]["contradiction_id"] == "cid-001"
    assert candidates[0]["surfaced"] is None


def test_contradiction_candidates_excludes_surfaced(data_dir: Path) -> None:
    state = data_dir / "daemon_state"
    items = yaml.safe_load((state / "holding.yaml").read_text())
    items[1]["surfaced"] = "2026-04-04T12:00:00+00:00"
    (state / "holding.yaml").write_text(yaml.dump(items))

    reader = DaemonStateReader(data_dir)
    assert reader.contradiction_candidates() == []


# ---------------------------------------------------------------------------
# DAEMON_SELF
# ---------------------------------------------------------------------------


def test_daemon_self_current(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    doc = reader.daemon_self()
    assert doc is not None
    assert doc["version"] == 3
    assert doc["who_daemon_is"] == "A curious entity."


def test_daemon_self_history_sorted(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    history = reader.daemon_self_history()
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2


def test_daemon_self_returns_none_when_absent(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path)
    assert reader.daemon_self() is None


# ---------------------------------------------------------------------------
# DAEMON_RELATIONAL
# ---------------------------------------------------------------------------


def test_daemon_relational_current(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    doc = reader.daemon_relational()
    assert doc is not None
    assert doc["version"] == 2
    assert "Analytically" in doc["how_user_thinks"]


def test_daemon_relational_history(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    history = reader.daemon_relational_history()
    assert len(history) == 1
    assert history[0]["version"] == 1


# ---------------------------------------------------------------------------
# Distillation metrics
# ---------------------------------------------------------------------------


def test_distillation_metrics_sorted_by_cycle(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    records = reader.distillation_metrics()
    assert len(records) == 2
    assert records[0]["cycle_number"] == 1
    assert records[1]["cycle_number"] == 2
    assert "convergence" in records[1]["notes"]


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


def test_threads_returns_all(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    threads = reader.threads()
    assert len(threads) == 1
    assert threads[0]["title"] == "The question of presence"
    assert threads[0]["status"] == "active"


def test_threads_empty_when_dir_absent(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path)
    assert reader.threads() == []


# ---------------------------------------------------------------------------
# Push history
# ---------------------------------------------------------------------------


def test_push_history(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    records = reader.push_history()
    assert len(records) == 1
    assert records[0]["content_summary"] == "Sent note about open loop."


# ---------------------------------------------------------------------------
# Register inference
# ---------------------------------------------------------------------------


def test_register_inference(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    entries = reader.register_inference()
    assert len(entries) == 1
    assert entries[0]["inferred_register"] == "casual"
    assert entries[0]["corrected_register"] == "reflective"


# ---------------------------------------------------------------------------
# Embedding backfill queue
# ---------------------------------------------------------------------------


def test_embedding_backfill_queue(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    queue = reader.embedding_backfill_queue()
    assert len(queue) == 1
    assert queue[0]["path"] == "queued_session.yaml"
    assert isinstance(queue[0]["age_days"], float)


def test_embedding_backfill_queue_empty_when_absent(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path)
    assert reader.embedding_backfill_queue() == []


def test_embedding_backfill_queue_excludes_dotfiles(tmp_path: Path) -> None:
    q = tmp_path / "daemon_state" / "memory_queue"
    q.mkdir(parents=True)
    (q / ".gitkeep").write_text("")
    (q / "real_item.yaml").write_text("type: session")
    reader = DaemonStateReader(tmp_path)
    queue = reader.embedding_backfill_queue()
    assert len(queue) == 1
    assert queue[0]["path"] == "real_item.yaml"


# ---------------------------------------------------------------------------
# BORDERLINE pool
# ---------------------------------------------------------------------------


def test_borderline_pool_all(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    items = reader.borderline_pool()
    assert len(items) == 2
    statuses = {i["status"] for i in items}
    assert "pending" in statuses
    assert "discarded" in statuses


def test_borderline_pending_filters(data_dir: Path) -> None:
    reader = DaemonStateReader(data_dir)
    pending = reader.borderline_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == "bl1"
    assert pending[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# Resilience: malformed files return empty results, not exceptions
# ---------------------------------------------------------------------------


def test_malformed_yaml_returns_empty(tmp_path: Path) -> None:
    state = tmp_path / "daemon_state"
    state.mkdir()
    (state / "holding.yaml").write_text("this: is: not: valid: yaml: [[[")
    reader = DaemonStateReader(tmp_path)
    assert reader.holding() == []


def test_malformed_jsonl_skips_bad_lines(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    good = json.dumps(
        {
            "workflow_name": "test",
            "trigger": "cron",
            "started_at": "2026-04-04T00:00:00+00:00",
            "completed_at": "2026-04-04T00:00:01+00:00",
            "status": "success",
            "memory_server_available": True,
            "metadata": {},
        }
    )
    (logs / "workflow_runs.jsonl").write_text(good + "\n{bad json\n")
    reader = DaemonStateReader(tmp_path)
    runs = reader.workflow_runs()
    assert len(runs) == 1


def test_nonexistent_data_dir_returns_empty(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path / "nonexistent")
    assert reader.workflow_runs() == []
    assert reader.scratch() == []
    assert reader.holding() == []
    assert reader.daemon_self() is None
    assert reader.daemon_self_history() == []
    assert reader.threads() == []
    assert reader.borderline_pool() == []


# ---------------------------------------------------------------------------
# Memory server config helper
# ---------------------------------------------------------------------------


def test_memory_server_url_default(tmp_path: Path) -> None:
    reader = DaemonStateReader(tmp_path / "data")
    # No daemon-memory-server.yaml present → use defaults
    url = reader.memory_server_url()
    assert url == "http://localhost:8765"


def test_memory_server_url_from_config(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    cfg = {"connection": {"host": "192.168.1.5", "port": 9000}}
    (tmp_path / "daemon-memory-server.yaml").write_text(yaml.dump(cfg))
    reader = DaemonStateReader(data)
    assert reader.memory_server_url() == "http://192.168.1.5:9000"
