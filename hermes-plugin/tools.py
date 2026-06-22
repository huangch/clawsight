"""ClawSight tool handlers for Hermes Agent.

Implements an MCP 2025-03-26 Streamable HTTP client that proxies tool calls
to a WSInsight MCP server running inside a Docker container.

Communication flow:
  POST {mcp_url}
    Content-Type: application/json
    Accept: application/json, text/event-stream
    Mcp-Session-Id: {sid}   (after initialization)

  Response may be JSON or SSE (text/event-stream). The last "data: {...}"
  line in an SSE stream is the JSON-RPC result.

Configuration via environment variables:
  WSINSIGHT_MCP_URL        — MCP endpoint (default: http://127.0.0.1:8765/mcp)
  WSINSIGHT_MCP_TIMEOUT_MS — request timeout in ms (default: 300000)
  WSINSIGHT_CONTAINER_NAME — default Docker container name (default: clawsight-mcp)
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
except ImportError:
    _HAS_HTTPX = False

logger = logging.getLogger(__name__)

_DOCKER_IMAGE    = "huangchtw/wsinsight:latest"
_DEFAULT_PORT    = 8765
_DEFAULT_CNAME   = "clawsight-mcp"
_DEFAULT_MCP_URL = f"http://127.0.0.1:{_DEFAULT_PORT}/mcp"

# sptxinsight runs as a SEPARATE container / MCP server (its own image, port
# and name) so it can run side by side with the wsinsight server.
_SPTX_DOCKER_IMAGE    = "huangchtw/sptxinsight:latest"
_SPTX_DEFAULT_PORT    = 8766
_SPTX_DEFAULT_CNAME   = "clawsight-sptx-mcp"
_SPTX_DEFAULT_MCP_URL = f"http://127.0.0.1:{_SPTX_DEFAULT_PORT}/mcp"


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


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

class _State:
    def __init__(
        self,
        *,
        default_url: str = _DEFAULT_MCP_URL,
        default_cname: str = _DEFAULT_CNAME,
        url_env: str = "WSINSIGHT_MCP_URL",
        timeout_env: str = "WSINSIGHT_MCP_TIMEOUT_MS",
        cname_env: str = "WSINSIGHT_CONTAINER_NAME",
    ) -> None:
        self.mcp_url: str = os.environ.get(url_env, default_url)
        self.timeout_s: float = (
            int(os.environ.get(timeout_env, "300000")) / 1000.0
        )
        self.container: str = os.environ.get(cname_env, default_cname)
        self._client: McpHttpClient | None = None

    def client(self) -> McpHttpClient:
        if self._client is None or self._client.url != self.mcp_url.rstrip("/"):
            self._client = McpHttpClient(self.mcp_url, self.timeout_s)
        return self._client

    def reset(self) -> None:
        if self._client:
            self._client.reset()
        self._client = None


_state = _State()
_sptx_state = _State(
    default_url=_SPTX_DEFAULT_MCP_URL,
    default_cname=_SPTX_DEFAULT_CNAME,
    url_env="SPTXINSIGHT_MCP_URL",
    timeout_env="SPTXINSIGHT_MCP_TIMEOUT_MS",
    cname_env="SPTXINSIGHT_CONTAINER_NAME",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


async def _proxy(mcp_tool_name: str, params: dict, state: "_State | None" = None) -> str:
    """Parse 'arguments' from params and proxy to the MCP server."""
    st = state if state is not None else _state
    args = _parse_arguments(params)
    if isinstance(args, str):
        return args
    try:
        return await st.client().call_tool(mcp_tool_name, args)
    except Exception as exc:
        st.reset()
        msg = str(exc).lower()
        if any(w in msg for w in ("connect", "connection", "refused", "timeout")):
            return (
                f"[ERROR] Cannot reach MCP server at {st.mcp_url}.\n"
                "Ensure the Docker container is running and connected."
            )
        return f"[ERROR] MCP call '{mcp_tool_name}' failed: {exc}"


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


# ---------------------------------------------------------------------------
# Connection / Docker management
# ---------------------------------------------------------------------------

async def wsinsight_server_info(params: dict, **_: Any) -> str:
    return json.dumps(
        {
            "mcp_url": _state.mcp_url,
            "container_name": _state.container,
            "timeout_ms": int(_state.timeout_s * 1000),
            "session_active": (
                _state._client is not None
                and _state._client._session_id is not None
            ),
        },
        indent=2,
    )


async def wsinsight_connect(params: dict, **_: Any) -> str:
    if url := (params.get("mcp_url") or "").strip():
        _state.mcp_url = url
        _state.reset()
    if ms := params.get("timeout_ms"):
        _state.timeout_s = float(ms) / 1000.0
        _state.reset()
    try:
        init = await _state.client().initialize()
        result = init.get("result", {})
        si = result.get("serverInfo", {})
        pv = result.get("protocolVersion", "?")
        return (
            f"Connected to WSInsight MCP server.\n"
            f"  URL:      {_state.mcp_url}\n"
            f"  Server:   {si.get('name', '?')} v{si.get('version', '?')}\n"
            f"  Protocol: {pv}"
        )
    except Exception as exc:
        _state.reset()
        return (
            f"[ERROR] Connection to {_state.mcp_url} failed: {exc}\n"
            "Is the container running? Start it with wsinsight_start_docker."
        )


async def wsinsight_start_docker(params: dict, **_: Any) -> str:
    data_dir = (params.get("data_dir") or "").strip()
    if not data_dir:
        return "[ERROR] 'data_dir' is required"

    gpu_ids      = (params.get("gpu_ids") or "").strip()
    mcp_port     = int(params.get("mcp_port") or _DEFAULT_PORT)
    cname        = (params.get("container_name") or _state.container).strip()
    max_conc     = params.get("max_concurrent")
    experimental = bool(params.get("experimental", False))

    # Remove any existing container with the same name
    _docker("stop", cname, timeout=20)
    _docker("rm",   cname, timeout=20)

    gpu_flag = f"device={gpu_ids}" if gpu_ids else "all"
    mcp_cmd  = f"wsinsight-mcp --http 0.0.0.0:{mcp_port}"
    if experimental:
        mcp_cmd += " --experimental"
    if max_conc is not None:
        mcp_cmd += f" --max-concurrent {int(max_conc)}"

    rc, out = _docker(
        "run", "-d",
        "--name", cname,
        "--gpus", gpu_flag,
        "--shm-size=32g",
        "--init",
        "-p", f"{mcp_port}:{mcp_port}",
        "-v", f"{data_dir}:/workspace",
        _DOCKER_IMAGE,
        "bash", "-lc", mcp_cmd,
        timeout=120,
    )
    if rc != 0:
        return f"[ERROR] docker run failed (exit {rc}):\n{out}"

    cid = out[:12]
    _state.container = cname
    _state.mcp_url   = f"http://127.0.0.1:{mcp_port}/mcp"
    _state.reset()

    return (
        f"Container started.\n"
        f"  Name:    {cname} ({cid})\n"
        f"  MCP URL: {_state.mcp_url}\n"
        f"  Data:    {data_dir} → /workspace\n"
        f"  GPUs:    {gpu_flag}\n\n"
        "Wait ~5 seconds, then call wsinsight_connect to verify."
    )


async def wsinsight_stop_docker(params: dict, **_: Any) -> str:
    cname = (params.get("container_name") or _state.container).strip()
    rc_stop, _ = _docker("stop", cname, timeout=30)
    rc_rm,   _ = _docker("rm",   cname, timeout=30)
    _state.reset()
    if rc_stop == 0:
        return f"Container '{cname}' stopped and removed."
    return (
        f"[WARN] docker stop exited {rc_stop}. "
        "The container may have already been stopped."
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

async def wsinsight_list_tools(params: dict, **_: Any) -> str:
    try:
        tools = await _state.client().list_tools()
    except Exception as exc:
        _state.reset()
        return f"[ERROR] {exc}"

    if not tools:
        return (
            "No tools found. Is the server running?\n"
            "Start it with wsinsight_start_docker, then call wsinsight_connect."
        )

    lines = [f"WSInsight MCP tools ({len(tools)}):\n"]
    for t in tools:
        name  = t.get("name", "")
        desc  = (t.get("description") or "").split("\n")[0][:110]
        schema  = t.get("inputSchema", {})
        props   = schema.get("properties", {})
        required = set(schema.get("required", []))
        psummary = ", ".join(
            f"{k}{'*' if k in required else ''}" for k in props
        )
        lines.append(f"  {name}")
        lines.append(f"    {desc}")
        if psummary:
            lines.append(f"    params: {psummary}  (* = required)")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline tools (proxied directly to MCP server)
# ---------------------------------------------------------------------------

async def wsinsight_run(params: dict, **_: Any) -> str:
    return await _proxy("run", params)

async def wsinsight_patch(params: dict, **_: Any) -> str:
    return await _proxy("patch", params)

async def wsinsight_infer(params: dict, **_: Any) -> str:
    return await _proxy("infer", params)

async def wsinsight_ncomp(params: dict, **_: Any) -> str:
    return await _proxy("ncomp", params)

async def wsinsight_agg(params: dict, **_: Any) -> str:
    return await _proxy("agg", params)

async def wsinsight_export(params: dict, **_: Any) -> str:
    return await _proxy("export", params)

async def wsinsight_reg(params: dict, **_: Any) -> str:
    return await _proxy("reg", params)


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------

async def wsinsight_job_status(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    try:
        return await _state.client().call_tool("job_status", {"job_id": job_id})
    except Exception as exc:
        _state.reset()
        return f"[ERROR] {exc}"


async def wsinsight_job_logs(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    args: dict[str, Any] = {"job_id": job_id}
    if (since_line := params.get("since_line")) is not None:
        args["since_line"] = int(since_line)
    if (max_lines := params.get("max_lines")) is not None:
        args["max_lines"] = int(max_lines)
    try:
        return await _state.client().call_tool("job_logs", args)
    except Exception as exc:
        _state.reset()
        return f"[ERROR] {exc}"


async def wsinsight_cancel_job(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    try:
        return await _state.client().call_tool("cancel_job", {"job_id": job_id})
    except Exception as exc:
        _state.reset()
        return f"[ERROR] {exc}"


async def wsinsight_list_jobs(params: dict, **_: Any) -> str:
    try:
        return await _state.client().call_tool("list_jobs", {})
    except Exception as exc:
        _state.reset()
        return f"[ERROR] {exc}"


# ===========================================================================
# sptxinsight tools — proxied to a SEPARATE sptxinsight MCP server / container
# ===========================================================================

async def sptx_server_info(params: dict, **_: Any) -> str:
    return json.dumps(
        {
            "mcp_url": _sptx_state.mcp_url,
            "container_name": _sptx_state.container,
            "timeout_ms": int(_sptx_state.timeout_s * 1000),
            "session_active": (
                _sptx_state._client is not None
                and _sptx_state._client._session_id is not None
            ),
        },
        indent=2,
    )


async def sptx_connect(params: dict, **_: Any) -> str:
    if url := (params.get("mcp_url") or "").strip():
        _sptx_state.mcp_url = url
        _sptx_state.reset()
    if ms := params.get("timeout_ms"):
        _sptx_state.timeout_s = float(ms) / 1000.0
        _sptx_state.reset()
    try:
        init = await _sptx_state.client().initialize()
        result = init.get("result", {})
        si = result.get("serverInfo", {})
        pv = result.get("protocolVersion", "?")
        return (
            f"Connected to sptxinsight MCP server.\n"
            f"  URL:      {_sptx_state.mcp_url}\n"
            f"  Server:   {si.get('name', '?')} v{si.get('version', '?')}\n"
            f"  Protocol: {pv}"
        )
    except Exception as exc:
        _sptx_state.reset()
        return (
            f"[ERROR] Connection to {_sptx_state.mcp_url} failed: {exc}\n"
            "Is the container running? Start it with sptx_start_docker."
        )


async def sptx_start_docker(params: dict, **_: Any) -> str:
    data_dir = (params.get("data_dir") or "").strip()
    if not data_dir:
        return "[ERROR] 'data_dir' is required"

    gpu_ids      = (params.get("gpu_ids") or "").strip()
    mcp_port     = int(params.get("mcp_port") or _SPTX_DEFAULT_PORT)
    cname        = (params.get("container_name") or _sptx_state.container).strip()
    max_conc     = params.get("max_concurrent")
    experimental = bool(params.get("experimental", False))

    # Remove any existing container with the same name
    _docker("stop", cname, timeout=20)
    _docker("rm",   cname, timeout=20)

    gpu_flag = f"device={gpu_ids}" if gpu_ids else "all"
    mcp_cmd  = f"sptxinsight-mcp --http 0.0.0.0:{mcp_port}"
    if experimental:
        mcp_cmd += " --experimental"
    if max_conc is not None:
        mcp_cmd += f" --max-concurrent {int(max_conc)}"

    rc, out = _docker(
        "run", "-d",
        "--name", cname,
        "--gpus", gpu_flag,
        "--shm-size=32g",
        "--init",
        "-p", f"{mcp_port}:{mcp_port}",
        "-v", f"{data_dir}:/workspace",
        _SPTX_DOCKER_IMAGE,
        "bash", "-lc", mcp_cmd,
        timeout=120,
    )
    if rc != 0:
        return f"[ERROR] docker run failed (exit {rc}):\n{out}"

    cid = out[:12]
    _sptx_state.container = cname
    _sptx_state.mcp_url   = f"http://127.0.0.1:{mcp_port}/mcp"
    _sptx_state.reset()

    return (
        f"Container started.\n"
        f"  Name:    {cname} ({cid})\n"
        f"  MCP URL: {_sptx_state.mcp_url}\n"
        f"  Data:    {data_dir} → /workspace\n"
        f"  GPUs:    {gpu_flag}\n\n"
        "Wait ~5 seconds, then call sptx_connect to verify."
    )


async def sptx_stop_docker(params: dict, **_: Any) -> str:
    cname = (params.get("container_name") or _sptx_state.container).strip()
    rc_stop, _ = _docker("stop", cname, timeout=30)
    rc_rm,   _ = _docker("rm",   cname, timeout=30)
    _sptx_state.reset()
    if rc_stop == 0:
        return f"Container '{cname}' stopped and removed."
    return (
        f"[WARN] docker stop exited {rc_stop}. "
        "The container may have already been stopped."
    )


async def sptx_list_tools(params: dict, **_: Any) -> str:
    try:
        tools = await _sptx_state.client().list_tools()
    except Exception as exc:
        _sptx_state.reset()
        return f"[ERROR] {exc}"

    if not tools:
        return (
            "No tools found. Is the server running?\n"
            "Start it with sptx_start_docker, then call sptx_connect."
        )

    lines = [f"sptxinsight MCP tools ({len(tools)}):\n"]
    for t in tools:
        name  = t.get("name", "")
        desc  = (t.get("description") or "").split("\n")[0][:110]
        schema  = t.get("inputSchema", {})
        props   = schema.get("properties", {})
        required = set(schema.get("required", []))
        psummary = ", ".join(
            f"{k}{'*' if k in required else ''}" for k in props
        )
        lines.append(f"  {name}")
        lines.append(f"    {desc}")
        if psummary:
            lines.append(f"    params: {psummary}  (* = required)")
        lines.append("")

    return "\n".join(lines)


# -- Pipeline tools (proxied directly to the sptxinsight MCP server) ---------

async def sptx_run(params: dict, **_: Any) -> str:
    return await _proxy("run", params, _sptx_state)

async def sptx_ingest(params: dict, **_: Any) -> str:
    return await _proxy("ingest", params, _sptx_state)

async def sptx_annotate(params: dict, **_: Any) -> str:
    return await _proxy("annotate", params, _sptx_state)

async def sptx_export(params: dict, **_: Any) -> str:
    return await _proxy("export", params, _sptx_state)

async def sptx_cme(params: dict, **_: Any) -> str:
    return await _proxy("cme", params, _sptx_state)

async def sptx_cme_profile(params: dict, **_: Any) -> str:
    return await _proxy("cme_profile", params, _sptx_state)

async def sptx_hplot(params: dict, **_: Any) -> str:
    return await _proxy("hplot", params, _sptx_state)

async def sptx_hplot_finalize(params: dict, **_: Any) -> str:
    return await _proxy("hplot_finalize", params, _sptx_state)

async def sptx_cci(params: dict, **_: Any) -> str:
    return await _proxy("cci", params, _sptx_state)


# -- Job management (sptxinsight server) ------------------------------------

async def sptx_job_status(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    try:
        return await _sptx_state.client().call_tool("job_status", {"job_id": job_id})
    except Exception as exc:
        _sptx_state.reset()
        return f"[ERROR] {exc}"


async def sptx_job_logs(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    args: dict[str, Any] = {"job_id": job_id}
    if (since_line := params.get("since_line")) is not None:
        args["since_line"] = int(since_line)
    if (max_lines := params.get("max_lines")) is not None:
        args["max_lines"] = int(max_lines)
    try:
        return await _sptx_state.client().call_tool("job_logs", args)
    except Exception as exc:
        _sptx_state.reset()
        return f"[ERROR] {exc}"


async def sptx_cancel_job(params: dict, **_: Any) -> str:
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        return "[ERROR] 'job_id' is required"
    try:
        return await _sptx_state.client().call_tool("cancel_job", {"job_id": job_id})
    except Exception as exc:
        _sptx_state.reset()
        return f"[ERROR] {exc}"


async def sptx_list_jobs(params: dict, **_: Any) -> str:
    try:
        return await _sptx_state.client().call_tool("list_jobs", {})
    except Exception as exc:
        _sptx_state.reset()
        return f"[ERROR] {exc}"
