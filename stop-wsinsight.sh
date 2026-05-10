#!/usr/bin/env bash
# stop-wsinsight.sh — Stop and remove the WSInsight MCP Docker container.
#
# Usage:
#   ./stop-wsinsight.sh [container_name]
#
# Default container name: clawsight-mcp
set -euo pipefail

CONTAINER="${1:-clawsight-mcp}"

echo "Stopping container '$CONTAINER'..."
docker stop "$CONTAINER" 2>/dev/null && docker rm "$CONTAINER" 2>/dev/null || {
  echo "Container '$CONTAINER' was not running (or already removed)."
  exit 0
}
echo "Done."
