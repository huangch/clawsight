---
name: clawsight
description: Run the WSInsight engine family (wsinsight, sptxinsight, hplot, kurtorank, wsitrain) in Docker via MCP.
---

# ClawSight Skill

ClawSight starts Docker containers for five analysis engines and proxies tool
calls to the MCP server inside each one.

| Engine | What it does | GPU | Port |
|---|---|---|---|
| `wsinsight` | Whole-slide pathology: tissue segmentation, patching, GPU cell inference, neighborhood composition, niche discovery, GeoJSON/OME-CSV export | yes | 8765 |
| `sptxinsight` | Spatial transcriptomics: AnnData ingest, cell typing, niche discovery, H-Plot, ligand-receptor (CCI) | yes | 8766 |
| `hplot` | Signed-distance boundary profiling: cluster-mass permutation tests, GAM effect sizes | no | 8767 |
| `kurtorank` | Unsupervised subtype annotation and marker ranking for gene-limited panels | no | 8768 |
| `wsitrain` | Headless end-to-end training of WSInsight CellViT heads | yes | 8769 |

## The five tools, per engine

Every engine has exactly the same interface:

| Tool | Purpose |
|---|---|
| `<engine>_start` | Start the container + MCP server, then list its tools |
| `<engine>_stop` | Stop and remove the container |
| `<engine>_status` | Is it running? which URL? how many tools? |
| `<engine>_list_tools` | Live tool catalog; pass `tool=` for one tool's full schema |
| `<engine>_call` | Invoke any tool the container exposes |

**Tool catalogs are discovered live, never hard-coded.** Whatever the installed
image supports is what you can call.

## Standard workflow

Always start the container first — nothing else works until it is running.

```
1. wsinsight_start({"data_dir": "/data/slides"})
      -> mounts /data/slides at /workspace and prints the tool list
2. wsinsight_call({"tool": "run", "arguments": {
       "wsi_dir": "/workspace/images",
       "results_dir": "/workspace/out",
       "model": "CellViT-SAM-H-x40"}})
      -> returns {"job_id": "..."} for long-running tools
3. wsinsight_call({"tool": "job_status", "arguments": {"job_id": "..."}})
      -> poll until status is "done"
4. wsinsight_call({"tool": "job_logs", "arguments": {"job_id": "..."}})
5. wsinsight_stop({})
```

If you do not know a tool's parameters, call
`<engine>_list_tools({"tool": "<name>"})` for its full JSON input schema
rather than guessing.

## Paths are container paths

`data_dir` is a **host** directory; everything inside the container sees it as
`/workspace`. So after `wsinsight_start({"data_dir": "/data/slides"})`, a host
file `/data/slides/images/a.svs` is `/workspace/images/a.svs` in every
subsequent `_call`. Passing host paths to `_call` will fail.

## Long-running vs immediate

Pipeline tools (`run`, `patch`, `infer`, `ncomp`, `niche`, training stages, …)
return a `job_id` immediately. Poll with `job_status`, stream with `job_logs`,
stop with `cancel_job`, and list everything with `list_jobs` — all through
`<engine>_call`.

Short tools (`export`, `reg`, `niche_profile`, …) block and return their result
directly.

## GPUs

`wsinsight`, `sptxinsight` and `wsitrain` take `gpu_ids` on `_start`
(`"0,1"`; omit for all GPUs). `hplot` and `kurtorank` are CPU-only and reject
the option. Use `max_concurrent` to limit parallel jobs — set it to the number
of GPUs you gave the container.

## Experimental tools

`wsinsight` and `sptxinsight` hide some sub-commands unless started with
`experimental: true` (the default for both). `hplot`, `kurtorank` and
`wsitrain` have no such split.

## Engines are independent

Each runs in its own container on its own port, so several can run at once —
for example `wsinsight` producing cell tables while `hplot` analyses an earlier
result. Stopping one does not affect the others.

## Troubleshooting

- **"Cannot reach the ... MCP server"** — the container is not running. Call
  `<engine>_status`, then `<engine>_start`.
- **Tools missing right after `_start`** — the server may still be booting.
  Call `<engine>_list_tools` again.
- **Outputs owned by root** — `_start` passes your uid/gid so the container
  writes as you. If files are still root-owned, the mounted directory was
  root-owned to begin with.
- **Port already in use** — pass a different `port` to `_start`, or set
  `CLAWSIGHT_<ENGINE>_PORT`.

## Configuration

Per-engine overrides, all optional:

```
CLAWSIGHT_<ENGINE>_IMAGE      e.g. huangchtw/wsinsight:v1.2
CLAWSIGHT_<ENGINE>_PORT
CLAWSIGHT_<ENGINE>_CONTAINER
CLAWSIGHT_<ENGINE>_MCP_URL    point at an already-running server
CLAWSIGHT_<ENGINE>_TIMEOUT_MS
```

`<ENGINE>` is the engine name upper-cased, e.g. `CLAWSIGHT_WSINSIGHT_PORT`.
