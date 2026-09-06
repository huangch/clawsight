// Engine registry for ClawSight — engine-agnostic.
//
// Mirror of `hermes-plugin/engines.py`. Every supported backend is described
// by one table entry; no per-engine code exists outside this file. Adding a
// new engine means adding a row here.
//
// Each engine ships a Docker image whose CLI exposes:
//   * `<cli> schema`         — machine-readable JSON of every sub-command
//   * `<cli>-mcp --http …`   — the MCP server the agent talks to
//
// Every default can be overridden per engine via environment variables:
//   CLAWSIGHT_<ENGINE>_IMAGE, _PORT, _CONTAINER, _MCP_URL, _TIMEOUT_MS
// where `<ENGINE>` is the engine name upper-cased with "-" replaced by "_".
import { McpHttpClient } from "./mcp-client.js";
export class Engine {
    name;
    image;
    cli;
    portDefault;
    gpu;
    experimental;
    summary;
    mcpBin;
    /** Mutable — overwritten after `_start` succeeds with the actual values used. */
    state;
    constructor(spec) {
        this.name = spec.name;
        this.image = spec.image;
        this.cli = spec.cli;
        this.portDefault = spec.port;
        this.gpu = spec.gpu;
        this.experimental = spec.experimental;
        this.summary = spec.summary;
        this.mcpBin = spec.mcpBin ?? `${spec.cli}-mcp`;
        this.state = resolveEnv(this);
    }
}
function envPrefix(name) {
    return "CLAWSIGHT_" + name.toUpperCase().replace(/-/g, "_");
}
function readEnv(prefix, key) {
    const value = process.env[`${prefix}_${key}`];
    return value && value !== "" ? value : undefined;
}
export function resolveEnv(engine) {
    const prefix = envPrefix(engine.name);
    let port = engine.portDefault;
    const portStr = readEnv(prefix, "PORT");
    if (portStr) {
        const parsed = Number(portStr);
        if (Number.isFinite(parsed))
            port = parsed;
    }
    const timeoutMs = Number(readEnv(prefix, "TIMEOUT_MS") ?? "300000");
    return {
        image: readEnv(prefix, "IMAGE") ?? `${engine.image}:latest`,
        port,
        container: readEnv(prefix, "CONTAINER") ?? `clawsight-${engine.name}`,
        mcpUrl: readEnv(prefix, "MCP_URL") ?? `http://127.0.0.1:${port}/mcp`,
        timeoutS: (Number.isFinite(timeoutMs) ? timeoutMs : 300_000) / 1000,
    };
}
// ---------------------------------------------------------------------------
// ENGINES — single source of truth. Order is preserved for tool ordering.
// ---------------------------------------------------------------------------
export const ENGINES = [
    new Engine({
        name: "wsinsight",
        image: "huangchtw/wsinsight",
        cli: "wsinsight",
        port: 8765,
        gpu: true,
        experimental: true,
        summary: "Whole-slide image (WSI) pathology pipeline: tissue segmentation, " +
            "patching, GPU cell inference, neighborhood composition, niche " +
            "discovery and GeoJSON/OME-CSV export.",
    }),
    new Engine({
        name: "sptxinsight",
        image: "huangchtw/sptxinsight",
        cli: "sptxinsight",
        port: 8766,
        gpu: true,
        experimental: true,
        summary: "Spatial-transcriptomics sibling of WSInsight: AnnData ingest, " +
            "cell typing, niche discovery, H-Plot and ligand-receptor (CCI) " +
            "analysis.",
    }),
    new Engine({
        name: "hplot",
        image: "huangchtw/hplot",
        cli: "hplot",
        port: 8767,
        gpu: false,
        experimental: false,
        summary: "H-Plot: signed-distance tissue-boundary profiling with cluster-mass " +
            "permutation tests and GAM effect sizes. CPU only.",
    }),
    new Engine({
        name: "kurtorank",
        image: "huangchtw/kurtorank",
        cli: "kurtorank",
        port: 8768,
        gpu: false,
        experimental: false,
        summary: "KurtoRank: unsupervised ensemble subtype annotation and marker " +
            "ranking for gene-limited spatial transcriptomics.",
    }),
    new Engine({
        name: "wsitrain",
        image: "huangchtw/wsitrain",
        cli: "wsitrain",
        port: 8769,
        gpu: true,
        experimental: false,
        summary: "WSInsight-Train: headless end-to-end training of WSInsight CellViT " +
            "heads.",
        mcpBin: "wsinsight-train-mcp",
    }),
];
const engineByName = new Map(ENGINES.map((e) => [e.name, e]));
export function engine(name) {
    const e = engineByName.get(name);
    if (!e)
        throw new Error(`Unknown engine: ${name}`);
    return e;
}
export class EngineState {
    engine;
    image;
    port;
    container;
    mcpUrl;
    timeoutS;
    // Live tool catalog. Populated by `_start` / `_list_tools`. Drives the
    // post-start expansion described in SKILL.md.
    tools = [];
    _client = null;
    constructor(e) {
        this.engine = e;
        this.image = e.state.image;
        this.port = e.state.port;
        this.container = e.state.container;
        this.mcpUrl = e.state.mcpUrl;
        this.timeoutS = e.state.timeoutS;
    }
    client() {
        if (this._client === null || this._client.url !== this.mcpUrl.replace(/\/$/, "")) {
            this._client = new McpHttpClient(this.mcpUrl, this.timeoutS);
        }
        return this._client;
    }
    reset() {
        if (this._client !== null)
            this._client.reset();
        this.tools = [];
    }
}
export const STATES = Object.fromEntries(ENGINES.map((e) => [e.name, new EngineState(e)]));
export function state(name) {
    const s = STATES[name];
    if (!s)
        throw new Error(`Unknown engine state: ${name}`);
    return s;
}
