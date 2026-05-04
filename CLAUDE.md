# CLAUDE.md — kai-devtools

## What this repo is

The observability panel for the daemon. Built during Stage 3 of the `kai-daemon`
build. Reads daemon state and log files to surface what the daemon is doing,
thinking, and deciding.

This is a development and debugging tool — not part of the daemon's runtime.
It never writes to daemon state. It only reads.

## Role in the system

Provides visibility into every layer of the daemon during development:
- Workflow execution history
- Daemon state (DAEMON_SELF, DAEMON_RELATIONAL, holding store, thread store)
- Memory server health
- Register inference log
- Distillation health metrics
- Contradiction candidate review

## What depends on this repo

Nothing. This is the end of the dependency graph.

## What this repo depends on

- `kai-daemon` internal state structures — the YAML schemas for DAEMON_SELF,
  DAEMON_RELATIONAL, holding store, threads, and the log format for
  `workflow_runs.jsonl`

During development, kai-daemon's state structures may still be changing.
Install editable from this devcontainer:

```bash
uv add --editable /workspaces/kai-daemon
```

Switch to a stable dependency once kai-daemon's state schemas are settled.

## Build, test, lint

```bash
uv sync
uv run pytest
uv run tox
uv run pyright
uv run ruff check .
```

## Architecture references

- `../kai-project/docs/kai-architecture.md` §13 — observability surfaces (canonical list)
- `../kai-project/docs/kai-architecture.md` §4a — DAEMON_SELF schema
- `../kai-project/docs/kai-architecture.md` §4b — DAEMON_RELATIONAL schema
- `../kai-project/docs/kai-architecture.md` §4d — holding store schema
- `../kai-project/docs/kai-architecture.md` §4f — thread store schema
- `../kai-project/docs/kai-technical.md` Stage 3 and Stage 3.5 acceptance criteria
- `../kai-project/docs/adr-001-mlx-kv-server-status-endpoint.md` — Inference panel decision rationale
- `../kai-project/docs/kai-tools.md` — tool catalogue, permission matrix, Kai SDK spec

## Required observability surfaces

These are the surfaces that must be present for Stage 3 to be considered
complete. Every item is required — this is not a prioritised list.

| Surface                           | What it shows                                              |
|-----------------------------------|------------------------------------------------------------|
| Workflow run history              | `data/logs/workflow_runs.jsonl` — all runs, filterable     |
| Scratch space viewer              | Current scratch items, type, TTL, epistemic origin         |
| Holding store viewer              | All held items, relevance trigger, register needed, urgency|
| DAEMON_SELF viewer + version diff | Current version and diff against any prior version         |
| DAEMON_RELATIONAL viewer + diff   | Current version and diff against any prior version         |
| Distillation metrics              | Health signals — convergence, flattery drift, oscillation  |
| Session thread stack              | Current stack state (foreground, peripheral, floating)     |
| Push history                      | Out-of-session push log with timestamps                    |
| Register inference log            | Per-turn inference and corrections                         |
| Memory server availability        | Live status indicator                                      |
| Embedding backfill queue          | Items pending embedding, count and age                     |
| Contradiction candidate review    | Candidates pending human review, with resolution interface |
| BORDERLINE pool review            | Inner life outputs awaiting promote/discard decision; auto-expire after 30 days |
| Inference panel                   | KV cache bar (fill, capacity, checkpoint marker) + `inference_calls.jsonl` operation log; polls GET /status/kv on kai-daemon proxy (not mlx-kv-server directly); added in Stage 3.5 |

## Critical constraints

**Read-only with respect to daemon state files.** This tool never directly
writes to `data/` or any daemon YAML. Actions that appear to be writes (e.g.
contradiction resolution, BORDERLINE promote/discard) are implemented as HTTP
POST requests to `kai-daemon`'s local API, which performs the write. The tool
is a UI — the daemon owns the state.

**No inference.** kai-devtools never calls any model. No mlx-kv-client
dependency. No OpenRouter dependency.

**File paths are relative to the kai-daemon data directory.** The path to
`data/` is configured at startup, not hardcoded. The tool reads from wherever
`kai-daemon` is running.

## Stage 3 acceptance criteria

- [ ] All observability surfaces listed above (excluding Inference panel) are present and functional
- [ ] BORDERLINE pool: promote and discard actions work; auto-expiry confirmed at 30 days
- [ ] Version diffs for DAEMON_SELF and DAEMON_RELATIONAL are correct
- [ ] Contradiction candidate review interface is functional
- [ ] No writes to daemon state from this tool (automated test asserts this)

## Stage 3.5 acceptance criteria

- [ ] Inference panel present between Memory and Contradictions tabs
- [ ] Cache bar renders with correct fill level, capacity, and checkpoint marker
- [ ] Colour transitions: green < 75%, amber 75–90%, red > 90%
- [ ] Polls `GET /status/kv` on kai-daemon proxy at <= 5s interval (kai-devtools never connects to mlx-kv-server directly)
- [ ] Degrades gracefully if mlx-kv-server is unreachable (shows last known state or disconnected indicator)
- [ ] Operation log reads from `data/logs/inference_calls.jsonl` and is filterable by primitive type

## GitHub issue hygiene

```bash
gh issue close <number> --repo distilledecho/kai-devtools
bash ../kai-project/setup/project-move.sh <issue-url> "Done"
```

## Review

Run in a **fresh Claude Code session** when Stage 3 is complete:

```
/review stage=3
```
