#!/usr/bin/env bash
# stop-sptxinsight.sh — Stop and remove the sptxinsight MCP Docker container.
#
# Usage:
#   ./stop-sptxinsight.sh [container_name]
#
# Default container name: clawsight-sptx-mcp
set -euo pipefail

CONTAINER="${1:-clawsight-sptx-mcp}"

echo "Stopping container '$CONTAINER'..."
docker stop "$CONTAINER" 2>/dev/null && docker rm "$CONTAINER" 2>/dev/null || {
  echo "Container '$CONTAINER' was not running (or already removed)."
  exit 0
}
echo "Done."
