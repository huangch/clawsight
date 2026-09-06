// Test-only stub for the `openclaw/plugin-sdk/plugin-entry` module.
//
// At production runtime the OpenClaw host package provides a real
// `definePluginEntry` implementation. The TS ambient declaration at
// `src/types/openclaw-sdk.d.ts` carries the surface shape for the typecheck,
// but at test time there is NO OpenClaw host in the node_modules tree, so
// vitest's runtime resolution fails.
//
// This stub mirrors the minimum API our `index.ts` actually uses:
//   - `definePluginEntry({ id, name, description, register })`
//     returns the same object back so `pluginEntry.register(api)` keeps
//     working. No validation, no manifest building — the production runtime
//     does that. We don't need it for handler tests.
//
// Wired in via `vitest.config.ts > resolve.alias`.

export type AnyAgentTool = {
  label?: string;
  name: string;
  description: string;
  parameters: unknown;
  execute: (
    _id: string,
    params: Record<string, unknown>,
  ) => unknown | Promise<unknown>;
  resultContentSource?: "network" | "local";
  [key: string]: unknown;
};

export interface OpenClawPluginApi {
  id?: string;
  name?: string;
  version?: string;
  config: unknown;
  pluginConfig?: Record<string, unknown>;
  rootDir?: string;
  logger: {
    info: (msg: string) => void;
    warn: (msg: string) => void;
    error: (msg: string) => void;
    debug?: (msg: string) => void;
  };
  registerTool: (
    tool: AnyAgentTool,
    opts?: { name?: string; names?: string[]; optional?: boolean },
  ) => void;
  registerLifecycle?: (hooks: {
    onLoad?: (ctx: { registerCleanup: (fn: () => void) => void }) => void;
    onUnload?: (ctx: { registerCleanup: (fn: () => void) => void }) => void;
  }) => void;
  [key: string]: unknown;
}

export interface PluginConfigSchema {
  type?: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

export type DefinedPluginEntry = {
  id: string;
  name: string;
  description?: string;
  version?: string;
  configSchema?: PluginConfigSchema;
  register?: (api: OpenClawPluginApi) => void | Promise<void>;
  [key: string]: unknown;
};

export function definePluginEntry(
  options: DefinedPluginEntry,
): DefinedPluginEntry {
  return options;
}
