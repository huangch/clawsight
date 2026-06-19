#!/usr/bin/env bash
# start-sptxinsight.sh — Pull and start the sptxinsight MCP Docker container.
#
# Runs as a SEPARATE container from wsinsight (different image, port and name)
# so the two MCP servers can run side by side.
#
# Usage:
#   ./start-sptxinsight.sh -d /path/to/data [options]
#
# Options:
#   -d <data_dir>        Required. Host path mounted as /workspace inside the container.
#   -g <gpu_ids>         Comma-separated GPU IDs (e.g. 0,1). Default: all GPUs.
#   -p <port>            MCP HTTP port (host and container). Default: 8766.
#   -n <name>            Docker container name. Default: clawsight-sptx-mcp.
#   -c <max_concurrent>  Max concurrent GPU jobs. Default: auto (= GPU count).
#   -e                   Enable experimental tools (hplot/hplot-finalize/cci).
#   -h                   Show this help and exit.
set -euo pipefail

IMAGE="huangchtw/sptxinsight:latest"
DATA_DIR=""
GPU_IDS=""
MCP_PORT=8766
CONTAINER_NAME="clawsight-sptx-mcp"
MAX_CONCURRENT=""
EXPERIMENTAL=false

while getopts ":d:g:p:n:c:eh" opt; do
  case $opt in
    d) DATA_DIR="$OPTARG"       ;;
    g) GPU_IDS="$OPTARG"        ;;
    p) MCP_PORT="$OPTARG"       ;;
    n) CONTAINER_NAME="$OPTARG" ;;
    c) MAX_CONCURRENT="$OPTARG" ;;
    e) EXPERIMENTAL=true        ;;
    h)
      sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0
      ;;
    :) echo "Error: option -$OPTARG requires an argument."; exit 1 ;;
    *) echo "Error: unknown option -$OPTARG. Use -h for help."; exit 1 ;;
  esac
done

if [ -z "$DATA_DIR" ]; then
  echo "Error: -d <data_dir> is required."
  echo "Run with -h for usage."
  exit 1
fi

if [ ! -d "$DATA_DIR" ]; then
  echo "Error: data directory '$DATA_DIR' does not exist."
  exit 1
fi

# Remove any existing container with the same name (ignore errors)
docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker rm   "$CONTAINER_NAME" >/dev/null 2>&1 || true

# Build GPU flag
if [ -n "$GPU_IDS" ]; then
  GPU_FLAG="device=${GPU_IDS}"
else
  GPU_FLAG="all"
fi

# Build the MCP server command
MCP_CMD="sptxinsight-mcp --http 0.0.0.0:${MCP_PORT}"
[ "$EXPERIMENTAL" = true ]   && MCP_CMD="${MCP_CMD} --experimental"
[ -n "$MAX_CONCURRENT" ]     && MCP_CMD="${MCP_CMD} --max-concurrent ${MAX_CONCURRENT}"

echo "Starting sptxinsight MCP server..."
echo "  Image:     $IMAGE"
echo "  Data:      $DATA_DIR → /workspace"
echo "  GPUs:      $GPU_FLAG"
echo "  Port:      $MCP_PORT"
echo "  Container: $CONTAINER_NAME"
[ "$EXPERIMENTAL" = true ] && echo "  Mode:      experimental tools enabled"

docker run -d \
  --name "$CONTAINER_NAME" \
  --gpus "$GPU_FLAG" \
  --shm-size=32g \
  --init \
  -p "${MCP_PORT}:${MCP_PORT}" \
  -v "${DATA_DIR}:/workspace" \
  "$IMAGE" bash -lc "$MCP_CMD"

echo ""
echo "MCP endpoint: http://127.0.0.1:${MCP_PORT}/mcp"
echo "Wait ~5 seconds, then call sptx_connect to verify."
