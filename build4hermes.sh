#!/usr/bin/env bash
# build4hermes.sh — Install the ClawSight Hermes plugin.
set -euo pipefail

PLUGIN_SRC="$(cd "$(dirname "$0")/hermes-plugin" && pwd)"
PLUGIN_DEST="$HOME/.hermes/plugins/clawsight"

echo "==> Installing Python dependencies (httpx)..."
pip install --quiet httpx

echo "==> Copying plugin to $PLUGIN_DEST..."
rm -rf "$PLUGIN_DEST"
cp -r "$PLUGIN_SRC" "$PLUGIN_DEST"

echo "==> Syntax check..."
for f in __init__ schemas tools; do
  python3 -m py_compile "$PLUGIN_DEST/${f}.py"
  echo "    OK: ${f}.py"
done

echo "==> Plugin installed."
hermes plugins list 2>/dev/null | grep -q clawsight \
  && echo "    clawsight is registered." \
  || echo "    (Restart hermes to pick up the new plugin.)"

echo ""
echo "Done. Optionally set in your environment:"
echo "  WSINSIGHT_MCP_URL        (default: http://127.0.0.1:8765/mcp)"
echo "  WSINSIGHT_MCP_TIMEOUT_MS (default: 300000)"
echo "  WSINSIGHT_CONTAINER_NAME (default: clawsight-mcp)"
