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
5. wsinsight_run({ "arguments": { "wsi_dir": "slides",
                                  "results_dir": "results",
                                  "model": "breast-tumor-resnet34.tcga-brca" } })
6. wsinsight_job_status({ "job_id": "<id>" })  ← poll until "done"
7. wsinsight_stop_docker({})          ← clean up when finished
```

## Rules

- **File paths** inside `arguments` must be **relative to `/workspace`**
  (= the `data_dir` you passed to `wsinsight_start_docker`).
- **Argument names are the WSInsight CLI parameter names in snake_case**
  (e.g. `wsi_dir`, `results_dir`, `batch_size`, `num_workers`,
  `region_inference_dir`, `export_geojson`). Always call
  `wsinsight_list_tools` first — the MCP server exposes the canonical
  schema and the plugin does not hard-code it.
- **Async tools** (long-running on the server) return `job_id` immediately:
  `run`, `patch`, `infer`, `ncomp`, plus the experimental `hplot`, `ecomp`,
  `tcomp`, `cme`. Poll `wsinsight_job_status` until `status` is `"done"`
  or `"error"`.
- **Sync tools** (`export`, `reg`, and the experimental `hplot-finalize`)
  block until completion and return output directly.
- If you get a connection error, call `wsinsight_connect` to re-establish the
  session (the server may have restarted or the container may have cycled).
- **Experimental tools** (`hplot`, `hplot-finalize`, `ecomp`, `tcomp`, `cme`)
  appear in `wsinsight_list_tools` only when the container was started with
  `"experimental": true` (which sets `WSINSIGHT_EXPERIMENTAL=1` and launches
  the server with `--experimental`).

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

## Available models

Pass one of the names below as the `model` argument. The MCP server resolves
them from the bundled WSInsight zoo registry inside the container; no network
access is required.

**Cell-level (object-based) models** — each cell becomes one row in
`model-outputs-csv/<slide>.csv`:

- `CellViT-256-x20`, `CellViT-256-x40`, `CellViT-256-x40-AMP`
- `CellViT-SAM-H-x20`, `CellViT-SAM-H-x40`, `CellViT-SAM-H-x40-AMP`
- `CellViT-Virchow-x40-AMP`
- `10xGenomics-BRCA-CellViT-SAM-H-x40`,
  `10xGenomics-CRC-CellViT-SAM-H-x40`
- `hovernet_fast_pannuke`
- `hne_cell_classification`

**Region / patch-level models** — each patch becomes one row
(useful as `region_inference_dir` for `reg` or for `region_prob_*` columns):

- `breast-tumor-resnet34.tcga-brca`
- `lung-tumor-resnet34.tcga-luad`
- `pancreas-tumor-preactresnet34.tcga-paad`
- `prostate-tumor-resnet34.tcga-prad`
- `pancancer-lymphocytes-inceptionv4.tcga`
- `lymphnodes-tiatoolbox-resnet50.patchcamelyon`
- `colorectal-tiatoolbox-resnet50.kather100k`
- `colorectal-resnet34.penn`

**Selection rules:**

- The `x20` / `x40` suffix on CellViT models **must match the slide
  magnification** (TCGA diagnostic SVS slides are typically 40x).
- `--model` is mutually exclusive with the trio
  (`--config` + `--model-path`) and `--zoo-model-dir` (folder with
  `config.json` + `torchscript_model.pt`). For ad hoc weights, pass them via
  the `config`/`model_path` or `zoo_model_dir` arguments instead of `model`.

## Output data formats

Everything lands under the `results_dir` you passed (relative to `/workspace`):

```
<results_dir>/
  masks/<slide>.jpg                  Tissue segmentation thumbnails
  patches/<slide>.h5                 Patch coords (and optional images)
  model-outputs-csv/<slide>.csv      Per-cell (or per-patch) inference table
  ncomp-outputs-csv/<slide>.csv      Per-cell neighborhood composition
  graphs/<slide>.h5                  Cached Delaunay graph
  export-csv/<slide>.csv             Merged per-cell table (model + ncomp)
  export-geojson/<slide>.geojson     QuPath-compatible GeoJSON
  export-omecsv/<slide>.ome.csv.gz   QuPath / OMERO+ compatible OME-CSV
  patch_metadata_<ts>.json           Patch-stage configuration
  infer_metadata_<ts>.json           Inference-stage configuration
```

### `model-outputs-csv/<slide>.csv` (per-cell or per-patch)

Columns:

- `minx`, `miny`, `width`, `height` — bounding box in level-0 pixels.
- `prob_<class>` — one float column per model class. The class names come
  from the model's bundled `config.json` (e.g. `prob_tumor`,
  `prob_lymphocyte`).
- *(object-based models only)* `center_x`, `center_y` — cell centre in
  level-0 pixels.
- *(when `region_inference_dir` is supplied)* `region_minx`, `region_miny`,
  `region_width`, `region_height`, `region_prob_<class>` — enclosing region
  patch and its class probabilities. Argmax of `region_prob_*` gives a
  per-cell region label (e.g. tumor vs non-tumor).

### `ncomp-outputs-csv/<slide>.csv` (per-cell composition)

- `center_x`, `center_y` — cell centre.
- `cell_type` — argmax over `prob_*` from the model output.
- `neighborhood_size` — number of k-hop neighbours (excluding self).
- `neighborhood_<type>_count` and `neighborhood_<type>_prop` — per-class
  counts and proportions across the k-hop neighbourhood. `_prop` is `NaN`
  when `neighborhood_size == 0`.

### `export-csv/<slide>.csv`

Left-join of `model-outputs-csv/` with `ncomp-outputs-csv/` on
`(center_x, center_y)`. Same columns as the two sources combined.

### `patches/<slide>.h5` (HDF5)

- `/coords` — `(N, 2) int32`, top-left `[x, y]` of each patch at level 0.
  Attributes: `patch_size`, `patch_level`, `patch_spacing_um_px`,
  optional `tile_dim`.
- `/slide.attrs` — `slide_path`, `slide_mpp`, `slide_width`, `slide_height`.
- `/images` — `(N, patch_size, patch_size, 3) uint8`, only when the run
  used `cache_image_patches=True`.
- `/polygons/{coords, offsets}` — ragged polygon vertices (when polygons
  were supplied).

### `graphs/<slide>.h5` (HDF5, produced by `ncomp`)

- `cell_centers` — `(N, 2) int32`.
- `simplices` — `(M, 3) int32` Delaunay triangle vertex indices.
- `edges_source`, `edges_target`, `edges_length` — unpruned undirected
  edges (length in pixels).
- `file.attrs` — `num_cells`, `mpp`, `centers_hash` (SHA-256 of
  `cell_centers.tobytes()` for cache invalidation).

Edges are stored unpruned; pruning to `ncomp_max_neighbor_distance` happens
at read time.

### `export-geojson/<slide>.geojson`

Standard GeoJSON `FeatureCollection`. Each feature:

```json
{
  "type": "Feature",
  "id": "<uuid4>",
  "geometry": {"type": "Polygon", "coordinates": [[[x1,y1], ...]]},
  "properties": {
    "isLocked": true,
    "objectType": "detection",       // or "tile" / "annotation"
    "classification": {"name": "prob_<winner>", "color": [R,G,B]},
    "measurements": {"prob_tumor": 0.92, "neighborhood_tumor_prop": 0.7, ...}
  }
}
```

`measurements` includes every numeric column except the geometry columns
(`minx`, `miny`, `width`, `height`, `center_x`, `center_y`).

### `export-omecsv/<slide>.ome.csv.gz`

Gzip-compressed CSV with columns:

- `object` — row index.
- `secondary_object` — same as `object`.
- `polygon` — WKT polygon string.
- `objectType` — `"detection"` / `"tile"` / `"annotation"` (chosen via
  `object_type` argument to `wsinsight_export`).
- `classification` — argmax class name with the `prob_` prefix stripped.
- All numeric non-geometry columns. `NaN` is written as the literal
  string `"NaN"`.

### Reading results from agent code

```python
import pandas as pd
df = pd.read_csv("results/model-outputs-csv/SLIDE.csv")
print(df.columns.tolist())   # incl. prob_<class> for every model class
```
