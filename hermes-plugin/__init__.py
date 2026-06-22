"""ClawSight — Hermes Agent plugin for WSInsight + sptxinsight AI.

Provides tools for managing two MCP servers in Docker:
  * wsinsight_* — whole-slide image (WSI) pathology pipelines.
  * sptx_*      — spatial-transcriptomics cell-typing / CME / H-Plot / CCI.
Each backend runs in its own container (default ports 8765 and 8766).

Configuration (set in .env or environment):
  WSINSIGHT_MCP_URL         — wsinsight MCP endpoint (default: http://127.0.0.1:8765/mcp)
  WSINSIGHT_MCP_TIMEOUT_MS  — request timeout in ms (default: 300000)
  WSINSIGHT_CONTAINER_NAME  — default container name (default: clawsight-mcp)
  SPTXINSIGHT_MCP_URL        — sptxinsight MCP endpoint (default: http://127.0.0.1:8766/mcp)
  SPTXINSIGHT_MCP_TIMEOUT_MS — request timeout in ms (default: 300000)
  SPTXINSIGHT_CONTAINER_NAME — default container name (default: clawsight-sptx-mcp)

Install:
  bash /path/to/clawsight/build4hermes.sh

Usage (wsinsight):
  1. wsinsight_start_docker({ "data_dir": "/data/slides" })
  2. wsinsight_connect({})
  3. wsinsight_list_tools({})
  4. wsinsight_run({ "arguments": { ... } })
  5. wsinsight_job_status({ "job_id": "..." })  # poll until done
  6. wsinsight_stop_docker({})

Usage (sptxinsight): same flow with the sptx_* tools.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

from . import schemas
from . import tools as _tools


def _install_skill() -> None:
    """Copy the bundled skill file to ~/.hermes/skills/clawsight/ on first load."""
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
    """Register all ClawSight tools with the Hermes plugin context."""

    _install_skill()

    _TOOLS = [
        # ------------------------------------------------------------------
        # Connection / Docker management
        # ------------------------------------------------------------------
        (
            "wsinsight_server_info",
            schemas.WSINSIGHT_SERVER_INFO,
            _tools.wsinsight_server_info,
        ),
        (
            "wsinsight_connect",
            schemas.WSINSIGHT_CONNECT,
            _tools.wsinsight_connect,
        ),
        (
            "wsinsight_start_docker",
            schemas.WSINSIGHT_START_DOCKER,
            _tools.wsinsight_start_docker,
        ),
        (
            "wsinsight_stop_docker",
            schemas.WSINSIGHT_STOP_DOCKER,
            _tools.wsinsight_stop_docker,
        ),
        # ------------------------------------------------------------------
        # Discovery
        # ------------------------------------------------------------------
        (
            "wsinsight_list_tools",
            schemas.WSINSIGHT_LIST_TOOLS,
            _tools.wsinsight_list_tools,
        ),
        # ------------------------------------------------------------------
        # Pipeline
        # ------------------------------------------------------------------
        (
            "wsinsight_run",
            schemas.WSINSIGHT_RUN,
            _tools.wsinsight_run,
        ),
        (
            "wsinsight_patch",
            schemas.WSINSIGHT_PATCH,
            _tools.wsinsight_patch,
        ),
        (
            "wsinsight_infer",
            schemas.WSINSIGHT_INFER,
            _tools.wsinsight_infer,
        ),
        (
            "wsinsight_ncomp",
            schemas.WSINSIGHT_NCOMP,
            _tools.wsinsight_ncomp,
        ),
        (
            "wsinsight_agg",
            schemas.WSINSIGHT_AGG,
            _tools.wsinsight_agg,
        ),
        (
            "wsinsight_export",
            schemas.WSINSIGHT_EXPORT,
            _tools.wsinsight_export,
        ),
        (
            "wsinsight_reg",
            schemas.WSINSIGHT_REG,
            _tools.wsinsight_reg,
        ),
        # ------------------------------------------------------------------
        # Job management
        # ------------------------------------------------------------------
        (
            "wsinsight_job_status",
            schemas.WSINSIGHT_JOB_STATUS,
            _tools.wsinsight_job_status,
        ),
        (
            "wsinsight_job_logs",
            schemas.WSINSIGHT_JOB_LOGS,
            _tools.wsinsight_job_logs,
        ),
        (
            "wsinsight_cancel_job",
            schemas.WSINSIGHT_CANCEL_JOB,
            _tools.wsinsight_cancel_job,
        ),
        (
            "wsinsight_list_jobs",
            schemas.WSINSIGHT_LIST_JOBS,
            _tools.wsinsight_list_jobs,
        ),
        # ==================================================================
        # sptxinsight tools (separate MCP server / container)
        # ==================================================================
        (
            "sptx_server_info",
            schemas.SPTX_SERVER_INFO,
            _tools.sptx_server_info,
        ),
        (
            "sptx_connect",
            schemas.SPTX_CONNECT,
            _tools.sptx_connect,
        ),
        (
            "sptx_start_docker",
            schemas.SPTX_START_DOCKER,
            _tools.sptx_start_docker,
        ),
        (
            "sptx_stop_docker",
            schemas.SPTX_STOP_DOCKER,
            _tools.sptx_stop_docker,
        ),
        (
            "sptx_list_tools",
            schemas.SPTX_LIST_TOOLS,
            _tools.sptx_list_tools,
        ),
        (
            "sptx_run",
            schemas.SPTX_RUN,
            _tools.sptx_run,
        ),
        (
            "sptx_ingest",
            schemas.SPTX_INGEST,
            _tools.sptx_ingest,
        ),
        (
            "sptx_annotate",
            schemas.SPTX_ANNOTATE,
            _tools.sptx_annotate,
        ),
        (
            "sptx_export",
            schemas.SPTX_EXPORT,
            _tools.sptx_export,
        ),
        (
            "sptx_cme",
            schemas.SPTX_CME,
            _tools.sptx_cme,
        ),
        (
            "sptx_cme_profile",
            schemas.SPTX_CME_PROFILE,
            _tools.sptx_cme_profile,
        ),
        (
            "sptx_hplot",
            schemas.SPTX_HPLOT,
            _tools.sptx_hplot,
        ),
        (
            "sptx_hplot_finalize",
            schemas.SPTX_HPLOT_FINALIZE,
            _tools.sptx_hplot_finalize,
        ),
        (
            "sptx_cci",
            schemas.SPTX_CCI,
            _tools.sptx_cci,
        ),
        (
            "sptx_job_status",
            schemas.SPTX_JOB_STATUS,
            _tools.sptx_job_status,
        ),
        (
            "sptx_job_logs",
            schemas.SPTX_JOB_LOGS,
            _tools.sptx_job_logs,
        ),
        (
            "sptx_cancel_job",
            schemas.SPTX_CANCEL_JOB,
            _tools.sptx_cancel_job,
        ),
        (
            "sptx_list_jobs",
            schemas.SPTX_LIST_JOBS,
            _tools.sptx_list_jobs,
        ),
    ]

    for name, schema, handler in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="clawsight",
            schema=schema,
            handler=handler,
            is_async=True,
        )
