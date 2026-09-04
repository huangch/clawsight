"""ClawSight tool handlers — engine-agnostic.

Five handlers are generated per engine from the registry in ``engines.py``:

    <engine>_start       start the Docker container + MCP server
    <engine>_stop        stop and remove it
    <engine>_status      container / connection health
    <engine>_list_tools  live tool catalog (from the running container)
    <engine>_call        invoke any tool the container exposes

Nothing about a specific engine is hard-coded here, so a new backend only
needs a row in ``ENGINES``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from .engines import ENGINES, Engine, EngineState, state
from .mcpclient import _docker, _parse_arguments

logger = logging.getLogger(__name__)

# The images run as root and remap their baked-in `user` (uid 1000) to the
# owner of the mounted /workspace. Without these the session stays root and
# every output file lands root-owned.
_HOST_UID = str(os.getuid())
_HOST_GID = str(os.getgid())


def _err(msg: str) -> str:
    return f"[ERROR] {msg}"


def _running(container: str) -> bool:
    rc, out = _docker("inspect", "-f", "{{.State.Running}}", container, timeout=15)
    return rc == 0 and out.strip() == "true"


async def _refresh_tools(st: EngineState) -> str | None:
    """Populate st.tools from the live server. Returns an error string or None."""
    try:
        st.tools = await st.client().list_tools()
        return None
    except Exception as exc:
        st.reset()
        return str(exc)


# ---------------------------------------------------------------------------
# Handler factories
# ---------------------------------------------------------------------------

def make_start(engine: Engine) -> Callable:
    async def start(params: dict, **_: Any) -> str:
        st = state(engine.name)
        data_dir = (params.get("data_dir") or "").strip()
        if not data_dir:
            return _err("'data_dir' is required (host directory mounted at /workspace)")
        if not os.path.isdir(data_dir):
            return _err(f"data_dir does not exist: {data_dir}")

        port = int(params.get("port") or st.port)
        cname = (params.get("container_name") or st.container).strip()
        gpu_ids = (params.get("gpu_ids") or "").strip()
        max_conc = params.get("max_concurrent")
        experimental = bool(params.get("experimental", engine.experimental))

        _docker("stop", cname, timeout=30)
        _docker("rm", cname, timeout=30)

        cmd = f"{engine.mcp_bin} --http 0.0.0.0:{port}"
        if experimental and engine.experimental:
            cmd += " --experimental"
        if max_conc is not None:
            cmd += f" --max-concurrent {int(max_conc)}"

        argv = ["run", "-d", "--name", cname]
        if engine.gpu:
            argv += ["--gpus", f"device={gpu_ids}" if gpu_ids else "all"]
        argv += [
            "--shm-size=32g", "--init",
            "-e", f"HOST_UID={_HOST_UID}",
            "-e", f"HOST_GID={_HOST_GID}",
            "-p", f"{port}:{port}",
            "-v", f"{data_dir}:/workspace",
            st.image, "bash", "-lc", cmd,
        ]
        rc, out = _docker(*argv, timeout=180)
        if rc != 0:
            return _err(f"docker run failed (exit {rc}):\n{out}")

        st.port = port
        st.container = cname
        st.mcp_url = f"http://127.0.0.1:{port}/mcp"
        st.reset()

        lines = [
            f"Started '{engine.name}' container {cname} ({out[:12]})",
            f"  image   : {st.image}",
            f"  mcp_url : {st.mcp_url}",
            f"  data_dir: {data_dir} -> /workspace",
        ]
        err = await _refresh_tools(st)
        if err:
            lines.append(
                f"  tools   : not discovered yet ({err.splitlines()[0][:80]}); "
                f"the server may still be starting — retry {engine.name}_list_tools."
            )
        else:
            lines.append(f"  tools   : {len(st.tools)} discovered")
            lines.append("")
            lines.append(_format_tools(engine, st.tools))
        return "\n".join(lines)

    start.__name__ = f"{engine.name}_start"
    return start


def make_stop(engine: Engine) -> Callable:
    async def stop(params: dict, **_: Any) -> str:
        st = state(engine.name)
        cname = (params.get("container_name") or st.container).strip()
        rc1, _ = _docker("stop", cname, timeout=60)
        rc2, out = _docker("rm", cname, timeout=30)
        st.reset()
        st.tools = []
        if rc1 != 0 and rc2 != 0:
            return f"No running container named {cname} (nothing to stop)."
        return f"Stopped and removed '{engine.name}' container {cname}."

    stop.__name__ = f"{engine.name}_stop"
    return stop


def make_status(engine: Engine) -> Callable:
    async def status(params: dict, **_: Any) -> str:
        st = state(engine.name)
        running = _running(st.container)
        lines = [
            f"engine    : {engine.name}",
            f"image     : {st.image}",
            f"container : {st.container} ({'running' if running else 'not running'})",
            f"mcp_url   : {st.mcp_url}",
            f"gpu       : {'yes' if engine.gpu else 'no (CPU only)'}",
        ]
        if not running:
            lines.append(f"\nStart it with {engine.name}_start(data_dir=...).")
            return "\n".join(lines)
        err = await _refresh_tools(st)
        lines.append(
            f"tools     : {len(st.tools)} available" if not err
            else f"tools     : unreachable ({err.splitlines()[0][:80]})"
        )
        return "\n".join(lines)

    status.__name__ = f"{engine.name}_status"
    return status


def _format_tools(engine: Engine, tools: list[dict]) -> str:
    if not tools:
        return "(no tools reported)"
    rows = [f"{engine.name} exposes {len(tools)} tools:"]
    for t in sorted(tools, key=lambda x: x.get("name", "")):
        desc = (t.get("description") or "").strip().splitlines()
        head = desc[0][:88] if desc else ""
        rows.append(f"  {t.get('name', '?'):<22} {head}")
    rows.append(
        f"\nCall any of them with {engine.name}_call("
        f'tool="<name>", arguments={{...}}).'
    )
    return "\n".join(rows)


def make_list_tools(engine: Engine) -> Callable:
    async def list_tools(params: dict, **_: Any) -> str:
        st = state(engine.name)
        detail = (params.get("tool") or "").strip()
        err = await _refresh_tools(st)
        if err:
            return _err(
                f"Cannot reach the {engine.name} MCP server at {st.mcp_url}.\n"
                f"Start it with {engine.name}_start(data_dir=...).\nDetail: {err}"
            )
        if detail:
            for t in st.tools:
                if t.get("name") == detail:
                    return json.dumps(t, indent=2, sort_keys=True)
            return _err(f"{engine.name} has no tool named '{detail}'")
        return _format_tools(engine, st.tools)

    list_tools.__name__ = f"{engine.name}_list_tools"
    return list_tools


def make_call(engine: Engine) -> Callable:
    async def call(params: dict, **_: Any) -> str:
        st = state(engine.name)
        tool = (params.get("tool") or "").strip()
        if not tool:
            return _err(
                f"'tool' is required. Run {engine.name}_list_tools() to see what "
                f"this engine exposes."
            )
        args = _parse_arguments(params)
        if isinstance(args, str):
            return args
        try:
            return await st.client().call_tool(tool, args)
        except Exception as exc:
            st.reset()
            msg = str(exc).lower()
            if any(w in msg for w in ("connect", "connection", "refused", "timeout")):
                return _err(
                    f"Cannot reach the {engine.name} MCP server at {st.mcp_url}.\n"
                    f"Start it with {engine.name}_start(data_dir=...)."
                )
            return _err(f"{engine.name}.{tool} failed: {exc}")

    call.__name__ = f"{engine.name}_call"
    return call


FACTORIES: dict[str, Callable[[Engine], Callable]] = {
    "start": make_start,
    "stop": make_stop,
    "status": make_status,
    "list_tools": make_list_tools,
    "call": make_call,
}


def build_handlers() -> dict[str, Callable]:
    """`{tool_name: handler}` for every engine x verb combination."""
    return {
        f"{name}_{verb}": factory(engine)
        for name, engine in ENGINES.items()
        for verb, factory in FACTORIES.items()
    }


__all__ = ["build_handlers", "FACTORIES"]
