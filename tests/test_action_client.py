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
        def do_POST(self) -> None:  # noqa: N802
            body, status = responses.get(
                self.path, ({"ok": False, "error": "not found"}, 404)
            )
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
# ActionResult is immutable (frozen dataclass)
# ---------------------------------------------------------------------------


def test_action_result_immutable() -> None:
    r = ActionResult(ok=True, id="abc", error=None, http_status=200)
    with pytest.raises((AttributeError, TypeError)):
        r.ok = False  # type: ignore[misc]
