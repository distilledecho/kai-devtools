[![CI](https://github.com/distilledecho/kai-devtools/actions/workflows/ci.yml/badge.svg)](https://github.com/distilledecho/kai-devtools/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/distilledecho/kai-devtools/branch/main/graph/badge.svg)](https://codecov.io/gh/distilledecho/kai-devtools)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

# kai-devtools

Observability panel for kai-daemon — a terminal UI for inspecting every layer of the daemon's state during development.

## The system

Kai is a local AI system with persistent memory, a background workflow engine, and a structured inner life. It runs across two machines on the same local network:

- **Inference server** — runs `mlx-kv-server` natively on Apple Silicon. Handles all inference: conversation, inner life generation, ingestion workflows, embedding generation. Runs `kai-daemon`.
- **Memory server** — runs `daemon-memory-server`. Stores, indexes, and serves all persistent memory. Never initiates inference.

**Six components:**

| Component | Role |
|---|---|
| `mlx-kv-server` | Inference server (five primitives) |
| `mlx-kv-client` | Thin HTTP client for mlx-kv-server |
| `daemon-memory-server` | Memory server — episodic, artifact, and semantic APIs |
| `daemon-memory-client` | Thin HTTP client for daemon-memory-server |
| `kai-daemon` | The daemon itself |
| `kai-devtools` | This tool — observability panel |

## What kai-devtools shows

kai-devtools is a read-only terminal UI. It never writes directly to daemon state — actions that appear to be writes (contradiction resolution, BORDERLINE promote/discard) are sent as HTTP requests to the daemon's local action API, which performs the write.

Surfaces:

- Workflow run history (`data/logs/workflow_runs.jsonl`) — all runs, filterable
- Scratch space — current items, type, TTL, epistemic origin
- Holding store — held items with relevance trigger, register needed, urgency
- DAEMON_SELF viewer + version diff against any prior version
- DAEMON_RELATIONAL viewer + version diff against any prior version
- Distillation metrics — convergence, flattery drift, oscillation
- Session thread stack — foreground, peripheral, and floating threads
- Push history — out-of-session push log with timestamps
- Register inference log — per-turn inference and corrections
- Memory server availability — live status indicator
- Embedding backfill queue — items pending embedding, count and age
- Contradiction candidate review — candidates pending human review
- BORDERLINE pool review — inner life outputs awaiting promote/discard; auto-expire after 30 days

Source          | <https://github.com/distilledecho/kai-devtools>
:---:           | :---:
Documentation   | <https://distilledecho.github.io/kai-devtools>
Releases        | <https://github.com/distilledecho/kai-devtools/releases>

## Quick start

The four services must be started in order. Steps 1–3 start the system kai-devtools observes; step 4 starts kai-devtools itself.

### 1. Start mlx-kv-server (inference server)

Must run natively on Apple Silicon — not in a devcontainer.

```
uv run python -m mlx_kv_server
```

The port is configurable in `config.toml`.

### 2. Start daemon-memory-server (memory server)

```
uv run python -m daemon_memory_server --host localhost --port 8765
```

The port must match `connection.port` in `kai-daemon/daemon-memory-server.yaml`.

### 3. Start kai-daemon (inference server)

```
uv run python -m kai_daemon
```

Connection settings are configurable in `daemon-memory-server.yaml`.

### 4. Start kai-devtools

```
uv run python -m kai_devtools --data-dir /path/to/kai-daemon/data
```

| Option | Default | Description |
|---|---|---|
| `--data-dir` | `./data` | Path to the daemon's `data/` directory |
| `--api-host` | `127.0.0.1` | Host for the daemon action API |
| `--api-port` | `9271` | Port for the daemon action API |

<!-- README only content. Anything below this line won't be included in index.md -->

See https://distilledecho.github.io/kai-devtools for more detailed documentation.
