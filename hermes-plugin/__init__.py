"""ClawSight — Hermes Agent plugin for the WSInsight engine family.

Manages Docker containers for every backend and proxies MCP tool calls to the
server running inside each one. Five tools per engine:

    <engine>_start       start the container + MCP server, discover its tools
    <engine>_stop        stop and remove it
    <engine>_status      container / connection health
    <engine>_list_tools  live tool catalog
    <engine>_call        invoke any tool the container exposes

Engines are declared in ``engines.py``; nothing here is engine-specific, so a
new backend is one table row. Currently: wsinsight, sptxinsight, hplot,
kurtorank, wsitrain.

Typical flow:
    1. wsinsight_start({"data_dir": "/data/slides"})
    2. wsinsight_list_tools({})
    3. wsinsight_call({"tool": "run", "arguments": {...}})
    4. wsinsight_call({"tool": "job_status", "arguments": {"job_id": "..."}})
    5. wsinsight_stop({})

Per-engine overrides (environment):
    CLAWSIGHT_<ENGINE>_IMAGE / _PORT / _CONTAINER / _MCP_URL / _TIMEOUT_MS

Install:
    bash /path/to/clawsight/build4hermes.sh
"""

import logging
import shutil
from pathlib import Path

from .engines import ENGINES
from .schemas import build_schemas
from .tools import build_handlers

logger = logging.getLogger(__name__)


def _install_skill() -> None:
    """Copy the bundled skill file to ~/.hermes/skills/clawsight/ on first load."""
    try:
        from hermes_constants import get_hermes_home
        dest = get_hermes_home() / "skills" / "clawsight" / "SKILL.md"
    except Exception:
        try:
            from hermes_cli.config import get_hermes_home
            dest = get_hermes_home() / "skills" / "clawsight" / "SKILL.md"
        except Exception:
            dest = Path.home() / ".hermes" / "skills" / "clawsight" / "SKILL.md"

    if dest.exists():
        return  # don't overwrite user edits

    source = Path(__file__).parent / "SKILL.md"
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        logger.info("ClawSight: installed skill to %s", dest)


def register(ctx) -> None:
    """Register every engine's tools with the Hermes plugin context."""
    _install_skill()

    schemas = build_schemas()
    handlers = build_handlers()

    missing = set(schemas) ^ set(handlers)
    if missing:
        raise RuntimeError(f"ClawSight: schema/handler mismatch for {sorted(missing)}")

    for name, handler in sorted(handlers.items()):
        ctx.register_tool(
            name=name,
            toolset="clawsight",
            schema=schemas[name],
            handler=handler,
            is_async=True,
        )

    logger.info(
        "ClawSight: registered %d tools across %d engines (%s)",
        len(handlers), len(ENGINES), ", ".join(sorted(ENGINES)),
    )
