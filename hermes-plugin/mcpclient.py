"""MCP Streamable HTTP client and Docker helpers for ClawSight.

Extracted verbatim from the original tools.py so the engine-agnostic rewrite
reuses the transport that was already proven against the WSInsight containers.

Implements an MCP 2025-03-26 Streamable HTTP client:

  POST {mcp_url}
    Content-Type: application/json
    Accept: application/json, text/event-stream
    Mcp-Session-Id: {sid}   (after initialization)

  The response may be JSON or SSE; the last ``data: {...}`` line of an SSE
  stream carries the JSON-RPC result.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:  # pragma: no cover - httpx is a hard runtime dep
    _HAS_HTTPX = False

logger = logging.getLogger(__name__)


__all__ = ["McpHttpClient", "_parse_arguments", "_docker", "_HAS_HTTPX"]


# ---------------------------------------------------------------------------
# MCP Streamable HTTP client
# ---------------------------------------------------------------------------

class McpHttpClient:
    """Async MCP 2025-03-26 Streamable HTTP client.

    Maintains a single session (Mcp-Session-Id) across calls.
    One instance is kept alive in _State for the plugin lifetime.
    """

    def __init__(self, url: str, timeout_s: float = 300.0) -> None:
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self._session_id: str | None = None
        self._msg_id: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _req_headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _notification_headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _extract_session(self, resp: httpx.Response) -> None:
        sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid

    @staticmethod
    def _parse_sse(text: str) -> dict | None:
        """Return the last JSON object from an SSE stream body."""
        last: dict | None = None
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    last = json.loads(line[6:])
                except Exception:
                    pass
        return last

    # ------------------------------------------------------------------
    # Low-level POST
    # ------------------------------------------------------------------

    async def _post(self, payload: dict) -> dict | None:
        """POST a JSON-RPC message and return the parsed response dict."""
        if not _HAS_HTTPX:
            raise RuntimeError(
                "httpx is required. Install with: pip install httpx"
            )
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            async with client.stream(
                "POST",
                self.url,
                json=payload,
                headers=self._req_headers(),
            ) as resp:
                self._extract_session(resp)
                if resp.status_code in (202, 204):
                    return None
                resp.raise_for_status()
                body = await resp.aread()
                text = body.decode("utf-8", errors="replace")
                ct = resp.headers.get("content-type", "")
                if "text/event-stream" in ct:
                    return self._parse_sse(text)
                return json.loads(text) if text.strip() else None

    async def _notify(self, payload: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not _HAS_HTTPX:
            return
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.url,
                    json=payload,
                    headers=self._notification_headers(),
                )
                self._extract_session(resp)
        except Exception:
            pass  # notifications are fire-and-forget

    # ------------------------------------------------------------------
    # MCP protocol
    # ------------------------------------------------------------------

    async def initialize(self) -> dict:
        """Perform the MCP initialize handshake. Returns the init result."""
        data = await self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "clawsight", "version": "1.0.0"},
            },
        })
        # Notify server that we are initialized (no id = notification)
        await self._notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return data or {}

    async def _ensure(self) -> None:
        if not self._session_id:
            await self.initialize()

    async def list_tools(self) -> list[dict]:
        await self._ensure()
        data = await self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
        })
        if not data:
            return []
        return data.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> str:
        await self._ensure()
        data = await self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if data is None:
            return "[No response from MCP server]"
        if "error" in data:
            e = data["error"]
            return f"[MCP Error {e.get('code', '')}: {e.get('message', '')}]"
        content = data.get("result", {}).get("content", [])
        texts = [
            c["text"]
            for c in content
            if isinstance(c, dict) and c.get("type") == "text" and "text" in c
        ]
        return "\n".join(texts) if texts else "[Empty response]"

    def reset(self) -> None:
        """Drop the current session so the next call triggers re-initialization."""
        self._session_id = None
        self._msg_id = 0


def _parse_arguments(params: dict) -> dict | str:
    """Extract and validate the 'arguments' sub-object from tool params."""
    raw = params.get("arguments")
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return "[ERROR] 'arguments' must be a JSON object, not a plain string"
    if not isinstance(raw, dict):
        return "[ERROR] 'arguments' must be a JSON object"
    return raw


def _docker(*args: str, timeout: int = 60) -> tuple[int, str]:
    """Run a docker sub-command; return (returncode, combined output)."""
    try:
        r = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or "").strip() or (r.stderr or "").strip()
        return r.returncode, out
    except FileNotFoundError:
        return -1, "[ERROR] 'docker' executable not found in PATH"
    except subprocess.TimeoutExpired:
        return -1, f"[ERROR] docker command timed out after {timeout}s"
    except Exception as exc:
        return -1, f"[ERROR] {exc}"
