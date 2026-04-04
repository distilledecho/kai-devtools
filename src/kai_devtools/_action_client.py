"""HTTP client for the daemon's localhost action API (§13).

All write operations (contradiction resolution, BORDERLINE promote/discard) are
routed through this client as HTTP POST requests to kai-daemon's action API.
kai-devtools never writes directly to daemon state files.

Default base URL: ``http://127.0.0.1:9271`` (daemon's ``DEFAULT_PORT``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "http://127.0.0.1:9271"
_MEMORY_SERVER_PROBE_PATH = "/episodic/sessions/recent?n=1"


@dataclass(frozen=True)
class ActionResult:
    """Result of a daemon action API call."""

    ok: bool
    id: str | None
    error: str | None
    http_status: int


class ActionClient:
    """POST-only HTTP client for the daemon action API (§13).

    Parameters
    ----------
    base_url:
        Base URL for the action API.  Defaults to ``http://127.0.0.1:9271``.
    timeout:
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Contradiction actions
    # ------------------------------------------------------------------

    def contradiction_resolve(self, contradiction_id: str) -> ActionResult:
        """POST /actions/contradiction/{id}/resolve."""
        return self._post(f"/actions/contradiction/{contradiction_id}/resolve")

    def contradiction_dismiss(self, contradiction_id: str) -> ActionResult:
        """POST /actions/contradiction/{id}/dismiss."""
        return self._post(f"/actions/contradiction/{contradiction_id}/dismiss")

    # ------------------------------------------------------------------
    # BORDERLINE actions
    # ------------------------------------------------------------------

    def borderline_promote(self, item_id: str) -> ActionResult:
        """POST /actions/borderline/{id}/promote."""
        return self._post(f"/actions/borderline/{item_id}/promote")

    def borderline_discard(self, item_id: str) -> ActionResult:
        """POST /actions/borderline/{id}/discard."""
        return self._post(f"/actions/borderline/{item_id}/discard")

    # ------------------------------------------------------------------
    # Memory server availability check (read-only probe)
    # ------------------------------------------------------------------

    def check_memory_server(self, memory_server_url: str) -> bool:
        """Return True if the daemon-memory-server responds to a probe request."""
        url = memory_server_url.rstrip("/") + _MEMORY_SERVER_PROBE_PATH
        try:
            resp = httpx.get(url, timeout=3.0)
            return resp.status_code < 500
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post(self, path: str) -> ActionResult:
        url = self._base + path
        try:
            resp = httpx.post(url, timeout=self._timeout)
            body: dict[str, Any] = resp.json()
            return ActionResult(
                ok=bool(body.get("ok", False)),
                id=body.get("id"),
                error=body.get("error"),
                http_status=resp.status_code,
            )
        except httpx.TimeoutException:
            logger.warning("action-api: timeout posting to %s", url)
            return ActionResult(ok=False, id=None, error="timeout", http_status=0)
        except httpx.HTTPError as exc:
            logger.warning("action-api: HTTP error posting to %s: %s", url, exc)
            return ActionResult(ok=False, id=None, error=str(exc), http_status=0)
        except Exception as exc:
            logger.warning("action-api: unexpected error posting to %s: %s", url, exc)
            return ActionResult(ok=False, id=None, error=str(exc), http_status=0)
