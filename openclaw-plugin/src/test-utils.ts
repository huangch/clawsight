// Shared helpers for the ClawSight OpenClaw-plugin vitest suite.
//
// The 25 `<engine>_<verb>` tools (5 engines × 5 verbs) are registered via
// `api.registerTool(...)` during the `register` body of the
// `definePluginEntry({...})` default export. We don't have a real OpenClaw
// host in the test process, so these helpers stand up a minimal fake `api`
// that captures every tool, then drive `tool.execute(...)` from the test body.
//
// Network is stubbed by spying on the docker spawn functions; the spy is
// installed in `installDockerStub` and restored by `restoreAll()` so test
// ordering cannot leak state. We mirror the exact shape of clawpyter's
// `clawpyter/openclaw-plugin/src/test-utils.ts`.

import { vi } from "vitest";

import pluginEntry from "./index.js";

import type {
  OpenClawPluginApi,
  PluginConfigSchema,
  DefinedPluginEntry,
} from "openclaw/plugin-sdk/plugin-entry";

export interface CapturedTool {
  name: string;
  description: string;
  parameters: unknown;
  execute: (id: string, params: Record<string, unknown>) => Promise<unknown>;
}

export interface Harness {
  entry: DefinedPluginEntry;
  api: OpenClawPluginApi;
  tools: Map<string, CapturedTool>;
  /** Convenience lookup; throws if a test calls an unregistered name. */
  invoke<T = unknown>(
    name: string,
    params?: Record<string, unknown>,
  ): Promise<T>;
  /** Reset captured tools between tests. */
  reset(): Promise<void>;
}

/** Build a stub OpenClawPluginApi and run the plugin's `register(api)`. */
export async function buildHarness(
  pluginConfig: Record<string, unknown> = {},
): Promise<Harness> {
  const tools = new Map<string, CapturedTool>();

  const api = {
    id: "clawsight-test",
    name: "ClawSightTest",
    version: "0.0.0-test",
    config: pluginConfig,
    pluginConfig,
    rootDir: "/tmp/clawsight-test",
    logger: {
      info: () => undefined,
      warn: () => undefined,
      error: () => undefined,
      debug: () => undefined,
    },
  } as unknown as OpenClawPluginApi;

  // Patch registerTool onto the api. ClawSight's register is `(apiIn: unknown) => void`,
  // so we duck-type registerTool onto the api before calling the entry.
  (api as { registerTool?: unknown }).registerTool = (
    tool: { name: string; description: string; parameters: unknown; execute: CapturedTool["execute"] },
    _opts: { name?: string; names?: string[]; optional?: boolean } | undefined,
  ) => {
    tools.set(tool.name, {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters,
      execute: tool.execute,
    });
  };

  // Resolve the entry. clawpyter style exposes the default export as the
  // entry; our plugin follows the same pattern. Default import via `import
  // pluginEntry from "./index.js"` may surface either the entry object
  // (vite-node ESM interop) or the entry's `.default` property (CJS
  // interop in some bundler configs). Accept both.
  const pe = pluginEntry as unknown as DefinedPluginEntry | { default?: DefinedPluginEntry };
  const entry: DefinedPluginEntry | undefined =
    typeof (pe as DefinedPluginEntry).register === "function"
      ? (pe as DefinedPluginEntry)
      : (pe as { default?: DefinedPluginEntry }).default;
  if (!entry || typeof entry.register !== "function") {
    throw new Error("clawsight plugin: default export is not a definePluginEntry result");
  }
  await entry.register(api);

  return {
    entry,
    api,
    tools,
    async invoke<T = unknown>(
      name: string,
      params: Record<string, unknown> = {},
    ): Promise<T> {
      const tool = tools.get(name);
      if (!tool) {
        throw new Error(`tool not registered: ${name}`);
      }
      return (await tool.execute(name, params)) as T;
    },
    async reset(): Promise<void> {
      tools.clear();
    },
  };
}

export const SCHEMA_TYPE: PluginConfigSchema | undefined =
  (pluginEntry as unknown as { default?: DefinedPluginEntry })
    ?.default?.configSchema;
