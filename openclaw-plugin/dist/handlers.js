// ClawSight tool handlers — engine-agnostic.
//
// Five handlers are generated per engine from the registry in `engines.ts`:
//
//   <engine>_start        start the Docker container + MCP server
//   <engine>_stop         stop and remove it
//   <engine>_status       container / connection health
//   <engine>_list_tools   live tool catalog (from the running container)
//   <engine>_call         invoke any tool the container exposes
//
// Nothing about a specific engine is hard-coded here, so a new backend
// only needs a row in ENGINES.
//
// Mirror of `hermes-plugin/tools.py`.
import { existsSync } from "node:fs";
import { docker, dockerRunning } from "./docker.js";
import { ENGINES, state } from "./engines.js";
// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function err(msg) {
    return `[ERROR] ${msg}`;
}
// `process.getuid` / `process.getgid` exist on POSIX but not on Windows;
// the @types/node declarations are also conditionally present. Guard with a
// narrowing cast so the file compiles across host types.
const posixIds = process;
function hostUid() {
    return typeof posixIds.getuid === "function" ? posixIds.getuid() : 1000;
}
function hostGid() {
    return typeof posixIds.getgid === "function" ? posixIds.getgid() : 1000;
}
/** Parse the optional `arguments` sub-object from a tool invocation. */
function parseArguments(params) {
    const raw = params["arguments"];
    if (raw === undefined || raw === null)
        return { ok: true, value: {} };
    if (typeof raw === "string") {
        try {
            const parsed = JSON.parse(raw);
            if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
                return { ok: false, err: "'arguments' must be a JSON object" };
            }
            return { ok: true, value: parsed };
        }
        catch {
            return {
                ok: false,
                err: "'arguments' must be a JSON object, not a plain string",
            };
        }
    }
    if (typeof raw !== "object" || Array.isArray(raw)) {
        return { ok: false, err: "'arguments' must be a JSON object" };
    }
    return { ok: true, value: raw };
}
async function refreshTools(st) {
    try {
        const client = st.client();
        const tools = (await client.listTools());
        st.tools = tools;
        return null;
    }
    catch (e) {
        st.reset();
        return String(e);
    }
}
function formatTools(engine, tools) {
    if (!tools.length)
        return "(no tools reported)";
    const rows = [`${engine.name} exposes ${tools.length} tools:`];
    const sorted = [...tools].sort((a, b) => String(a.name ?? "").localeCompare(String(b.name ?? "")));
    for (const t of sorted) {
        const desc = String(t.description ?? "").trim().split("\n")[0] ?? "";
        rows.push(`  ${String(t.name ?? "?").padEnd(22)} ${desc.slice(0, 88)}`);
    }
    rows.push(`\nCall any of them with ${engine.name}_call(` +
        'tool="<name>", arguments={...}).');
    return rows.join("\n");
}
// ---------------------------------------------------------------------------
// handler factories — one per verb
// ---------------------------------------------------------------------------
function makeStart(engine) {
    return async (params) => {
        const st = state(engine.name);
        const dataDir = String(params["data_dir"] ?? "").trim();
        if (!dataDir) {
            return err("'data_dir' is required (host directory mounted at /workspace)");
        }
        // We can't easily stat in pure-JS without fs/promises, so try a
        // cheap synchronous existence check. Note: the host may be a Windows
        // path; Node accepts both styles.
        try {
            if (!existsSync(dataDir)) {
                return err(`data_dir does not exist: ${dataDir}`);
            }
        }
        catch (e) {
            return err(`cannot access data_dir: ${String(e)}`);
        }
        const port = params["port"] !== undefined ? Number(params["port"]) : st.port;
        if (!Number.isFinite(port))
            return err("'port' must be an integer");
        const cname = String(params["container_name"] ?? st.container).trim() || st.container;
        const gpuIds = String(params["gpu_ids"] ?? "").trim();
        const maxConc = params["max_concurrent"] !== undefined
            ? Number(params["max_concurrent"])
            : undefined;
        const experimental = params["experimental"] !== undefined
            ? Boolean(params["experimental"])
            : engine.experimental;
        await docker(["stop", cname], 30_000);
        await docker(["rm", cname], 30_000);
        let cmd = `${engine.mcpBin} --http 0.0.0.0:${port}`;
        if (experimental && engine.experimental)
            cmd += " --experimental";
        if (maxConc !== undefined && Number.isFinite(maxConc)) {
            cmd += ` --max-concurrent ${Math.trunc(maxConc)}`;
        }
        const argv = [
            "run",
            "-d",
            "--name",
            cname,
        ];
        if (engine.gpu) {
            argv.push("--gpus", gpuIds ? `device=${gpuIds}` : "all");
        }
        argv.push("--shm-size=32g", "--init", "-e", `HOST_UID=${hostUid()}`, "-e", `HOST_GID=${hostGid()}`, "-p", `${port}:${port}`, "-v", `${dataDir}:/workspace`, st.image, "bash", "-lc", cmd);
        const run = await docker(argv, 180_000);
        if (run.code !== 0) {
            return err(`docker run failed (exit ${run.code}):\n${run.out}`);
        }
        st.port = port;
        st.container = cname;
        st.mcpUrl = `http://127.0.0.1:${port}/mcp`;
        st.timeoutS = st.timeoutS; // unchanged
        st.reset();
        const lines = [
            `Started '${engine.name}' container ${cname} (${run.out.slice(0, 12)})`,
            `  image   : ${st.image}`,
            `  mcp_url : ${st.mcpUrl}`,
            `  data_dir: ${dataDir} -> /workspace`,
        ];
        const toolsErr = await refreshTools(st);
        if (toolsErr) {
            lines.push(`  tools   : not discovered yet (${toolsErr.split("\n")[0]?.slice(0, 80) ?? toolsErr}); ` +
                `the server may still be starting — retry ${engine.name}_list_tools.`);
        }
        else {
            lines.push(`  tools   : ${st.tools.length} discovered`);
            lines.push("");
            lines.push(formatTools(engine, st.tools));
        }
        return lines.join("\n");
    };
}
function makeStop(engine) {
    return async (params) => {
        const st = state(engine.name);
        const cname = String(params["container_name"] ?? st.container).trim() || st.container;
        const r1 = await docker(["stop", cname], 60_000);
        const r2 = await docker(["rm", cname], 30_000);
        st.reset();
        st.tools = [];
        if (r1.code !== 0 && r2.code !== 0) {
            return `No running container named ${cname} (nothing to stop).`;
        }
        return `Stopped and removed '${engine.name}' container ${cname}.`;
    };
}
function makeStatus(engine) {
    return async (_params) => {
        const st = state(engine.name);
        const running = await dockerRunning(st.container);
        const lines = [
            `engine    : ${engine.name}`,
            `image     : ${st.image}`,
            `container : ${st.container} (${running ? "running" : "not running"})`,
            `mcp_url   : ${st.mcpUrl}`,
            `gpu       : ${engine.gpu ? "yes" : "no (CPU only)"}`,
        ];
        if (!running) {
            lines.push(`\nStart it with ${engine.name}_start(data_dir=...).`);
            return lines.join("\n");
        }
        const refreshErr = await refreshTools(st);
        if (refreshErr) {
            lines.push(`tools     : unreachable (${refreshErr.split("\n")[0]?.slice(0, 80) ?? refreshErr})`);
        }
        else {
            lines.push(`tools     : ${st.tools.length} available`);
        }
        return lines.join("\n");
    };
}
function makeListTools(engine) {
    return async (params) => {
        const st = state(engine.name);
        const detail = String(params["tool"] ?? "").trim();
        const refreshErr = await refreshTools(st);
        if (refreshErr !== null) {
            return err(`Cannot reach the ${engine.name} MCP server at ${st.mcpUrl}.\n` +
                `Start it with ${engine.name}_start(data_dir=...).\n` +
                `Detail: ${refreshErr}`);
        }
        if (detail) {
            const hit = st.tools.find((t) => String(t.name ?? "") === detail);
            if (hit)
                return JSON.stringify(hit, null, 2);
            return err(`${engine.name} has no tool named '${detail}'`);
        }
        return formatTools(engine, st.tools);
    };
}
function makeCall(engine) {
    return async (params) => {
        const st = state(engine.name);
        const tool = String(params["tool"] ?? "").trim();
        if (!tool) {
            return err(`'tool' is required. Run ${engine.name}_list_tools() to see what ` +
                `this engine exposes.`);
        }
        const parsed = parseArguments(params);
        if (!parsed.ok)
            return err(parsed.err);
        try {
            return await st.client().callTool(tool, parsed.value);
        }
        catch (e) {
            st.reset();
            const low = String(e).toLowerCase();
            if (low.includes("connect") ||
                low.includes("connection") ||
                low.includes("refused") ||
                low.includes("timeout")) {
                return err(`Cannot reach the ${engine.name} MCP server at ${st.mcpUrl}.\n` +
                    `Start it with ${engine.name}_start(data_dir=...).`);
            }
            return err(`${engine.name}.${tool} failed: ${String(e)}`);
        }
    };
}
const FACTORIES = {
    start: makeStart,
    stop: makeStop,
    status: makeStatus,
    list_tools: makeListTools,
    call: makeCall,
};
const VERBS = ["start", "stop", "status", "list_tools", "call"];
/**
 * `{tool_name: handler}` for every engine × verb combination.
 */
export function buildHandlers() {
    const out = {};
    for (const engine of ENGINES) {
        for (const verb of VERBS) {
            const fn = FACTORIES[verb](engine);
            Object.defineProperty(fn, "name", { value: `${engine.name}_${verb}` });
            out[`${engine.name}_${verb}`] = fn;
        }
    }
    return out;
}
