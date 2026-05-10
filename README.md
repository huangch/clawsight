# ClawSight

**ClawSight** gives any AI agent full control over [WSInsight](https://github.com/huangch/wsinsight) — an end-to-end whole-slide image (WSI) pathology analysis toolkit. It enables Claude or any LLM to start, run, monitor, and stop GPU-accelerated pathology pipelines in natural language, with no manual CLI interaction required.

The WSInsight engine runs inside the official Docker image (`huangchtw/wsinsight:latest`). ClawSight manages the container lifecycle, speaks the MCP protocol to the server inside it, and exposes 15 agent-friendly tools.

Two agents are supported:

| Agent | Plugin format | Install script |
|---|---|---|
| [OpenClaw](https://openclaw.ai) | TypeScript (`openclaw-plugin/dist/index.js`) | `./build4openclaw.sh` |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Python (`hermes-plugin/`) | `./build4hermes.sh` |

---

## What Can It Do?

ClawSight exposes **15 tools** covering the full WSInsight pipeline:

**Docker & Connection:**
- Start the WSInsight Docker container with configurable GPUs, port, and data directory
- Stop and remove the container
- Connect to the MCP server and verify it is reachable
- Inspect the current plugin configuration

**Discovery:**
- Query the live MCP server for its available tools and parameter schemas

**Pipeline (async — returns `job_id` immediately):**
- `wsinsight_run` — full end-to-end pipeline: tissue segmentation → patch extraction → GPU inference → neighborhood composition → export
- `wsinsight_patch` — tissue segmentation and HDF5 patch extraction
- `wsinsight_infer` — GPU model inference on pre-extracted patches
- `wsinsight_ncomp` — per-cell Delaunay graph neighborhood composition

**Pipeline (synchronous):**
- `wsinsight_export` — export results to GeoJSON or OME-CSV
- `wsinsight_reg` — spatial registration of two WSI regions

**Job management:**
- Poll job status, stream log tail, cancel jobs, list all jobs

---

## Architecture

```
User (in OpenClaw or Hermes chat)
        │
        ▼
  Agent Application
  (OpenClaw  ·or·  Hermes Agent)
        │
        ▼
  ClawSight Plugin
  (openclaw-plugin/  ·or·  hermes-plugin/)
        │ ← MCP 2025-03-26 Streamable HTTP
        ▼
  WSInsight MCP Server (inside Docker)
  huangchtw/wsinsight:latest
  wsinsight-mcp --http 0.0.0.0:8765
        │
        ▼
  wsinsight CLI → GPU inference jobs
  /workspace (= your data directory)
```

ClawSight speaks the [MCP 2025-03-26 Streamable HTTP](https://spec.modelcontextprotocol.io/specification/2025-03-26/basic/transports/#streamable-http) transport directly (`POST /mcp`, SSE responses, `Mcp-Session-Id` session). The plugin manages the Docker container lifecycle locally; all heavy computation stays inside the container.

**Key files:**
- **`openclaw-plugin/src/index.ts`** — TypeScript plugin. Registers all 15 tools with OpenClaw.
- **`openclaw-plugin/src/wsinsight-mcp-client.ts`** — `WsInsightMcpClient` class. MCP HTTP client + Docker helpers (TypeScript, native `fetch` + `child_process`).
- **`openclaw-plugin/skills/clawsight/SKILL.md`** — Operating instructions for the AI (OpenClaw).
- **`hermes-plugin/tools.py`** — `McpHttpClient` class + 15 async handler functions (Python, `httpx`).
- **`hermes-plugin/schemas.py`** — JSON schemas the LLM sees when choosing tools.
- **`hermes-plugin/skill.md`** — Operating instructions for the AI (Hermes).
- **`start-wsinsight.sh`** — Helper script to start the Docker container.
- **`stop-wsinsight.sh`** — Helper script to stop the Docker container.

---

## Prerequisites

**Common (both agents):**
- **Docker** with GPU support (`nvidia-container-toolkit`)
- **NVIDIA GPU** (required for WSInsight model inference)

**For OpenClaw:**
- **OpenClaw** installed and running ([openclaw.ai](https://openclaw.ai))
- **Node.js** and **npm** ([nodejs.org](https://nodejs.org))

**For Hermes Agent:**
- **Hermes Agent** installed ([github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent))
- **Python 3.9+** with `pip install httpx` (handled automatically by `build4hermes.sh`)

---

## Installation

### Installing for OpenClaw

```bash
./build4openclaw.sh
```

`build4openclaw.sh` installs npm dependencies, compiles `src/` to `dist/index.js`, and registers the plugin with OpenClaw.

---

### Installing for Hermes Agent

```bash
./build4hermes.sh
```

`build4hermes.sh`:
1. Installs `httpx` via `pip`
2. Copies `hermes-plugin/` to `~/.hermes/plugins/clawsight/`
3. Syntax-checks all Python files
4. Reports registration status

The plugin is discovered by Hermes at startup. If Hermes is already running, restart it after installing.

**Configuration for Hermes** (optional — set in your shell or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `WSINSIGHT_MCP_URL` | `http://127.0.0.1:8765/mcp` | MCP endpoint URL |
| `WSINSIGHT_MCP_TIMEOUT_MS` | `300000` | Request timeout in ms (5 minutes) |
| `WSINSIGHT_CONTAINER_NAME` | `clawsight-mcp` | Default Docker container name |

---

## Usage

### Step 1 — Start the Docker container

Use the helper script or ask the AI to call `wsinsight_start_docker`:

```bash
./start-wsinsight.sh -d /path/to/slides -g 0
```

**Script options:**
```
Usage: ./start-wsinsight.sh -d <data_dir> [options]

  -d <data_dir>       Required. Host path mounted as /workspace inside the container.
  -g <gpu_ids>        Comma-separated GPU IDs (e.g. 0,1). Default: all GPUs.
  -p <port>           MCP HTTP port. Default: 8765.
  -n <name>           Container name. Default: clawsight-mcp.
  -c <max_concurrent> Max concurrent GPU jobs. Default: auto (= GPU count).
  -e                  Enable experimental tools (hplot/ecomp/tcomp/cme).
  -h                  Show help and exit.
```

Or let the AI do it — paste this into the agent chat:

```
Start WSInsight with data directory /path/to/slides on GPU 0.
```

### Step 2 — Verify the connection

Wait ~5 seconds after starting the container, then:

```
Connect to WSInsight and show available tools.
```

The AI calls `wsinsight_connect` followed by `wsinsight_list_tools`.

### Step 3 — Run a pipeline

```
Run a full WSInsight analysis on sample.svs using the
breast-tumor-resnet34.tcga-brca model and save results to results/.
```

The AI calls `wsinsight_run` with the appropriate arguments, then polls `wsinsight_job_status` until the job is done.

### Step 4 — Stop the container

```bash
./stop-wsinsight.sh
```

Or ask the AI: `Stop the WSInsight container.`

---

## Tool Reference

| Tool | Category | Returns |
|---|---|---|
| `wsinsight_server_info` | Connection | Current config (URL, container, timeout, session state) |
| `wsinsight_connect` | Connection | Server name, version, protocol version |
| `wsinsight_start_docker` | Docker | Container ID and MCP URL |
| `wsinsight_stop_docker` | Docker | Confirmation |
| `wsinsight_list_tools` | Discovery | All MCP server tools with param schemas |
| `wsinsight_run` | Pipeline | `job_id` (async) |
| `wsinsight_patch` | Pipeline | `job_id` (async) |
| `wsinsight_infer` | Pipeline | `job_id` (async) |
| `wsinsight_ncomp` | Pipeline | `job_id` (async) |
| `wsinsight_export` | Pipeline | Exit status + log tail (sync) |
| `wsinsight_reg` | Pipeline | Exit status + log tail (sync) |
| `wsinsight_job_status` | Job mgmt | Status, elapsed time, progress snippet |
| `wsinsight_job_logs` | Job mgmt | Last N log lines |
| `wsinsight_cancel_job` | Job mgmt | Confirmation |
| `wsinsight_list_jobs` | Job mgmt | Table of all jobs with status |

### Pipeline tool arguments

Pipeline tools (`run`, `patch`, `infer`, `ncomp`, `export`, `reg`) accept a free-form `arguments` JSON object. The agent discovers the exact parameter names and types by calling `wsinsight_list_tools` first — the plugin queries the live MCP server rather than hard-coding schemas, so it stays in sync with every WSInsight version automatically.

All file paths inside `arguments` must be **relative to `/workspace`**, which is the `data_dir` you passed to `wsinsight_start_docker`.

### Async job polling pattern

Long-running tools return immediately:

```json
{ "job_id": "abc123", "status": "started", "hint": "Poll job_status(job_id='abc123')" }
```

Poll until done:

```
wsinsight_job_status({ "job_id": "abc123" })
→ { "status": "running", "elapsed_s": 42, ... }

wsinsight_job_status({ "job_id": "abc123" })
→ { "status": "done", "elapsed_s": 187 }
```

Retrieve logs at any time:

```
wsinsight_job_logs({ "job_id": "abc123", "tail": 100 })
```

---

## Experimental Tools

When the container is started with `-e` (`./start-wsinsight.sh -e -d /data`), additional experimental tools become available via the MCP server:

| Tool | Description |
|---|---|
| `hplot` | H-plot computation |
| `hplot-finalize` | Finalize H-plot output |
| `ecomp` | Edge composition analysis |
| `tcomp` | Triad composition analysis |
| `cme` | Cellular microenvironment clustering |

These appear automatically in `wsinsight_list_tools` output when enabled — no plugin changes required.

---

## Relationship to ClawPyter

[ClawPyter](https://github.com/huangch/clawpyter) and ClawSight are complementary:

- **ClawPyter** gives the agent control over a JupyterLab notebook kernel (Python REPL).
- **ClawSight** gives the agent control over GPU-scale WSI pathology analysis pipelines.

Used together, an agent can run WSInsight jobs via ClawSight, then load and visualize the GeoJSON/CSV results in a ClawPyter notebook — all in a single conversation.
