#!/bin/sh
# build4openclaw.sh — Build and install the ClawSight OpenClaw plugin.
cd "$(dirname "$0")/openclaw-plugin"
npm install
npm run build
openclaw plugins uninstall clawsight 2>/dev/null || true
openclaw plugins install -l "$(pwd)"
