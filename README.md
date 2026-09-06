# ClawSight

**ClawSight** lets an AI agent run the whole [WSInsight](https://github.com/huangch/wsinsight)
engine family in Docker. It manages container lifecycle and speaks MCP to the
server inside each container, so an agent can start GPU pipelines, poll jobs and
collect results in natural language.

Five engines are supported:

| Engine | What it does | GPU | Default port | Image |
|---|---|---|---|---|
| `wsinsight` | Whole-slide pathology: tissue segmentation, patching, GPU cell inference, neighborhood composition, niche discovery, GeoJSON/OME-CSV export | yes | 8765 | `huangchtw/wsinsight` |
| `sptxinsight` | Spatial transcriptomics: AnnData ingest, cell typing, niche discovery, H-Plot, ligand–receptor (CCI) | yes | 8766 | `huangchtw/sptxinsight` |
| `hplot` | Signed-distance boundary profiling: cluster-mass permutation tests, GAM effect sizes | no | 8767 | `huangchtw/hplot` |
| `kurtorank` | Unsupervised subtype annotation and marker ranking for gene-limited panels | no | 8768 | `huangchtw/kurtorank` |
| `wsitrain` | Headless end-to-end training of WSInsight CellViT heads | yes | 8769 | `huangchtw/wsitrain` |

---

## Design: five tools per engine, nothing hard-coded

ClawSight exposes **25 tools** — the same five for every engine:

| Tool | Purpose |
|---|---|
| `<engine>_start` | Start the container + MCP server, then discover its tools |
| `<engine>_stop` | Stop and remove the container |
| `<engine>_status` | Container state, MCP URL, tool count |
| `<engine>_list_tools` | Live tool catalog; pass `tool=` for one tool's full input schema |
| `<engine>_call` | Invoke any tool the container exposes |

**Tool catalogs are discovered at run time, never hard-coded.** Whatever the
installed image supports is what the agent can call, so a new CLI sub-command
appears without touching ClawSight. Adding a whole new engine is one row in
`hermes-plugin/engines.py`.

This is deliberate: earlier versions duplicated every backend command as a
hand-written schema, which drifted from the CLIs it wrapped.

---

## Architecture

```
Agent (Hermes / OpenClaw)
        │
        │  <engine>_start / _call / _list_tools ...
        ▼
   ClawSight plugin
        │  docker run / stop            MCP Streamable HTTP
        ├──────────────────────────►  container :8765  wsinsight-mcp
        ├──────────────────────────►  container :8766  sptxinsight-mcp
        ├──────────────────────────►  container :8767  hplot-mcp
        ├──────────────────────────►  container :8768  kurtorank-mcp
        └──────────────────────────►  container :8769  wsinsight-train-mcp
```

Each engine runs in its own container on its own port, so several can run
concurrently — for example `wsinsight` producing cell tables while `hplot`
analyses an earlier result.

---

## Prerequisites

**Common:**
- **Docker**; with `nvidia-container-toolkit` for the GPU engines
- **NVIDIA GPU** for `wsinsight`, `sptxinsight`, `wsitrain` (`hplot` and
  `kurtorank` are CPU-only)

**For Hermes Agent:**
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- Python 3.11+ with `httpx` (installed by `build4hermes.sh`)

**For OpenClaw:**
- [OpenClaw](https://openclaw.ai) plus Node.js and npm

---

## Installation

### Hermes Agent

```bash
./build4hermes.sh
```

It installs `httpx`, copies `hermes-plugin/` to `~/.hermes/plugins/clawsight/`,
syntax-checks the Python files and reports registration status. Restart Hermes
afterwards if it is already running.

### OpenClaw

```bash
./build4openclaw.sh
```

The OpenClaw plugin is **engine-agnostic**: it mirrors the Hermes plugin
exactly — same five-tools-per-engine surface for every backend in
`openclaw-plugin/src/engines.ts`. Add a row there and you get the matching
`<engine>_start` / `_stop` / `_status` / `_list_tools` / `_call` tools with
no other code changes.

---

## Usage

Start the container first — nothing else works until it is running.

```jsonc
// 1. start (mounts /data/slides at /workspace inside the container)
wsinsight_start({"data_dir": "/data/slides", "gpu_ids": "0"})

// 2. see what this image offers
wsinsight_list_tools({})

// 3. launch a pipeline — long-running tools return a job_id
wsinsight_call({"tool": "run", "arguments": {
    "wsi_dir": "/workspace/images",
    "results_dir": "/workspace/out",
    "model": "CellViT-SAM-H-x40"
}})

// 4. poll
wsinsight_call({"tool": "job_status", "arguments": {"job_id": "01HZ..."}})
wsinsight_call({"tool": "job_logs",   "arguments": {"job_id": "01HZ..."}})

// 5. done
wsinsight_stop({})
```

### Paths are container paths

`data_dir` is a **host** directory mounted at `/workspace`. After
`wsinsight_start({"data_dir": "/data/slides"})`, the host file
`/data/slides/images/a.svs` is `/workspace/images/a.svs` in every subsequent
`_call`. Passing host paths to `_call` will fail.

### Long-running vs immediate

Pipeline tools (`run`, `patch`, `infer`, `ncomp`, `niche`, training stages, …)
return a `job_id` immediately; poll with `job_status`, stream with `job_logs`,
stop with `cancel_job`, enumerate with `list_jobs` — all via `<engine>_call`.
Short tools (`export`, `reg`, `niche_profile`, …) block and return their result.

### Discovering parameters

Rather than guessing arguments, ask for the tool's own schema:

```jsonc
sptxinsight_list_tools({"tool": "niche"})   // full JSON input schema
```

---

## Configuration

Every default is overridable per engine; all are optional.

| Variable | Example | Description |
|---|---|---|
| `CLAWSIGHT_<ENGINE>_IMAGE` | `huangchtw/wsinsight:v1.2` | Pin a specific image tag |
| `CLAWSIGHT_<ENGINE>_PORT` | `9765` | Host/container port |
| `CLAWSIGHT_<ENGINE>_CONTAINER` | `my-wsinsight` | Container name |
| `CLAWSIGHT_<ENGINE>_MCP_URL` | `http://host:8765/mcp` | Talk to an already-running server, skipping Docker |
| `CLAWSIGHT_<ENGINE>_TIMEOUT_MS` | `600000` | Request timeout |

`<ENGINE>` is the engine name upper-cased, e.g. `CLAWSIGHT_WSINSIGHT_PORT`.

### File ownership

`_start` passes your `HOST_UID`/`HOST_GID` into the container, which remaps its
baked-in `user` (uid 1000) to you and drops privileges. Outputs are therefore
owned by you, not root. If files still come out root-owned, the mounted
directory was root-owned to begin with.

---

## Experimental tools

`wsinsight` and `sptxinsight` hide some sub-commands unless started with
`experimental: true` (the default for both) — for wsinsight that adds `hplot`,
`ecomp`, `tcomp`, `niche`, `niche_profile`, `import` and `agg`; for sptxinsight
`hplot`, `hplot_finalize` and `cci`. `hplot`, `kurtorank` and `wsitrain` have no
such split.

---

## Development

```
hermes-plugin/
├── engines.py     the registry — one row per engine, the only place to add one
├── mcpclient.py   MCP 2025-03-26 Streamable HTTP client + Docker helpers
├── tools.py       five handler factories, engine-agnostic
├── schemas.py     five schema templates, generated from the registry
├── __init__.py    registration loop
├── tools_sync.py  regenerates plugin.yaml from the registry
└── SKILL.md       agent-facing usage guide

openclaw-plugin/
├── src/
│   ├── engines.ts      mirror of engines.py
│   ├── docker.ts       port of _docker() helper
│   ├── mcp-client.ts   MCP 2025-03-26 Streamable HTTP client (engine-agnostic)
│   ├── handlers.ts     start / stop / status / list_tools / call factories
│   ├── schemas.ts      schema templates + TypeBox conversion
│   └── index.ts        loop over ENGINES × verbs, register 25 tools
├── skills/clawsight/SKILL.md   agent-facing usage guide (must stay in sync)
├── openclaw.plugin.json        manifest (compat metadata, no per-engine config)
└── package.json
```

`plugin.yaml`'s `provides_tools` list is generated, never edited by hand:

```bash
python hermes-plugin/tools_sync.py --check   # exit 1 on drift
python hermes-plugin/tools_sync.py           # rewrite it
```

---

## Relationship to ClawPyter

[ClawPyter](https://github.com/huangch/clawpyter) and ClawSight are
complementary:

- **ClawPyter** gives the agent a JupyterLab kernel (Python REPL).
- **ClawSight** gives the agent GPU-scale pipelines in Docker.

Together, an agent can run a WSInsight job through ClawSight, then load and
visualise the resulting GeoJSON/CSV in a ClawPyter notebook — in one
conversation.
