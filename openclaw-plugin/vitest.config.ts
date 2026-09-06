// Vitest config for the ClawSight OpenClaw TypeScript suite.
//
// Mirrors clawpyter/openclaw-plugin/vitest.config.ts: tests live next to
// the modules they exercise (under src/**/*.test.ts), a test-stub resolves
// the bare `openclaw/plugin-sdk/plugin-entry` specifier at runtime because
// no OpenClaw host is installed in this plugin's node_modules, and we
// match the production `tsc --noEmit -p tsconfig.json` to keep the two
// paths in lockstep (5 engines × 5 verbs = 25 tools must register, and a
// green vitest must mean a green tsc for the same sources).

import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  test: {
    include: ["src/**/*.test.ts"],
    testTimeout: 5000,
  },
  resolve: {
    alias: {
      "openclaw/plugin-sdk/plugin-entry": `${here}/src/test-stub-openclaw-sdk.ts`,
    },
  },
});
