// JSON schemas for ClawSight tools, generated from the engine registry.
// One template per verb; the engine's metadata (GPU, experimental, summary)
// fills in the wording, so no schema is hand-written.
//
// Mirror of `hermes-plugin/schemas.py`.
import { Type } from "@sinclair/typebox";
import { ENGINES } from "./engines.js";
// ---------------------------------------------------------------------------
// Per-verb templates
// ---------------------------------------------------------------------------
function startSchema(e) {
    const properties = {
        data_dir: {
            type: "string",
            description: "Host directory mounted at /workspace inside the container. " +
                "All inputs and outputs live under it.",
        },
        port: {
            type: "integer",
            description: `Host/container port for the MCP server (default ${e.portDefault}).`,
        },
        container_name: {
            type: "string",
            description: `Container name (default clawsight-${e.name}).`,
        },
        max_concurrent: {
            type: "integer",
            description: "Maximum concurrent jobs the server will run.",
        },
    };
    if (e.gpu) {
        properties.gpu_ids = {
            type: "string",
            description: 'Comma-separated GPU ids to expose, e.g. "0,1". Empty or ' +
                "omitted exposes all GPUs.",
        };
    }
    if (e.experimental) {
        properties.experimental = {
            type: "boolean",
            description: "Expose experimental sub-commands as tools " +
                `(default ${String(e.experimental).toLowerCase()}).`,
        };
    }
    return {
        type: "object",
        description: `Start the ${e.name} Docker container and its MCP server, then ` +
            `discover the tools it exposes. ${e.summary}`,
        properties,
        required: ["data_dir"],
    };
}
function stopSchema(e) {
    return {
        type: "object",
        description: `Stop and remove the ${e.name} container.`,
        properties: {
            container_name: {
                type: "string",
                description: `Container name (default clawsight-${e.name}).`,
            },
        },
        required: [],
    };
}
function statusSchema(e) {
    return {
        type: "object",
        description: `Report whether the ${e.name} container is running, its MCP URL, ` +
            "and how many tools it currently exposes.",
        properties: {},
        required: [],
    };
}
function listToolsSchema(e) {
    return {
        type: "object",
        description: `List the tools the running ${e.name} server exposes, with a short ` +
            "description of each. Pass 'tool' to get one tool's full input " +
            `schema. Requires ${e.name}_start to have been run.`,
        properties: {
            tool: {
                type: "string",
                description: "Return the full JSON input schema for this one tool instead " +
                    "of the summary list.",
            },
        },
        required: [],
    };
}
function callSchema(e) {
    return {
        type: "object",
        description: `Invoke any tool exposed by the running ${e.name} server. Use ` +
            `${e.name}_list_tools first to discover tool names and their ` +
            "parameters. Long-running tools return a job_id — poll it by " +
            'calling this tool again with tool="job_status".',
        properties: {
            tool: {
                type: "string",
                description: `Tool name as reported by ${e.name}_list_tools.`,
            },
            arguments: {
                type: "object",
                description: "Arguments object for that tool, matching its input schema.",
            },
        },
        required: ["tool"],
    };
}
const TEMPLATES = {
    start: startSchema,
    stop: stopSchema,
    status: statusSchema,
    list_tools: listToolsSchema,
    call: callSchema,
};
const VERBS = Object.keys(TEMPLATES);
/**
 * Map our internal JSON Schema object into TypeBox's `Type.Object({...})`.
 * Used by `index.ts` to compose the `parameters` slot of `registerTool`.
 *
 * The TypeBox conversion is best-effort: it produces `Type.Object({...})`
 * with `Type.String()`, `Type.Number()`, `Type.Boolean()`, and `Type.Object({...})`
 * properties. Unknown property kinds fall back to `Type.String()`. The
 * OpenClaw SDK accepts the resulting `TSchema` as the `parameters` slot.
 */
export function jsonSchemaToTypeBox(schema) {
    const props = {};
    if (schema.properties) {
        for (const [key, value] of Object.entries(schema.properties)) {
            const t = (value.type ?? "string").toLowerCase();
            switch (t) {
                case "integer":
                case "number":
                    props[key] = Type.Number();
                    break;
                case "boolean":
                    props[key] = Type.Boolean();
                    break;
                case "object":
                    props[key] = Type.Object({});
                    break;
                default:
                    props[key] = Type.String();
            }
        }
    }
    const requiredKeys = new Set(schema.required ?? []);
    for (const key of requiredKeys) {
        if (props[key] === undefined)
            props[key] = Type.String();
    }
    if (Object.keys(props).length === 0)
        return Type.Object({});
    // Cast through `unknown` so we can attach the JSON-Schema `required` array
    // (TypeBox encodes this on its Object literal at runtime; the type system
    // treats the property metadata as part of the schema).
    return Type.Object(props, {
        additionalProperties: schema.additionalProperties ?? false,
    });
}
/**
 * `{tool_name: tool_definition}` for every engine × verb combination.
 */
export function buildTools() {
    const out = {};
    for (const engine of ENGINES) {
        for (const verb of VERBS) {
            const inner = TEMPLATES[verb](engine);
            out[`${engine.name}_${verb}`] = {
                name: `${engine.name}_${verb}`,
                description: inner.description ?? "",
                parameters: inner,
            };
        }
    }
    return out;
}
