"""Engine registry for ClawSight.

Every supported backend is described by one table entry; there is no
per-engine code anywhere else in the plugin. Adding a new engine means adding
a row here.

Each engine ships a Docker image whose CLI exposes:
  * ``<cli> schema``          — machine-readable JSON of every sub-command
  * ``<cli>-mcp --http ...``  — the MCP server the agent talks to

Every default can be overridden per engine via environment variables:
  CLAWSIGHT_<ENGINE>_IMAGE, _PORT, _CONTAINER, _MCP_URL, _TIMEOUT_MS
(``<ENGINE>`` upper-cased with ``-`` replaced by ``_``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .mcpclient import McpHttpClient


@dataclass(frozen=True)
class Engine:
    """Static description of one backend."""

    name: str
    image: str
    cli: str
    port: int
    gpu: bool
    experimental: bool
    summary: str
    # MCP server binary; defaults to "<cli>-mcp" but wsitrain breaks the pattern.
    mcp_bin: str = ""

    def __post_init__(self) -> None:
        if not self.mcp_bin:
            object.__setattr__(self, "mcp_bin", f"{self.cli}-mcp")

    @property
    def env_prefix(self) -> str:
        return "CLAWSIGHT_" + self.name.upper().replace("-", "_")

    def _env(self, key: str, default: Any) -> Any:
        return os.environ.get(f"{self.env_prefix}_{key}", default)

    def resolved(self) -> dict[str, Any]:
        port = int(self._env("PORT", self.port))
        return {
            "image": self._env("IMAGE", f"{self.image}:latest"),
            "port": port,
            "container": self._env("CONTAINER", f"clawsight-{self.name}"),
            "mcp_url": self._env("MCP_URL", f"http://127.0.0.1:{port}/mcp"),
            "timeout_s": float(self._env("TIMEOUT_MS", 300_000)) / 1000.0,
        }


ENGINES: dict[str, Engine] = {
    e.name: e
    for e in (
        Engine(
            name="wsinsight",
            image="huangchtw/wsinsight",
            cli="wsinsight",
            port=8765,
            gpu=True,
            experimental=True,
            summary="Whole-slide image (WSI) pathology pipeline: tissue "
                    "segmentation, patching, GPU cell inference, neighborhood "
                    "composition, niche discovery and GeoJSON/OME-CSV export.",
        ),
        Engine(
            name="sptxinsight",
            image="huangchtw/sptxinsight",
            cli="sptxinsight",
            port=8766,
            gpu=True,
            experimental=True,
            summary="Spatial-transcriptomics sibling of WSInsight: AnnData "
                    "ingest, cell typing, niche discovery, H-Plot and "
                    "ligand-receptor (CCI) analysis.",
        ),
        Engine(
            name="hplot",
            image="huangchtw/hplot",
            cli="hplot",
            port=8767,
            gpu=False,
            experimental=False,
            summary="H-Plot: signed-distance tissue-boundary profiling with "
                    "cluster-mass permutation tests and GAM effect sizes. "
                    "CPU only.",
        ),
        Engine(
            name="kurtorank",
            image="huangchtw/kurtorank",
            cli="kurtorank",
            port=8768,
            gpu=False,
            experimental=False,
            summary="KurtoRank: unsupervised ensemble subtype annotation and "
                    "marker ranking for gene-limited spatial transcriptomics.",
        ),
        Engine(
            name="wsitrain",
            image="huangchtw/wsitrain",
            cli="wsitrain",
            port=8769,
            gpu=True,
            experimental=False,
            summary="WSInsight-Train: headless end-to-end training of "
                    "WSInsight CellViT heads.",
            mcp_bin="wsinsight-train-mcp",
        ),
    )
}


class EngineState:
    """Live connection state for one engine (one per plugin lifetime)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        cfg = engine.resolved()
        self.image: str = cfg["image"]
        self.port: int = cfg["port"]
        self.container: str = cfg["container"]
        self.mcp_url: str = cfg["mcp_url"]
        self.timeout_s: float = cfg["timeout_s"]
        self._client: McpHttpClient | None = None
        # Populated by <engine>_start / _list_tools; drives the post-start
        # expansion described in SKILL.md.
        self.tools: list[dict] = []

    def client(self) -> McpHttpClient:
        if self._client is None or self._client.url != self.mcp_url.rstrip("/"):
            self._client = McpHttpClient(self.mcp_url, timeout_s=self.timeout_s)
        return self._client

    def reset(self) -> None:
        if self._client is not None:
            self._client.reset()


STATES: dict[str, EngineState] = {name: EngineState(e) for name, e in ENGINES.items()}


def state(name: str) -> EngineState:
    return STATES[name]


__all__ = ["Engine", "ENGINES", "EngineState", "STATES", "state"]
