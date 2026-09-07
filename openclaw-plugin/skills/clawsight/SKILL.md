---
name: clawsight
description: Operate wsinsight / sptxinsight / hplot / kurtorank / wsitrain through Docker-hosted MCP servers — start containers, discover tools, run analyses, and poll async jobs.
---

# ClawSight Skill (OpenClaw)

ClawSight is **engine-agnostic**: every supported backend (currently five) is
described by one row in `openclaw-plugin/src/engines.ts`. Each engine exposes
the same five tools:

```
<engine>_start         start the Docker container + MCP server
<engine>_stop          stop and remove the container
<engine>_status        container health + how many tools are exposed
<engine>_list_tools    live tool catalog (pass `tool=` for one tool's full schema)
<engine>_call          invoke any tool the container exposes
```

Adding a new engine means adding a row in `engines.ts` (image, port, GPU
flag, summary). Neither this skill nor `index.ts` needs to change.

## Engines

| Prefix | Engine | Image | Default port | GPU |
| ------ | ------ | ----- | ------------ | --- |
| `wsinsight_` | Whole-slide-image pathology pipeline | `huangchtw/wsinsight` | 8765 | yes |
| `sptxinsight_` | Spatial transcriptomics (AnnData in, micron coords) | `huangchtw/sptxinsight` | 8766 | yes |
| `hplot_` | H-Plot stats/plotting core (CPU only) | `huangchtw/hplot` | 8767 | no |
| `kurtorank_` | Unsupervised subtype annotation + marker ranking | `huangchtw/kurtorank` | 8768 | no |
| `wsitrain_` | Headless end-to-end training of WSInsight CellViT heads | `huangchtw/wsitrain` | 8769 | yes |

Everything below that says `<engine>` applies to **all five** prefixes.

## Recommended lifecycle

```
1. <engine>_start   ({ data_dir: "...", ... })
2. <engine>_status  ({})              ← confirm container is up
3. <engine>_list_tools({})            ← discover exact parameter names
4. <engine>_call({ tool: "<name>", arguments: { ... } })
5. (long-running tool?) <engine>_call({ tool: "job_status", arguments: { job_id: "..." } })   ← poll until terminal
6. <engine>_stop    ({})
```

`list_tools` and `call` are the only two tools you usually need after the
container is up. `start` and `stop` own container lifecycle. The actual
pipeline commands (`run`, `infer`, `screen`, `loci`, …) live **inside the
container's MCP server** and are discovered at runtime — see step 3.

## Tool reference

### `<engine>_start`

Start the Docker container and its MCP server, then discover the tools it
exposes. Replaces any container with the same name.

| Parameter | Type | Required | Default | Description |
| --------- | ---- | -------- | ------- | ----------- |
| `data_dir` | string | **yes** | — | Host directory mounted at `/workspace`. All inputs and outputs live under it. |
| `port` | integer | no | engine default | Host/container port for the MCP server. |
| `container_name` | string | no | `clawsight-<engine>` | Container name. |
| `max_concurrent` | integer | no | server default | Cap on simultaneous jobs the server will run. |
| `gpu_ids` | string (GPU engines only) | no | `all` | Comma-separated GPU ids to expose, e.g. `"0,1"`. |
| `experimental` | boolean (experimental engines only) | no | engine default | Expose experimental sub-commands as tools. |

Per-engine defaults can be overridden via env vars
(`CLAWSIGHT_<ENGINE>_IMAGE`, `_PORT`, `_CONTAINER`, `_MCP_URL`, `_TIMEOUT_MS`;
upper-cased, dashes → underscores).

### `<engine>_stop`

Stop and remove the container.

| Parameter | Type | Required | Default | Description |
| --------- | ---- | -------- | ------- | ----------- |
| `container_name` | string | no | `clawsight-<engine>` | Container name to stop. |

### `<engine>_status`

Report whether the container is running, its MCP URL, and how many tools it
currently exposes.

No parameters.

### `<engine>_list_tools`

List the tools the running server exposes, with a short description of each.
Pass `tool="<name>"` to get that tool's full JSON input schema.

| Parameter | Type | Required | Default | Description |
| --------- | ---- | -------- | ------- | ----------- |
| `tool` | string | no | — | Return the full schema for this one tool instead of the summary list. |

Tool catalogs are **discovered at run time** — never hard-coded in this
plugin. Whatever the installed image supports is what the agent can call, so
a new CLI sub-command appears without touching ClawSight.

### `<engine>_call`

Invoke any tool exposed by the running server. Use `<engine>_list_tools`
first to discover tool names and their parameters. Long-running tools return
a `job_id`; poll it by calling `<engine>_call` again with
`tool="job_status"` (engine-specific job polling tools are also discovered).

| Parameter | Type | Required | Default | Description |
| --------- | ---- | -------- | ------- | ----------- |
| `tool` | string | **yes** | — | Tool name as reported by `<engine>_list_tools`. |
| `arguments` | object | no | `{}` | Arguments object for that tool, matching its input schema. May be a JSON string or an object. |

## Examples

### Run a WSInsight patch + infer pipeline

```
1. wsinsight_start({ data_dir: "/data/wsi", gpu_ids: "0" })
2. wsinsight_status({})                                        ← "running"
3. wsinsight_list_tools({})                                   ← returns ~14 tools
4. wsinsight_call({ tool: "run", arguments: {
                  wsi_dir: "raw", results_dir: "results",
                  model: "CellViT-SAM-H-x40"
                } })                                          ← returns job_id
5. wsinsight_call({ tool: "job_status", arguments: { job_id: "<id>" } })
   # repeat step 5 until status === "succeeded" or "failed"
6. wsinsight_stop({})
```

### H-Plot a downstream result

```
1. hplot_start({ data_dir: "/data/wsi/results", port: 8767 })
2. hplot_list_tools({})                                        ← plot, test, screen, gam, schema
3. hplot_call({ tool: "plot",   arguments: { ... } })
4. hplot_call({ tool: "screen", arguments: { ... } })        ← long-running → job_id
5. hplot_call({ tool: "job_status", arguments: { job_id: "..." } })
6. hplot_stop({})
```

## Why a plugin / MCP and not just `docker run wsinsight …`?

The engines all expose a CLI, and the agent's `run_command` works fine for
quick one-shots. ClawSight earns its keep when:

- The command is **long-running** (30 min+ pipelines). The handler returns a
  human-readable summary + `job_id` immediately and lets you poll — no
  `tmux + log scraping` ceremony.
- The **container lifecycle needs to be portable across hosts and Docker
  versions**: GPU mapping, port conflict avoidance, `HOST_UID/HOST_GID`
  remapping, image pinning defaults.
- You need a **consistent shape** across five engines — one `start`/`stop`/
  `status`/`list_tools`/`call` template beats re-learning each engine's CLI.

When you just want to debug a single command end-to-end, `run_command`
straight to the CLI is fine.

## See also

- `hermes-plugin/SKILL.md` — Hermes Agent runtime counterpart (the surface is
  identical; this file and the Hermes one MUST stay in sync on tool names,
  parameter vocabulary, and lifecycle guidance).
- `openclaw-plugin/src/engines.ts` — the engine registry that drives both
  schema and handler generation.
