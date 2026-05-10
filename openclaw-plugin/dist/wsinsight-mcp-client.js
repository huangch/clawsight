// MCP 2025-03-26 Streamable HTTP client for the WSInsight MCP server.
//
// Protocol:
//   POST {url}
//     Content-Type: application/json
//     Accept: application/json, text/event-stream
//     Mcp-Session-Id: {sid}   (after initialization)
//
//   Response is either plain JSON or SSE (text/event-stream).
//   For SSE: split on newlines, last "data: {...}" line is the result.
//
// Docker lifecycle (start/stop) is managed externally via the shell scripts
// start-wsinsight.sh / stop-wsinsight.sh shipped alongside this plugin.
export class WsInsightMcpClient {
    mcpUrl;
    timeoutMs;
    sessionId = null;
    msgId = 0;
    constructor(mcpUrl, timeoutMs = 300_000) {
        this.mcpUrl = mcpUrl;
        this.timeoutMs = timeoutMs;
    }
    // -------------------------------------------------------------------------
    // Session helpers
    // -------------------------------------------------------------------------
    nextId() {
        return ++this.msgId;
    }
    reqHeaders() {
        const h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        };
        if (this.sessionId)
            h["Mcp-Session-Id"] = this.sessionId;
        return h;
    }
    notifyHeaders() {
        const h = { "Content-Type": "application/json" };
        if (this.sessionId)
            h["Mcp-Session-Id"] = this.sessionId;
        return h;
    }
    extractSession(resp) {
        const sid = resp.headers.get("mcp-session-id") ??
            resp.headers.get("Mcp-Session-Id");
        if (sid)
            this.sessionId = sid;
    }
    static parseSSE(text) {
        let last = null;
        for (const line of text.split("\n")) {
            if (line.startsWith("data: ")) {
                try {
                    last = JSON.parse(line.slice(6));
                }
                catch {
                    // skip malformed lines
                }
            }
        }
        return last;
    }
    // -------------------------------------------------------------------------
    // Low-level POST
    // -------------------------------------------------------------------------
    async post(payload) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            const resp = await fetch(this.mcpUrl, {
                method: "POST",
                headers: this.reqHeaders(),
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            this.extractSession(resp);
            if (resp.status === 202 || resp.status === 204)
                return null;
            if (!resp.ok) {
                const body = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${body.slice(0, 200)}`);
            }
            const ct = resp.headers.get("content-type") ?? "";
            const text = await resp.text();
            if (ct.includes("text/event-stream")) {
                return WsInsightMcpClient.parseSSE(text);
            }
            return text.trim() ? JSON.parse(text) : null;
        }
        finally {
            clearTimeout(timer);
        }
    }
    async notify(payload) {
        try {
            const resp = await fetch(this.mcpUrl, {
                method: "POST",
                headers: this.notifyHeaders(),
                body: JSON.stringify(payload),
            });
            this.extractSession(resp);
        }
        catch {
            // notifications are fire-and-forget
        }
    }
    // -------------------------------------------------------------------------
    // MCP protocol
    // -------------------------------------------------------------------------
    async initialize() {
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "initialize",
            params: {
                protocolVersion: "2025-03-26",
                capabilities: {},
                clientInfo: { name: "clawsight", version: "1.0.0" },
            },
        }));
        await this.notify({ jsonrpc: "2.0", method: "notifications/initialized" });
        return data ?? {};
    }
    async ensureInitialized() {
        if (!this.sessionId)
            await this.initialize();
    }
    async listTools() {
        await this.ensureInitialized();
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "tools/list",
        }));
        return (data?.["result"]?.["tools"] ?? []);
    }
    async callTool(name, args) {
        await this.ensureInitialized();
        const data = (await this.post({
            jsonrpc: "2.0",
            id: this.nextId(),
            method: "tools/call",
            params: { name, arguments: args },
        }));
        if (!data)
            return "[No response from MCP server]";
        if (data["error"]) {
            const e = data["error"];
            return `[MCP Error ${e["code"] ?? ""}]: ${e["message"] ?? ""}`;
        }
        const content = data["result"]?.["content"] ?? [];
        const texts = content
            .filter((c) => typeof c === "object" &&
            c !== null &&
            c.type === "text")
            .map((c) => c.text);
        return texts.join("\n") || "[Empty response]";
    }
    reset() {
        this.sessionId = null;
        this.msgId = 0;
    }
    // -------------------------------------------------------------------------
    // Response helper
    // -------------------------------------------------------------------------
    static asText(title, body) {
        return { content: [{ type: "text", text: `## ${title}\n\n${body}` }] };
    }
}
