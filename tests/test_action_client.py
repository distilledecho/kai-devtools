"""Tests for ActionClient — HTTP POST client for the daemon action API (§13)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from kai_devtools._action_client import ActionClient, ActionResult

# Response map type: path → (body, status_code)
_Responses = dict[str, tuple[dict[str, object], int]]


@contextmanager
def stub_server(responses: _Responses) -> Iterator[str]:
    """Context manager that runs a stub HTTP server for the duration of the block.

    Returns the base URL of the server.  Properly closes the server socket on
    exit so no ResourceWarning is raised under ``filterwarnings = "error"``.
    """

    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, path: str) -> None:
            body, status = responses.get(
                path, ({"ok": False, "error": "not found"}, 404)
            )
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            self._respond(self.path)

        def do_GET(self) -> None:  # noqa: N802
            self._respond(self.path)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # suppress output during tests

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    base_url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()  # stops serve_forever loop
        server.server_close()  # closes the listening socket


# ---------------------------------------------------------------------------
# Contradiction actions
# ---------------------------------------------------------------------------


def test_contradiction_resolve_success() -> None:
    path = "/actions/contradiction/cid-001/resolve"
    with stub_server({path: ({"ok": True, "id": "cid-001"}, 200)}) as base_url:
        result = ActionClient(base_url=base_url).contradiction_resolve("cid-001")
    assert result.ok is True
    assert result.id == "cid-001"
    assert result.http_status == 200


def test_contradiction_dismiss_success() -> None:
    path = "/actions/contradiction/cid-002/dismiss"
    with stub_server({path: ({"ok": True, "id": "cid-002"}, 200)}) as base_url:
        result = ActionClient(base_url=base_url).contradiction_dismiss("cid-002")
    assert result.ok is True
    assert result.id == "cid-002"


def test_contradiction_not_found() -> None:
    path = "/actions/contradiction/unknown/resolve"
    with stub_server(
        {path: ({"ok": False, "error": "contradiction 'unknown' not found"}, 404)}
    ) as base_url:
        result = ActionClient(base_url=base_url).contradiction_resolve("unknown")
    assert result.ok is False
    assert result.http_status == 404
    assert "unknown" in (result.error or "")


def test_contradiction_already_discharged() -> None:
    path = "/actions/contradiction/cid-003/resolve"
    with stub_server(
        {path: ({"ok": False, "error": "already discharged"}, 409)}
    ) as base_url:
        result = ActionClient(base_url=base_url).contradiction_resolve("cid-003")
    assert result.ok is False
    assert result.http_status == 409


# ---------------------------------------------------------------------------
# BORDERLINE actions
# ---------------------------------------------------------------------------


def test_borderline_promote_success() -> None:
    path = "/actions/borderline/bl-001/promote"
    with stub_server({path: ({"ok": True, "id": "bl-001"}, 200)}) as base_url:
        result = ActionClient(base_url=base_url).borderline_promote("bl-001")
    assert result.ok is True
    assert result.id == "bl-001"


def test_borderline_discard_success() -> None:
    path = "/actions/borderline/bl-002/discard"
    with stub_server({path: ({"ok": True, "id": "bl-002"}, 200)}) as base_url:
        result = ActionClient(base_url=base_url).borderline_discard("bl-002")
    assert result.ok is True
    assert result.id == "bl-002"


def test_borderline_not_found() -> None:
    path = "/actions/borderline/missing/promote"
    with stub_server(
        {path: ({"ok": False, "error": "BORDERLINE item 'missing' not found"}, 404)}
    ) as base_url:
        result = ActionClient(base_url=base_url).borderline_promote("missing")
    assert result.ok is False
    assert result.http_status == 404


def test_borderline_already_decided() -> None:
    path = "/actions/borderline/bl-003/discard"
    with stub_server(
        {path: ({"ok": False, "error": "already discarded"}, 409)}
    ) as base_url:
        result = ActionClient(base_url=base_url).borderline_discard("bl-003")
    assert result.ok is False
    assert result.http_status == 409


# ---------------------------------------------------------------------------
# Connection failures (daemon not running)
# ---------------------------------------------------------------------------


def test_connection_refused_returns_error_result() -> None:
    # Port 1 is reserved; connection will be refused immediately.
    client = ActionClient(base_url="http://127.0.0.1:1", timeout=1.0)
    result = client.contradiction_resolve("anything")
    assert result.ok is False
    assert result.http_status == 0
    assert result.error is not None


# ---------------------------------------------------------------------------
# fetch_kv_status
# ---------------------------------------------------------------------------

_KV_STATUS: dict[str, object] = {
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


def test_fetch_kv_status_success() -> None:
    with stub_server({"/status/kv": (_KV_STATUS, 200)}) as base_url:
        status, connected = ActionClient(base_url=base_url).fetch_kv_status()
    assert connected is True
    assert status is not None
    assert status["cache_used_tokens"] == 1842
    assert status["checkpoint_present"] is True


def test_fetch_kv_status_server_error() -> None:
    with stub_server({"/status/kv": ({"error": "internal"}, 500)}) as base_url:
        status, connected = ActionClient(base_url=base_url).fetch_kv_status()
    assert connected is False
    assert status is None


def test_fetch_kv_status_unreachable() -> None:
    client = ActionClient(base_url="http://127.0.0.1:1", timeout=1.0)
    status, connected = client.fetch_kv_status()
    assert connected is False
    assert status is None


# ---------------------------------------------------------------------------
# ActionResult is immutable (frozen dataclass)
# ---------------------------------------------------------------------------


def test_action_result_immutable() -> None:
    r = ActionResult(ok=True, id="abc", error=None, http_status=200)
    with pytest.raises((AttributeError, TypeError)):
        r.ok = False  # type: ignore[misc]
