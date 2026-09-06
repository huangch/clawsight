#!/bin/sh
# build4openclaw.sh — Build and install the ClawSight OpenClaw plugin.
cd "$(dirname "$0")/openclaw-plugin"
npm install
# Type-check + run vitest before installing. Catches SDK drift (we have
# test-stub for the runtime, but tsc still validates the real surface
# against our ambient declaration).
npx tsc -p tsconfig.json --noEmit
npx vitest run
npm run build
openclaw plugins uninstall clawsight 2>/dev/null || true
openclaw plugins install -l "$(pwd)"
