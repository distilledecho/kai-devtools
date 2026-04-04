"""Shared test fixtures for kai-devtools tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Minimal populated data/ directory that all readers can operate on."""
    state = tmp_path / "daemon_state"
    logs = tmp_path / "logs"
    for d in (
        state,
        logs,
        state / "daemon_self_history",
        state / "daemon_relational_history",
        state / "threads",
        state / "pickup_notes",
        state / "memory_queue",
    ):
        d.mkdir(parents=True, exist_ok=True)

    # workflow_runs.jsonl
    run = {
        "workflow_name": "distillation_health_check",
        "trigger": "cron",
        "started_at": "2026-04-04T02:00:00+00:00",
        "completed_at": "2026-04-04T02:00:05+00:00",
        "status": "success",
        "memory_server_available": True,
        "metadata": {},
    }
    (logs / "workflow_runs.jsonl").write_text(json.dumps(run) + "\n")

    # register_inference.jsonl
    reg = {
        "corrected_at": "2026-04-04T10:00:00+00:00",
        "thread_id": "aaaa-bbbb",
        "inferred_register": "casual",
        "corrected_register": "reflective",
        "metadata": {},
    }
    (logs / "register_inference.jsonl").write_text(json.dumps(reg) + "\n")

    # scratch.yaml
    scratch_items = [
        {
            "id": "s1",
            "workflow_id": "wf1",
            "session_id": "sess1",
            "timestamp": "2026-04-04T09:00:00+00:00",
            "content": "scratch content",
            "type": "signal",
            "lifecycle": "active",
            "epistemic_origin": "internal",
            "thread_ids": [],
            "acknowledged_by": [],
        }
    ]
    (state / "scratch.yaml").write_text(yaml.dump(scratch_items))

    # holding.yaml
    holding_items = [
        {
            "id": "h1",
            "content": "held observation",
            "type": "observation",
            "relevance_trigger": "when user mentions X",
            "register_needed": "exploratory",
            "urgency": "medium",
            "created": "2026-04-01T00:00:00+00:00",
            "surfaced": None,
            "discharge_notes": None,
            "source_workflow": "daemon_integration",
            "epistemic_origin": "internal",
            "thread_ids": [],
            "contradiction_id": None,
        },
        {
            "id": "h2",
            "content": "possible contradiction",
            "type": "reasoned_disagreement",
            "relevance_trigger": "when user mentions Y",
            "register_needed": "any",
            "urgency": "high",
            "created": "2026-04-02T00:00:00+00:00",
            "surfaced": None,
            "discharge_notes": None,
            "source_workflow": "contradiction_detection",
            "epistemic_origin": "internal",
            "thread_ids": [],
            "contradiction_id": "cid-001",
        },
    ]
    (state / "holding.yaml").write_text(yaml.dump(holding_items))

    # daemon_self.yaml
    ds = {
        "version": 3,
        "timestamp": "2026-04-04T06:00:00+00:00",
        "who_daemon_is": "A curious entity.",
        "current_fascinations": [],
        "aesthetic_sensibilities": "Clean prose.",
        "open_questions": [],
        "daemon_on_daemon": "Still becoming.",
        "overflow": "",
        "distillation_notes": "",
    }
    (state / "daemon_self.yaml").write_text(yaml.dump(ds))

    ds_v1 = {**ds, "version": 1, "who_daemon_is": "Version 1 self."}
    ds_v2 = {**ds, "version": 2, "who_daemon_is": "Version 2 self."}
    (state / "daemon_self_history" / "v1.yaml").write_text(yaml.dump(ds_v1))
    (state / "daemon_self_history" / "v2.yaml").write_text(yaml.dump(ds_v2))

    # daemon_relational.yaml
    dr = {
        "version": 2,
        "timestamp": "2026-04-04T06:00:00+00:00",
        "how_user_thinks": "Analytically.",
        "what_user_is_working_on": "The kai project.",
        "users_current_register": "exploratory",
        "where_daemon_reads_user_wrong": "Sometimes misses humour.",
        "open_loops": [],
        "overflow": "",
    }
    (state / "daemon_relational.yaml").write_text(yaml.dump(dr))

    dr_v1 = {**dr, "version": 1, "how_user_thinks": "Version 1 relational."}
    (state / "daemon_relational_history" / "v1.yaml").write_text(yaml.dump(dr_v1))

    # distillation_metrics.yaml
    metrics = [
        {
            "cycle_number": 1,
            "timestamp": "2026-04-01T03:00:00+00:00",
            "daemon_self_version": 1,
            "content_snapshot": "snapshot1",
            "notes": "",
        },
        {
            "cycle_number": 2,
            "timestamp": "2026-04-03T03:00:00+00:00",
            "daemon_self_version": 2,
            "content_snapshot": "snapshot2",
            "notes": "convergence detected",
        },
    ]
    (state / "distillation_metrics.yaml").write_text(yaml.dump(metrics))

    # threads/
    thread = {
        "id": "t1",
        "title": "The question of presence",
        "central_question": "What does it mean to be present?",
        "status": "active",
        "created": "2026-03-01T00:00:00+00:00",
        "last_touched": "2026-04-04T08:00:00+00:00",
        "dormant_since": None,
        "current_state": "Ongoing.",
        "unresolved": "Definition of presence.",
        "key_tension": None,
        "stance": {
            "position": "Presence is participatory.",
            "epistemic_status": "live",
        },
        "daemon_is_watching": None,
        "daemon_perspectives": [],
        "handoff_notes": [],
    }
    (state / "threads" / "t1.yaml").write_text(yaml.dump(thread))

    # push_history.yaml
    push_records = [
        {
            "id": "p1",
            "timestamp": "2026-03-28T10:00:00+00:00",
            "content_summary": "Sent note about open loop.",
        }
    ]
    (state / "push_history.yaml").write_text(yaml.dump(push_records))

    # borderline_pool.yaml
    bl_items = [
        {
            "id": "bl1",
            "raw_output": "Something borderline the daemon thought.",
            "created": "2026-04-03T10:00:00+00:00",
            "status": "pending",
            "promoted_at": None,
            "discarded_at": None,
        },
        {
            "id": "bl2",
            "raw_output": "Another borderline thought.",
            "created": "2026-03-01T10:00:00+00:00",
            "status": "discarded",
            "promoted_at": None,
            "discarded_at": "2026-03-15T10:00:00+00:00",
        },
    ]
    (state / "borderline_pool.yaml").write_text(yaml.dump(bl_items))

    # memory_queue: one queued item
    (state / "memory_queue" / "queued_session.yaml").write_text(
        yaml.dump({"type": "session_record", "session_id": "s1"})
    )

    return tmp_path
