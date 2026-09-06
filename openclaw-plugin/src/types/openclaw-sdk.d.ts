/**
 * Ambient declarations for OpenClaw plugin SDK subpaths.
 *
 * ClawSight is an external plugin — when the OpenClaw runtime loads it,
 * the host's package exports make `openclaw/plugin-sdk/*` resolve at
 * runtime through the `openclaw` host package's `exports` map. TypeScript
 * can't see those exports from inside an external plugin's `tsc` run
 * (we don't ship `@openclaw/plugin-sdk` as a direct dep), so we declare
 * the structural types we use here and let `skipLibCheck: true` quietly
 * tolerate any surface mismatch.
 *
 * If/when the OpenClaw project ships a public external SDK package on
 * npm, replace this file with `npm install @openclaw/plugin-sdk` and
 * delete this stub.
 */
declare module "openclaw/plugin-sdk/plugin-entry" {
  import type { JSONSchema7 } from "json-schema";

  export type AnyAgentTool = {
    label?: string;
    name: string;
    description: string;
    parameters: JSONSchema7 | unknown;
    execute: (
      _id: string,
      params: Record<string, unknown>,
    ) => unknown | Promise<unknown>;
    resultContentSource?: "network" | "local";
    [key: string]: unknown;
  };

  export type OpenClawPluginToolOptions = {
    name?: string;
    names?: string[];
    optional?: boolean;
  };

  export type OpenClawPluginToolFactory = (
    api: unknown,
  ) => AnyAgentTool | Promise<AnyAgentTool>;

  export type PluginLifecycleContext = {
    registerCleanup: (fn: () => void | Promise<void>) => void;
  };

  export type PluginConfigSchema =
    | JSONSchema7
    | { type: "object"; properties?: Record<string, unknown>; additionalProperties?: boolean }
    | Record<string, unknown>;

  /**
   * Trimmed subset of `OpenClawPluginApi` that ClawSight actually uses.
   * Full upstream interface is much larger — see OpenClaw 2026.9.x
   * `src/plugins/plugin-api.types.ts`. We declare only the surface we
   * touch, and rely on index-signature widening for the rest.
   */
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
      tool: AnyAgentTool | OpenClawPluginToolFactory,
      opts?: OpenClawPluginToolOptions,
    ) => void;
    registerLifecycle?: (hooks: {
      onLoad?: (ctx: PluginLifecycleContext) => void | Promise<void>;
      onUnload?: (ctx: PluginLifecycleContext) => void | Promise<void>;
    }) => void;
    [key: string]: unknown;
  }

  /**
   * Options accepted by `definePluginEntry`. Mirrors
   * `DefinePluginEntryOptions` in `src/plugin-sdk/plugin-entry.ts` of
   * upstream OpenClaw 2026.9.x.
   */
  export type DefinePluginEntryOptions = {
    id: string;
    name: string;
    description?: string;
    version?: string;
    kind?: string | string[];
    configSchema?: PluginConfigSchema;
    register?: (api: OpenClawPluginApi) => void | Promise<void>;
    reload?: unknown;
    nodeHostCommands?: unknown[];
    securityAuditCollectors?: unknown[];
    [key: string]: unknown;
  };

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
    options: DefinePluginEntryOptions,
  ): DefinedPluginEntry;
}
