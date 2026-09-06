// ClawSight OpenClaw plugin — engine-agnostic.
//
// Registers one tool per (engine × verb) pair from ENGINES, where verbs are
// {start, stop, status, list_tools, call}. Defaults to 5 engines × 5 verbs
// = 25 tools. Adding a new engine means adding one row in `engines.ts`;
// nothing in this file needs to change.
//
// Mirror of `hermes-plugin/__init__.py :: register` + the
// `schemata.TEMPLATES` × `handlers.FACTORIES` cross-product in Hermes.
import { jsonSchemaToTypeBox, buildTools } from "./schemas.js";
import { buildHandlers } from "./handlers.js";
import { ENGINES } from "./engines.js";
import { definePluginEntry, } from "openclaw/plugin-sdk/plugin-entry";
const OPT = { optional: true };
function makeExecutor(handler) {
    return async (id, params) => {
        // Echo a single line to the agent's stderr so the OpenClaw log lane
        // captures tool activity — mirrors the legacy plugin's console.log line.
        // eslint-disable-next-line no-console
        console.log("Tool execution:", { _id: id, params });
        let body;
        try {
            body = await handler(params);
        }
        catch (e) {
            body = `[ERROR] Unhandled exception in handler: ${String(e)}`;
        }
        return {
            content: [{ type: "text", text: `## ${id}\n\n${body}` }],
        };
    };
}
export default definePluginEntry({
    id: "clawsight",
    name: "ClawSight",
    description: "Docker-orchestrated MCP control for the WSInsight family of " +
        "compute engines (wsinsight / sptxinsight / hplot / kurtorank / " +
        "wsitrain). Five tools per engine — start, stop, status, list_tools, " +
        "call — generated from the cross-product of the engine registry " +
        "and the verb templates; nothing is hard-coded per engine.",
    register(apiIn) {
        const api = (apiIn ?? {});
        const registerTool = api.registerTool;
        if (typeof registerTool !== "function") {
            // Defensive: the OpenClaw SDK contract isn't present. The plugin will be
            // disabled by the loader; we still want the module to import cleanly so
            // other plugins keep working.
            // eslint-disable-next-line no-console
            console.warn("ClawSight: api.registerTool is missing — plugin will not register tools");
            return;
        }
        const tools = buildTools();
        const handlers = buildHandlers();
        let registered = 0;
        for (const engine of ENGINES) {
            for (const verb of [
                "start",
                "stop",
                "status",
                "list_tools",
                "call",
            ]) {
                const toolName = `${engine.name}_${verb}`;
                const def = tools[toolName];
                const handler = handlers[toolName];
                if (!def || !handler)
                    continue;
                const toolDef = {
                    name: toolName,
                    description: def.description,
                    parameters: jsonSchemaToTypeBox(def.parameters),
                    execute: makeExecutor(handler),
                };
                registerTool(toolDef, OPT);
                registered++;
            }
        }
        // eslint-disable-next-line no-console
        console.log(`ClawSight: registered ${registered} tools`);
    },
});
