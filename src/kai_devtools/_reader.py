"""Read-only reader for all daemon-local observability surfaces (§4a–4i, §13).

Every public method reads files from the configured data directory and returns
plain Python dicts/lists.  No method ever opens a file for writing.  This is
enforced by the automated test in ``tests/test_no_writes.py``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class DaemonStateReader:
    """Read-only view over ``data/`` from a running or past kai-daemon instance.

    Parameters
    ----------
    data_dir:
        Path to the daemon's ``data/`` directory.  Configured at startup; never
        hardcoded.  All sub-paths are derived from this root.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data = data_dir

    # ------------------------------------------------------------------
    # Internal paths (never used for writes)
    # ------------------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        """Path to the daemon's ``data/`` directory."""
        return self._data

    @property
    def _state_dir(self) -> Path:
        return self._data / "daemon_state"

    @property
    def _logs_dir(self) -> Path:
        return self._data / "logs"

    # ------------------------------------------------------------------
    # 1. Workflow run history — data/logs/workflow_runs.jsonl
    # ------------------------------------------------------------------

    def workflow_runs(self) -> list[dict[str, Any]]:
        """Return all workflow run entries, oldest first."""
        return self._read_jsonl(self._logs_dir / "workflow_runs.jsonl")

    # ------------------------------------------------------------------
    # 2. Scratch space — data/daemon_state/scratch.yaml
    # ------------------------------------------------------------------

    def scratch(self) -> list[dict[str, Any]]:
        """Return all scratch notes (active and archived)."""
        return self._read_yaml_list(self._state_dir / "scratch.yaml")

    # ------------------------------------------------------------------
    # 3. Holding store — data/daemon_state/holding.yaml
    # ------------------------------------------------------------------

    def holding(self) -> list[dict[str, Any]]:
        """Return all holding store items."""
        return self._read_yaml_list(self._state_dir / "holding.yaml")

    # ------------------------------------------------------------------
    # 4. DAEMON_SELF — current + version history
    # ------------------------------------------------------------------

    def daemon_self(self) -> dict[str, Any] | None:
        """Return the current DAEMON_SELF document, or None if not written yet."""
        return self._read_yaml(self._state_dir / "daemon_self.yaml")

    def daemon_self_history(self) -> list[dict[str, Any]]:
        """Return all archived DAEMON_SELF versions in ascending version order."""
        return self._read_versioned_history(self._state_dir / "daemon_self_history")

    # ------------------------------------------------------------------
    # 5. DAEMON_RELATIONAL — current + version history
    # ------------------------------------------------------------------

    def daemon_relational(self) -> dict[str, Any] | None:
        """Return the current DAEMON_RELATIONAL document, or None if absent."""
        return self._read_yaml(self._state_dir / "daemon_relational.yaml")

    def daemon_relational_history(self) -> list[dict[str, Any]]:
        """Return all archived DAEMON_RELATIONAL versions in ascending order."""
        return self._read_versioned_history(
            self._state_dir / "daemon_relational_history"
        )

    # ------------------------------------------------------------------
    # 6. Distillation metrics — data/daemon_state/distillation_metrics.yaml
    # ------------------------------------------------------------------

    def distillation_metrics(self) -> list[dict[str, Any]]:
        """Return all distillation cycle records in ascending cycle order."""
        records = self._read_yaml_list(self._state_dir / "distillation_metrics.yaml")
        return sorted(records, key=lambda r: r.get("cycle_number", 0))

    # ------------------------------------------------------------------
    # 7. Session thread stack — data/daemon_state/threads/*.yaml
    # ------------------------------------------------------------------

    def threads(self) -> list[dict[str, Any]]:
        """Return all threads sorted by last_touched descending."""
        threads_dir = self._state_dir / "threads"
        if not threads_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for path in sorted(threads_dir.glob("*.yaml")):
            doc = self._read_yaml(path)
            if doc:
                result.append(doc)
        return sorted(result, key=lambda t: t.get("last_touched", ""), reverse=True)

    # ------------------------------------------------------------------
    # 8. Push history — data/daemon_state/push_history.yaml
    # ------------------------------------------------------------------

    def push_history(self) -> list[dict[str, Any]]:
        """Return all push records in append order (oldest first)."""
        return self._read_yaml_list(self._state_dir / "push_history.yaml")

    # ------------------------------------------------------------------
    # 9. Register inference log — data/logs/register_inference.jsonl
    # ------------------------------------------------------------------

    def register_inference(self) -> list[dict[str, Any]]:
        """Return all register correction entries, oldest first."""
        return self._read_jsonl(self._logs_dir / "register_inference.jsonl")

    # ------------------------------------------------------------------
    # 10. Embedding backfill queue — data/daemon_state/memory_queue/
    # ------------------------------------------------------------------

    def embedding_backfill_queue(self) -> list[dict[str, Any]]:
        """Return one entry per file in memory_queue/, with path and age_days."""
        queue_dir = self._state_dir / "memory_queue"
        if not queue_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for path in sorted(queue_dir.iterdir()):
            if path.name.startswith("."):
                continue
            stat = path.stat()
            result.append(
                {
                    "path": path.name,
                    "size_bytes": stat.st_size if path.is_file() else 0,
                    "age_days": round(
                        (datetime.now(UTC).timestamp() - stat.st_mtime) / 86400,
                        2,
                    ),
                }
            )
        return sorted(result, key=lambda e: e["age_days"], reverse=True)

    # ------------------------------------------------------------------
    # 11. Contradiction candidates — holding items with contradiction_id set
    # ------------------------------------------------------------------

    def contradiction_candidates(self) -> list[dict[str, Any]]:
        """Return unsurfaced holding items that have a contradiction_id."""
        return [
            item
            for item in self.holding()
            if item.get("contradiction_id") is not None and item.get("surfaced") is None
        ]

    # ------------------------------------------------------------------
    # 12. BORDERLINE pool — data/daemon_state/borderline_pool.yaml
    # ------------------------------------------------------------------

    def borderline_pool(self) -> list[dict[str, Any]]:
        """Return all BORDERLINE pool items."""
        items = self._read_yaml_list(self._state_dir / "borderline_pool.yaml")
        return sorted(items, key=lambda i: i.get("created", ""), reverse=True)

    def borderline_pending(self) -> list[dict[str, Any]]:
        """Return BORDERLINE items with status 'pending'."""
        return [i for i in self.borderline_pool() if i.get("status") == "pending"]

    # ------------------------------------------------------------------
    # Config helper — read daemon-memory-server.yaml for server URL
    # ------------------------------------------------------------------

    def memory_server_config(self) -> dict[str, Any]:
        """Read connection config from daemon-memory-server.yaml next to data/.

        Returns an empty dict if the file does not exist or cannot be parsed.
        """
        cfg_path = self._data.parent / "daemon-memory-server.yaml"
        if not cfg_path.exists():
            return {}
        try:
            raw = yaml.safe_load(cfg_path.read_text())
            return raw if isinstance(raw, dict) else {}
        except yaml.YAMLError:
            logger.warning("Could not parse daemon-memory-server.yaml")
            return {}

    def memory_server_url(self) -> str:
        """Return the base URL for the daemon-memory-server from config."""
        cfg = self.memory_server_config()
        conn = cfg.get("connection", {})
        host = conn.get("host", "localhost")
        port = conn.get("port", 8765)
        return f"http://{host}:{port}"

    # ------------------------------------------------------------------
    # Internal helpers — all read-only
    # ------------------------------------------------------------------

    def _read_yaml(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
        except (yaml.YAMLError, OSError):
            logger.warning("Could not read YAML from %s", path)
            return None

    def _read_yaml_list(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [item for item in raw if isinstance(item, dict)]
        except (yaml.YAMLError, OSError):
            logger.warning("Could not read YAML list from %s", path)
            return []

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        result: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        result.append(parsed)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSONL line in %s", path)
        except OSError:
            logger.warning("Could not read JSONL from %s", path)
        return result

    def _read_versioned_history(self, history_dir: Path) -> list[dict[str, Any]]:
        if not history_dir.exists():
            return []
        versions: list[dict[str, Any]] = []
        for path in history_dir.glob("v*.yaml"):
            doc = self._read_yaml(path)
            if doc:
                versions.append(doc)
        return sorted(versions, key=lambda d: d.get("version", 0))
