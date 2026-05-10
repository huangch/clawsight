---
name: clawsight
description: Operate WSInsight whole-slide pathology AI via its Docker MCP server
---

# ClawSight Skill

ClawSight gives you full control over WSInsight — an end-to-end whole-slide
image (WSI) pathology analysis toolkit — by connecting to a WSInsight MCP
server running inside a Docker container.

## Pipeline overview

```
WSI file  →  wsinsight_patch  →  wsinsight_infer  →  wsinsight_ncomp  →  wsinsight_export
              (tissue seg +        (GPU model            (Delaunay graph      (GeoJSON /
               HDF5 patches)        inference)            neighborhood)        OME-CSV)
```

Or run everything in one call with **wsinsight_run**.

## Quick-start

```
1. wsinsight_start_docker({ "data_dir": "/path/to/slides", "gpu_ids": "0" })
2. # wait ~5 seconds
3. wsinsight_connect({})
4. wsinsight_list_tools({})           ← discover exact parameter names
5. wsinsight_run({ "arguments": { "wsi": "sample.svs", "out_dir": "results",
                                  "model": "breast-tumor-resnet34.tcga-brca" } })
6. wsinsight_job_status({ "job_id": "<id>" })  ← poll until "done"
7. wsinsight_stop_docker({})          ← clean up when finished
```

## Rules

- **File paths** inside `arguments` must be **relative to `/workspace`**
  (= the `data_dir` you passed to `wsinsight_start_docker`).
- **Always call `wsinsight_list_tools` first** before any pipeline tool.
  The MCP server knows the exact parameter names and types; the plugin does not
  hard-code them to stay in sync automatically.
- **Async tools** (`run`, `patch`, `infer`, `ncomp`) return `job_id` immediately.
  Poll `wsinsight_job_status` until `status` is `"done"` or `"error"`.
- **Sync tools** (`export`, `reg`) block until completion and return output directly.
- If you get a connection error, call `wsinsight_connect` to re-establish the
  session (the server may have restarted or the container may have cycled).
- **Experimental tools** (`hplot`, `ecomp`, `tcomp`, `cme`) appear in
  `wsinsight_list_tools` only when the container was started with
  `"experimental": true`.

## Tool reference

| Tool | Category | Blocks? |
|------|----------|---------|
| `wsinsight_server_info`  | Connection | sync |
| `wsinsight_connect`      | Connection | sync |
| `wsinsight_start_docker` | Docker     | sync |
| `wsinsight_stop_docker`  | Docker     | sync |
| `wsinsight_list_tools`   | Discovery  | sync |
| `wsinsight_run`          | Pipeline   | async → job_id |
| `wsinsight_patch`        | Pipeline   | async → job_id |
| `wsinsight_infer`        | Pipeline   | async → job_id |
| `wsinsight_ncomp`        | Pipeline   | async → job_id |
| `wsinsight_export`       | Pipeline   | sync |
| `wsinsight_reg`          | Pipeline   | sync |
| `wsinsight_job_status`   | Job mgmt   | sync |
| `wsinsight_job_logs`     | Job mgmt   | sync |
| `wsinsight_cancel_job`   | Job mgmt   | sync |
| `wsinsight_list_jobs`    | Job mgmt   | sync |
