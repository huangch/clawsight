import { Type } from "@sinclair/typebox";
import { WsInsightMcpClient } from "./wsinsight-mcp-client.js";
const DEFAULT_PORT = 8765;
const DEFAULT_CNAME = "clawsight-mcp";
export default function register(api) {
    const cfg = api?.pluginConfig ?? {};
    let mcpUrl = cfg.mcpUrl ?? `http://127.0.0.1:${DEFAULT_PORT}/mcp`;
    let timeoutMs = cfg.timeoutMs ?? 300_000;
    let cname = cfg.containerName ?? DEFAULT_CNAME;
    let client = new WsInsightMcpClient(mcpUrl, timeoutMs);
    const a = api;
    const OPT = { optional: true };
    function rebuildClient(newUrl) {
        if (newUrl)
            mcpUrl = newUrl;
        client = new WsInsightMcpClient(mcpUrl, timeoutMs);
    }
    async function proxy(toolName, args) {
        try {
            const text = await client.callTool(toolName, args);
            return WsInsightMcpClient.asText(toolName, text);
        }
        catch (err) {
            client.reset();
            const msg = String(err).toLowerCase();
            const connErr = msg.includes("connect") ||
                msg.includes("refused") ||
                msg.includes("timeout");
            const body = connErr
                ? `[ERROR] Cannot reach WSInsight MCP server at ${mcpUrl}.\n` +
                    "Ensure the Docker container is running (use start-wsinsight.sh) " +
                    "and call wsinsight_connect to verify."
                : `[ERROR] MCP call '${toolName}' failed: ${err}`;
            return WsInsightMcpClient.asText(toolName, body);
        }
    }
    // ── wsinsight_server_info ─────────────────────────────────────────────────
    a.registerTool({
        name: "wsinsight_server_info",
        description: "Show the current ClawSight configuration: MCP endpoint URL, " +
            "container name, request timeout, and whether a session is active. " +
            "Use this to verify the plugin state before running pipelines.",
        parameters: Type.Object({}),
        async execute(_id) {
            console.log("Tool execution:", { name: "wsinsight_server_info", _id });
            const info = {
                mcp_url: mcpUrl,
                container_name: cname,
                timeout_ms: timeoutMs,
                session_active: client
                    .sessionId !== null,
            };
            return WsInsightMcpClient.asText("wsinsight_server_info", JSON.stringify(info, null, 2));
        },
    }, OPT);
    // ── wsinsight_connect ─────────────────────────────────────────────────────
    a.registerTool({
        name: "wsinsight_connect",
        description: "Connect to a running WSInsight MCP server and verify it is reachable. " +
            "Performs the MCP initialize handshake and returns server name, version, " +
            "and protocol version on success. " +
            "Optionally override the MCP URL or timeout.",
        parameters: Type.Object({
            mcp_url: Type.Optional(Type.String({
                description: "MCP endpoint URL (e.g. http://127.0.0.1:8765/mcp). " +
                    "Overrides the current URL for this and all future calls.",
            })),
            timeout_ms: Type.Optional(Type.Number({ description: "Request timeout in ms (default: 300000)." })),
        }),
        async execute(_id, params) {
            console.log("Tool execution:", { name: "wsinsight_connect", params, _id });
            if (typeof params.mcp_url === "string") {
                rebuildClient(params.mcp_url);
            }
            if (typeof params.timeout_ms === "number") {
                timeoutMs = params.timeout_ms;
                rebuildClient();
            }
            try {
                const init = await client.initialize();
                const result = init["result"] ?? {};
                const si = result["serverInfo"] ?? {};
                const pv = result["protocolVersion"] ?? "?";
                const body = [
                    `URL:      ${mcpUrl}`,
                    `Server:   ${si["name"] ?? "?"} v${si["version"] ?? "?"}`,
                    `Protocol: ${pv}`,
                ].join("\n");
                return WsInsightMcpClient.asText("Connected", body);
            }
            catch (err) {
                client.reset();
                return WsInsightMcpClient.asText("Connection failed", `[ERROR] ${err}\nURL: ${mcpUrl}\nIs the container running?`);
            }
        },
    }, OPT);
    // ── wsinsight_list_tools ──────────────────────────────────────────────────
    a.registerTool({
        name: "wsinsight_list_tools",
        description: "List all tools available on the WSInsight MCP server with their " +
            "parameter names, types, and required fields. " +
            "Always call this before pipeline tools to know what to put in 'arguments'.",
        parameters: Type.Object({}),
        async execute(_id) {
            console.log("Tool execution:", { name: "wsinsight_list_tools", _id });
            try {
                const tools = await client.listTools();
                if (!tools.length) {
                    return WsInsightMcpClient.asText("wsinsight_list_tools", "No tools found. Is the server running? Call wsinsight_connect first.");
                }
                const lines = [`WSInsight MCP tools (${tools.length}):\n`];
                for (const t of tools) {
                    const name = String(t["name"] ?? "");
                    const desc = String(t["description"] ?? "").split("\n")[0].slice(0, 110);
                    const schema = t["inputSchema"] ?? {};
                    const props = Object.keys(schema["properties"] ?? {});
                    const req = new Set(schema["required"] ?? []);
                    const ps = props.map((k) => (req.has(k) ? `${k}*` : k)).join(", ");
                    lines.push(`  ${name}`, `    ${desc}`);
                    if (ps)
                        lines.push(`    params: ${ps}  (* = required)`);
                    lines.push("");
                }
                return WsInsightMcpClient.asText("wsinsight_list_tools", lines.join("\n"));
            }
            catch (err) {
                client.reset();
                return WsInsightMcpClient.asText("wsinsight_list_tools", `[ERROR] ${err}`);
            }
        },
    }, OPT);
    // ── pipeline tools ─────────────────────────────────────────────────────────
    // Each pipeline tool forwards the 'arguments' object to the MCP server tool
    // of the same name. The agent discovers exact params via wsinsight_list_tools.
    const ArgsParam = Type.Optional(Type.Object({}, {
        additionalProperties: true,
        description: "WSInsight command arguments as a JSON object. " +
            "Call wsinsight_list_tools to discover parameter names and types.",
    }));
    const pipelineTools = [
        {
            toolName: "run",
            desc: "Run the full WSInsight end-to-end pipeline on a WSI: " +
                "tissue segmentation → patch extraction → GPU model inference → " +
                "neighborhood composition → export. " +
                "Returns job_id immediately; poll wsinsight_job_status for progress.",
            isAsync: true,
        },
        {
            toolName: "patch",
            desc: "Segment tissue and extract patches from a WSI into an HDF5 cache. " +
                "Returns job_id immediately.",
            isAsync: true,
        },
        {
            toolName: "infer",
            desc: "Run GPU model inference on pre-extracted patches. " +
                "Returns job_id immediately.",
            isAsync: true,
        },
        {
            toolName: "ncomp",
            desc: "Compute per-cell neighborhood composition on a Delaunay graph. " +
                "Returns job_id immediately.",
            isAsync: true,
        },
        {
            toolName: "export",
            desc: "Export inference or composition results to GeoJSON or OME-CSV. " +
                "Runs synchronously.",
            isAsync: false,
        },
        {
            toolName: "reg",
            desc: "Register (spatially align) two WSI regions. Runs synchronously.",
            isAsync: false,
        },
    ];
    for (const { toolName, desc, isAsync } of pipelineTools) {
        const tn = toolName; // capture for closure
        a.registerTool({
            name: `wsinsight_${tn}`,
            description: `${desc} ` +
                "File paths in 'arguments' must be relative to /workspace (= data_dir). " +
                "Call wsinsight_list_tools to discover exact parameter names." +
                (isAsync
                    ? " Poll status with wsinsight_job_status."
                    : ""),
            parameters: Type.Object({ arguments: ArgsParam }),
            async execute(_id, params) {
                console.log("Tool execution:", { name: `wsinsight_${tn}`, params, _id });
                const args = params.arguments ?? {};
                return proxy(tn, args);
            },
        }, OPT);
    }
    // ── job management ─────────────────────────────────────────────────────────
    a.registerTool({
        name: "wsinsight_job_status",
        description: "Poll the status of a background WSInsight job. " +
            "Returns status (pending / running / done / error / cancelled), " +
            "elapsed time, and a progress snippet. " +
            "Call this repeatedly after a pipeline tool until status is 'done' or 'error'.",
        parameters: Type.Object({
            job_id: Type.String({
                description: "Job ID returned by a pipeline tool.",
            }),
        }),
        async execute(_id, params) {
            console.log("Tool execution:", { name: "wsinsight_job_status", params, _id });
            return proxy("job_status", { job_id: params.job_id });
        },
    }, OPT);
    a.registerTool({
        name: "wsinsight_job_logs",
        description: "Retrieve the last N stdout/stderr log lines from a background job. " +
            "Default: 50 lines.",
        parameters: Type.Object({
            job_id: Type.String({ description: "Job ID." }),
            tail: Type.Optional(Type.Number({
                description: "Number of log lines to return (default: 50).",
                minimum: 1,
                maximum: 4000,
            })),
        }),
        async execute(_id, params) {
            console.log("Tool execution:", { name: "wsinsight_job_logs", params, _id });
            const args = { job_id: params.job_id };
            if (typeof params.tail === "number")
                args["tail"] = params.tail;
            return proxy("job_logs", args);
        },
    }, OPT);
    a.registerTool({
        name: "wsinsight_cancel_job",
        description: "Cancel a running or pending WSInsight background job by job_id.",
        parameters: Type.Object({
            job_id: Type.String({ description: "Job ID to cancel." }),
        }),
        async execute(_id, params) {
            console.log("Tool execution:", { name: "wsinsight_cancel_job", params, _id });
            return proxy("cancel_job", { job_id: params.job_id });
        },
    }, OPT);
    a.registerTool({
        name: "wsinsight_list_jobs",
        description: "List all WSInsight background jobs (running, pending, done, error, cancelled) " +
            "with job_id, command, status, and elapsed time.",
        parameters: Type.Object({}),
        async execute(_id) {
            console.log("Tool execution:", { name: "wsinsight_list_jobs", _id });
            return proxy("list_jobs", {});
        },
    }, OPT);
}
